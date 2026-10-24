import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from data_engine.db_manager import init_db, get_connection
from data_engine.upstox_client import UpstoxClient
from data_engine.screener_and_nse_ings import DeepIndianFundamentals
from data_engine.fundamentals_sync import FundamentalsSync


def fetch_stock_history(isin: str, symbol: str, nse_key: str, bse_key: str, years: int = 3) -> pd.DataFrame:
    """Pure network fetch of daily OHLCV (thread-safe, NO database access)."""
    end_dt = datetime.now().strftime("%Y-%m-%d")
    start_dt = (datetime.now() - timedelta(days=365 * years)).strftime("%Y-%m-%d")

    inst_key = nse_key if (nse_key and pd.notna(nse_key)) else bse_key
    df_candles = pd.DataFrame()
    if inst_key and pd.notna(inst_key):
        try:
            df_candles = UpstoxClient().fetch_historical_candles(str(inst_key), start_dt, end_dt, interval="day")
        except Exception:
            df_candles = pd.DataFrame()

    # Fallback to yfinance if Upstox historical endpoint returns empty
    if df_candles.empty:
        try:
            hist = yf.Ticker(f"{symbol}.NS").history(period=f"{years}y", auto_adjust=False)
            if hist.empty:
                hist = yf.Ticker(f"{symbol}.BO").history(period=f"{years}y", auto_adjust=False)
            if not hist.empty:
                hist = hist.reset_index()
                df_candles = pd.DataFrame({
                    "trade_date": pd.to_datetime(hist["Date"]).dt.date,
                    "open": hist["Open"].round(2),
                    "high": hist["High"].round(2),
                    "low": hist["Low"].round(2),
                    "close": hist["Close"].round(2),
                    "volume": hist["Volume"].fillna(0).astype("int64")
                })
        except Exception:
            return pd.DataFrame()
    return df_candles


def write_candle_batch(frames: list[pd.DataFrame]) -> int:
    """Main-thread DB writer: bulk-upserts a batch of candle frames into daily_market."""
    usable = [f for f in frames if f is not None and not f.empty]
    if not usable:
        return 0
    all_df = pd.concat(usable, ignore_index=True)
    all_df = all_df.drop_duplicates(subset=["isin", "trade_date"], keep="last")

    all_df["turnover_cr"] = ((all_df["close"] * all_df["volume"]) / 1e7).round(4)

    # Candle sources carry no delivery data: store NULL (missing) until NSE Bhavcopy supplies it
    con = get_connection()
    con.register("temp_hist", all_df)
    con.execute("""
        INSERT INTO daily_market (isin, trade_date, open, high, low, close, volume, delivery_qty, delivery_pct, turnover_cr)
        SELECT isin, trade_date, open, high, low, close, volume, NULL, NULL, turnover_cr
        FROM temp_hist
        ON CONFLICT (isin, trade_date) DO NOTHING;
    """)
    con.close()
    return len(all_df)


def backfill_stock_history(isin: str, symbol: str, nse_key: str, bse_key: str, years: int = 3) -> int:
    """Single-stock compatibility path: fetch then immediately write."""
    df_candles = fetch_stock_history(isin, symbol, nse_key, bse_key, years=years)
    if df_candles.empty:
        return 0
    df_candles = df_candles.copy()
    df_candles["isin"] = isin
    return write_candle_batch([df_candles])


def get_backfill_targets(limit: int) -> pd.DataFrame:
    """Targets = the most active stocks (>= 25 Lakhs turnover on the latest NSE Bhavcopy day).
    No hand-picked winners: seeding known multibaggers would bias every backtest."""
    con = get_connection()
    latest = con.execute("SELECT MAX(trade_date) FROM daily_market").fetchone()[0]
    if latest is None:
        df = con.execute("""
            SELECT isin, symbol, nse_key, bse_key, 0.0 AS turnover_cr
            FROM instruments
            ORDER BY nse_key IS NULL ASC, symbol ASC
            LIMIT ?
        """, [limit]).df()
    else:
        df = con.execute("""
            SELECT i.isin, i.symbol, i.nse_key, i.bse_key, d.turnover_cr
            FROM instruments i
            JOIN daily_market d ON d.isin = i.isin AND d.trade_date = ?
            WHERE d.turnover_cr >= 0.25
            ORDER BY d.turnover_cr DESC,
                     i.symbol ASC
            LIMIT ?
        """, [latest, limit]).df()
    con.close()
    return df


def _worker_fetch(row, years: int):
    """Executed on ThreadPoolExecutor workers: network IO only, never touches DuckDB."""
    isin, sym = row["isin"], row["symbol"]
    df_candles = fetch_stock_history(isin, sym, row["nse_key"], row["bse_key"], years=years)

    deep = DeepIndianFundamentals()
    parsed = deep.parse_screener_company(sym)
    src, fund = (None, None)
    if parsed is not None:
        src, fund = "screener", parsed
    else:
        ydata = FundamentalsSync().fetch_ticker_fundamentals(sym)
        if ydata:
            src, fund = "yf", ydata
    return (isin, sym, df_candles, src, fund)


def run_backfill(limit: int = 250, years: int = 3, workers: int = 1):
    init_db()
    con = get_connection()
    count = con.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
    con.close()
    if count == 0:
        UpstoxClient().sync_master_instruments()

    df_targets = get_backfill_targets(limit)
    if df_targets.empty:
        print("No eligible instruments found (is the instrument master and Bhavcopy synced?)")
        return
    print(f"Backfilling {len(df_targets)} active stocks | workers={workers} | {years}y candles + Screener quarterly P&L")

    deep = DeepIndianFundamentals()
    yfs = FundamentalsSync()
    candle_buf = []
    done = 0
    candles_ok = 0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_worker_fetch, row, years) for _, row in df_targets.iterrows()]
        for fut in as_completed(futures):
            try:
                isin, sym, df_candles, src, fund = fut.result()
            except Exception as e:
                done += 1
                print(f"[{done}/{len(df_targets)}] WORKER ERROR: {repr(e)}")
                continue
            if df_candles is not None and not df_candles.empty:
                df_candles = df_candles.copy()
                df_candles["isin"] = isin
                candle_buf.append(df_candles)
                candles_ok += 1
            else:
                df_candles = None

            # All DuckDB writes happen here on the main thread (DuckDB is not thread-safe for multi-writer)
            if src == "screener" and fund:
                deep.write_screener_company(isin, fund)
            elif src == "yf" and fund:
                yfs.write_ticker_fundamentals(isin, fund)

            done += 1
            print(f"[{done}/{len(df_targets)}] {sym}: {'OK' if df_candles is not None else 'NO CANDLES'} | fundamentals={src or 'none'}")
            if len(candle_buf) >= 25:
                write_candle_batch(candle_buf)
                candle_buf.clear()

    write_candle_batch(candle_buf)
    candle_buf.clear()
    print(f"Backfill complete: {done} targets processed, {candles_ok} with historical candles.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=250, help="Number of stocks to backfill")
    parser.add_argument("--years", type=int, default=3, help="Years of daily history")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent fetch threads (writes stay on main thread)")
    args = parser.parse_args()
    run_backfill(limit=args.limit, years=args.years, workers=args.workers)

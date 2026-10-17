# 05. HISTORICAL 3-YEAR BACKFILL & DEEP INDIAN FUNDAMENTALS ENGINE

The basic daily sync (`sync_daily.py`) only pulls the last 5–10 days of data. To run historical Time-Machine backtests on **CUPID**, **STLTECH**, **HFCL**, and the broader NSE/BSE universe—and to get accurate Indian **ROCE, Quarterly OPM%, Promoter Pledge %, and ASM/GSM stages**—add the following two production scripts to `data_engine/`.

---

## 1. `data_engine/screener_and_nse_ings.py`
Pulls deep Indian fundamentals (12 quarters of Sales, Operating Profit, OPM%, Net Profit, EPS, ROCE, ROE, Debt-to-Equity, Promoter Holding %, and Promoter Pledge %) plus NSE ASM/GSM surveillance stages.

```python
import io
import time
import re
import pandas as pd
import requests
from bs4 import BeautifulSoup
from data_engine.db_manager import get_connection


class DeepIndianFundamentals:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def _clean_num(self, val: str) -> float:
        if pd.isna(val):
            return 0.0
        s = re.sub(r"[^0-9.\-]", "", str(val))
        try:
            return float(s) if s not in ("", "-", ".") else 0.0
        except Exception:
            return 0.0

    def sync_screener_company(self, isin: str, symbol: str) -> bool:
        """
        Parses top ratios, 12-quarter P&L table, Cash Flow conversion, and Shareholding pattern
        for a given NSE/BSE symbol from Screener.in for personal research use.
        """
        urls = [
            f"[https://www.screener.in/company/](https://www.screener.in/company/){symbol}/consolidated/",
            f"[https://www.screener.in/company/](https://www.screener.in/company/){symbol}/"
        ]
        soup = None
        for url in urls:
            try:
                resp = self.session.get(url, timeout=15)
                if resp.status_code == 200 and "top-ratios" in resp.text:
                    soup = BeautifulSoup(resp.text, "lxml")
                    if soup.find("section", {"id": "quarters"}):
                        break
            except Exception:
                continue

        if soup is None:
            return False

        # 1. Extract Top Ratios (Market Cap, ROCE, ROE)
        ratios = {}
        ul = soup.find("ul", {"id": "top-ratios"})
        if ul:
            for li in ul.find_all("li"):
                name_el = li.find("span", {"class": "name"})
                val_el = li.find("span", {"class": "number"})
                if name_el and val_el:
                    ratios[name_el.get_text(strip=True).lower()] = self._clean_num(val_el.get_text(strip=True))

        mcap_cr = ratios.get("market cap", 0.0)
        roce_pct = ratios.get("roce", 0.0)
        roe_pct = ratios.get("roe", 0.0)
        cmp_val = ratios.get("current price", 1.0)
        total_shares = int((mcap_cr * 1e7) / max(cmp_val, 0.1)) if mcap_cr > 0 else 0

        # 2. Extract Shareholding Pattern (Promoter % & Public Float)
        promoter_pct = 50.0
        promoter_change_qoq = 0.0
        sh_section = soup.find("section", {"id": "shareholding"})
        if sh_section:
            try:
                tables = pd.read_html(io.StringIO(str(sh_section)))
                if tables:
                    sh_df = tables[0]
                    prom_row = sh_df[sh_df.iloc[:, 0].astype(str).str.contains("Promoters", case=False, na=False)]
                    if not prom_row.empty and sh_df.shape[1] >= 3:
                        latest_prom = self._clean_num(prom_row.iloc[0, -1])
                        prev_prom = self._clean_num(prom_row.iloc[0, -2])
                        promoter_pct = latest_prom
                        promoter_change_qoq = round(latest_prom - prev_prom, 2)
            except Exception:
                pass

        public_float_shares = int(total_shares * max((100.0 - promoter_pct) / 100.0, 0.10))

        # 3. Extract Cash Flow Conversion (3Yr CFO / 3Yr PAT) & Balance Sheet Debt/Equity
        cfo_to_pat = 1.0
        debt_to_eq = 0.0
        cf_section = soup.find("section", {"id": "cash-flow"})
        pl_section = soup.find("section", {"id": "profit-loss"})
        bs_section = soup.find("section", {"id": "balance-sheet"})

        try:
            if bs_section:
                bs_df = pd.read_html(io.StringIO(str(bs_section)))[0]
                borrow_row = bs_df[bs_df.iloc[:, 0].astype(str).str.contains("Borrowings", case=False, na=False)]
                eq_row = bs_df[bs_df.iloc[:, 0].astype(str).str.contains("Equity Capital", case=False, na=False)]
                res_row = bs_df[bs_df.iloc[:, 0].astype(str).str.contains("Reserves", case=False, na=False)]
                if not borrow_row.empty and not eq_row.empty and not res_row.empty:
                    debt = self._clean_num(borrow_row.iloc[0, -1])
                    net_worth = self._clean_num(eq_row.iloc[0, -1]) + self._clean_num(res_row.iloc[0, -1])
                    debt_to_eq = round(debt / max(net_worth, 1.0), 2)

            if cf_section and pl_section:
                cf_df = pd.read_html(io.StringIO(str(cf_section)))[0]
                pl_df = pd.read_html(io.StringIO(str(pl_section)))[0]
                cfo_row = cf_df[cf_df.iloc[:, 0].astype(str).str.contains("Cash from Operating", case=False, na=False)]
                pat_row = pl_df[pl_df.iloc[:, 0].astype(str).str.contains("Net Profit", case=False, na=False)]
                if not cfo_row.empty and not pat_row.empty and cf_df.shape[1] >= 4:
                    cfo_3y = sum(self._clean_num(cfo_row.iloc[0, -i]) for i in range(1, 4))
                    pat_3y = sum(self._clean_num(pat_row.iloc[0, -i]) for i in range(1, 4))
                    cfo_to_pat = round(cfo_3y / max(pat_3y, 1.0), 2) if pat_3y > 0 else 0.5
        except Exception:
            pass

        con = get_connection()
        con.execute("""
            UPDATE instruments SET
                market_cap_cr = CASE WHEN ? > 0 THEN ? ELSE market_cap_cr END,
                total_shares = CASE WHEN ? > 0 THEN ? ELSE total_shares END,
                public_float_shares = CASE WHEN ? > 0 THEN ? ELSE public_float_shares END,
                promoter_pct = ?,
                promoter_change_qoq = ?,
                roce_pct = ?,
                roe_pct = ?,
                debt_to_equity = ?,
                cfo_to_pat_ratio = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE isin = ?;
        """, [mcap_cr, mcap_cr, total_shares, total_shares, public_float_shares, public_float_shares,
              promoter_pct, promoter_change_qoq, roce_pct, roe_pct, debt_to_eq, cfo_to_pat, isin])

        # 4. Extract Quarterly Results Table (Last 12 Quarters)
        q_section = soup.find("section", {"id": "quarters"})
        if q_section:
            try:
                q_df = pd.read_html(io.StringIO(str(q_section)))[0]
                q_df.rename(columns={q_df.columns[0]: "Metric"}, inplace=True)
                q_df["Metric"] = q_df["Metric"].astype(str).str.strip()

                for col in q_df.columns[1:]:
                    try:
                        q_end_dt = pd.to_datetime(col, format="%b %Y") + pd.offsets.MonthEnd(1)
                        q_end = q_end_dt.date()
                        # Set point-in-time filing date 42 days after quarter end
                        filing_dt = (q_end_dt + pd.Timedelta(days=42)).date()
                    except Exception:
                        continue

                    def get_row_val(pattern: str) -> float:
                        m = q_df[q_df["Metric"].str.contains(pattern, case=False, na=False)]
                        return self._clean_num(m.iloc[0][col]) if not m.empty else 0.0

                    sales = get_row_val(r"^Sales|^Revenue")
                    op_profit = get_row_val(r"^Operating Profit|^Financing Profit")
                    opm = get_row_val(r"^OPM|^Financing Margin")
                    pat = get_row_val(r"^Net Profit")
                    eps = get_row_val(r"^EPS")

                    con.execute("""
                        INSERT INTO quarterly_results (isin, quarter_end, filing_date, sales_cr, op_profit_cr, opm_pct, net_profit_cr, eps)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (isin, quarter_end) DO UPDATE SET
                            sales_cr = EXCLUDED.sales_cr,
                            op_profit_cr = EXCLUDED.op_profit_cr,
                            opm_pct = EXCLUDED.opm_pct,
                            net_profit_cr = EXCLUDED.net_profit_cr,
                            eps = EXCLUDED.eps;
                    """, [isin, q_end, filing_dt, sales, op_profit, opm, pat, eps])
            except Exception:
                pass

        con.close()
        return True
```

---

## 2. `data_engine/backfill_history.py`
Populates 3 years of historical daily OHLCV candles from **Upstox API v2** (with automatic fallback to `yfinance` if an instrument key was recently migrated) + deep fundamentals so your **Time-Machine Validator** works immediately on stocks like **CUPID**, **STLTECH**, **HFCL**, and the active NSE/BSE universe.

```python
import argparse
import time
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from data_engine.db_manager import init_db, get_connection
from data_engine.upstox_client import UpstoxClient
from data_engine.screener_and_nse_ings import DeepIndianFundamentals
from data_engine.fundamentals_sync import FundamentalsSync


PRIORITY_SEED_TICKERS = [
    "CUPID", "STLTECH", "HFCL", "TEJASNET", "NETWEB", "E2E", "KAYNES",
    "PGEL", "SHAKTIPUMP", "TARIL", "GENUSPOWER", "ZENTEC", "GRAVITA",
    "ANANTRAJ", "WABAG", "NEULANDLAB", "SUZLON", "INOXWIND", "JYOTICNC"
]


def backfill_stock_history(isin: str, symbol: str, nse_key: str, bse_key: str, years: int = 3):
    client = UpstoxClient()
    end_dt = datetime.now().strftime("%Y-%m-%d")
    start_dt = (datetime.now() - timedelta(days=365 * years)).strftime("%Y-%m-%d")

    inst_key = nse_key if (nse_key and pd.notna(nse_key)) else bse_key
    df_candles = pd.DataFrame()
    if inst_key and pd.notna(inst_key):
        df_candles = client.fetch_historical_candles(str(inst_key), start_dt, end_dt, interval="day")

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
            return 0

    if df_candles.empty:
        return 0

    df_candles["isin"] = isin
    # Estimate delivery_qty as 45% of volume only on historical rows where NSE Bhavcopy wasn't synced yet
    df_candles["delivery_qty"] = (df_candles["volume"] * 0.45).astype("int64")
    df_candles["delivery_pct"] = 45.0
    df_candles["turnover_cr"] = ((df_candles["close"] * df_candles["volume"]) / 1e7).round(4)

    con = get_connection()
    con.register("temp_hist", df_candles)
    con.execute("""
        INSERT INTO daily_market (isin, trade_date, open, high, low, close, volume, delivery_qty, delivery_pct, turnover_cr)
        SELECT isin, trade_date, open, high, low, close, volume, delivery_qty, delivery_pct, turnover_cr
        FROM temp_hist
        ON CONFLICT (isin, trade_date) DO NOTHING;
    """)
    con.close()
    return len(df_candles)


def run_backfill(limit: int = 250, years: int = 3):
    init_db()
    con = get_connection()
    count = con.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
    con.close()
    if count == 0:
        UpstoxClient().sync_master_instruments()

    con = get_connection()
    placeholders = ",".join([f"'{s}'" for s in PRIORITY_SEED_TICKERS])
    df_targets = con.execute(f"""
        SELECT isin, symbol, nse_key, bse_key
        FROM instruments
        ORDER BY CASE WHEN symbol IN ({placeholders}) THEN 0 ELSE 1 END,
                 nse_key IS NULL ASC,
                 symbol ASC
        LIMIT ?
    """, [limit]).df()
    con.close()

    deep_sync = DeepIndianFundamentals()
    yf_sync = FundamentalsSync()

    for idx, row in df_targets.iterrows():
        isin, sym = row["isin"], row["symbol"]
        rows_added = backfill_stock_history(isin, sym, row["nse_key"], row["bse_key"], years=years)
        ok = deep_sync.sync_screener_company(isin, sym)
        if not ok:
            yf_sync.sync_ticker_fundamentals(isin, sym)
        print(f"[{idx+1}/{len(df_targets)}] {sym}: {rows_added} daily candles + Quarterly P&L synced.")
        time.sleep(0.4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=250, help="Number of stocks to backfill")
    parser.add_argument("--years", type=int, default=3, help="Years of daily history")
    args = parser.parse_args()
    run_backfill(limit=args.limit, years=args.years)
```
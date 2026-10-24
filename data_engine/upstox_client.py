from __future__ import annotations

import gzip
import json
import time
from datetime import datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from config import UPSTOX_ACCESS_TOKEN, UPSTOX_BASE_URL, UPSTOX_INSTRUMENTS_URL
from data_engine.db_manager import get_connection


def _http_get_json(url: str, headers: dict | None = None, timeout: int = 20):
    request_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    request_headers.update(headers or {})
    try:
        request = Request(url, headers=request_headers, method="GET")
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError:
        return None

class UpstoxClient:
    def __init__(self, access_token: str = None):
        self.token = access_token or UPSTOX_ACCESS_TOKEN
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

    def sync_master_instruments(self):
        """Downloads complete NSE_EQ and BSE_EQ equity master and upserts into DuckDB."""
        import pandas as pd
        import requests

        print("Downloading Upstox Master Instruments...")
        resp = requests.get(UPSTOX_INSTRUMENTS_URL, timeout=60)
        resp.raise_for_status()
        raw_data = gzip.decompress(resp.content).decode("utf-8")
        records = json.loads(raw_data)
        df = pd.DataFrame(records)

        # Keep active NSE_EQ and BSE_EQ equities with valid ISINs
        eq_df = df[
            (df["segment"].isin(["NSE_EQ", "BSE_EQ"])) &
            (df["instrument_type"].isin(["EQ", "BE", "A", "B", "T"])) &
            (df["isin"].notna()) &
            (df["isin"].str.startswith("INE"))
        ].copy()

        nse_df = eq_df[eq_df["segment"] == "NSE_EQ"][["isin", "trading_symbol", "name", "instrument_key"]].rename(
            columns={"trading_symbol": "symbol", "name": "company_name", "instrument_key": "nse_key"}
        ).drop_duplicates(subset=["isin"])

        bse_df = eq_df[eq_df["segment"] == "BSE_EQ"][["isin", "trading_symbol", "name", "instrument_key"]].rename(
            columns={"trading_symbol": "bse_symbol", "name": "bse_name", "instrument_key": "bse_key"}
        ).drop_duplicates(subset=["isin"])

        merged = pd.merge(nse_df, bse_df, on="isin", how="outer")
        merged["symbol"] = merged["symbol"].fillna(merged["bse_symbol"])
        merged["company_name"] = merged["company_name"].fillna(merged["bse_name"])
        merged = merged[["isin", "symbol", "company_name", "nse_key", "bse_key"]].dropna(subset=["symbol"])

        con = get_connection()
        con.register("temp_inst", merged)
        con.execute("""
            INSERT INTO instruments (isin, symbol, company_name, nse_key, bse_key)
            SELECT isin, symbol, company_name, nse_key, bse_key FROM temp_inst
            ON CONFLICT (isin) DO UPDATE SET
                symbol = EXCLUDED.symbol,
                company_name = EXCLUDED.company_name,
                nse_key = EXCLUDED.nse_key,
                bse_key = EXCLUDED.bse_key,
                updated_at = NOW();
        """)
        con.close()
        print(f"Synced {len(merged)} unique NSE/BSE equities into DuckDB.")

    def fetch_historical_candles(self, instrument_key: str, from_date: str, to_date: str, interval: str = "day") -> pd.DataFrame:
        """Fetches historical daily candles from Upstox API v2."""
        import pandas as pd
        import requests

        url = f"{UPSTOX_BASE_URL}/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}"
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=20)
        if resp.status_code != 200:
            return pd.DataFrame()
        candles = resp.json().get("data", {}).get("candles", [])
        if not candles:
            return pd.DataFrame()
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
        df["trade_date"] = pd.to_datetime(df["timestamp"]).dt.date
        return df[["trade_date", "open", "high", "low", "close", "volume"]]

    def fetch_batch_live_quotes(self, instrument_keys: list[str]) -> dict:
        """Fetches live OHLCV quotes for up to 500 instruments per call."""
        if not self.token:
            return {}
        results = {}
        for i in range(0, len(instrument_keys), 450):
            batch = instrument_keys[i:i + 450]
            keys_param = ",".join(batch)
            url = f"{UPSTOX_BASE_URL}/market-quote/quotes?instrument_key={keys_param}"
            payload = _http_get_json(url, headers=self.headers, timeout=20)
            if payload:
                results.update(payload.get("data", {}))
            time.sleep(0.25)
        return results

    def refresh_live_quotes_into_db(self, trade_date: str = None) -> int:
        """Fetches live Upstox quotes for the latest scored universe and upserts the
        OHLCV of the latest active session in daily_market on the main (UI) thread."""
        import pandas as pd

        con = get_connection()
        session_date = trade_date
        if not session_date:
            session_date = con.execute("SELECT MAX(trade_date) FROM daily_market").fetchone()[0]
        if not session_date:
            con.close()
            return 0

        scored = con.execute("""
            SELECT s.isin, COALESCE(i.nse_key, i.bse_key) AS inst_key, i.symbol
            FROM daily_quant_scores s
            JOIN instruments i ON i.isin = s.isin
            WHERE s.trade_date = (SELECT MAX(trade_date) FROM daily_quant_scores)
              AND COALESCE(i.nse_key, i.bse_key) IS NOT NULL
        """).fetchall()
        if not scored:
            con.close()
            return 0

        key_map = {}
        for isin, inst_key, sym in scored:
            if inst_key:
                key_map[str(inst_key).upper()] = isin
            if sym:
                key_map[str(sym).upper()] = isin

        quotes = self.fetch_batch_live_quotes([k for _, k, _ in scored])

        rows = []
        for resp_key, q in quotes.items():
            isin = key_map.get(str(resp_key).upper())
            if not isin:
                isin = key_map.get(str(q.get("symbol", "")).upper())
            if not isin:
                continue
            ohlc = q.get("ohlc") or {}
            last_px = float(q.get("last_price") or 0)
            if last_px <= 0:
                continue
            rows.append({
                "isin": isin,
                "trade_date": session_date,
                "open": float(ohlc.get("open") or 0),
                "high": float(ohlc.get("high") or 0),
                "low": float(ohlc.get("low") or 0),
                "close": last_px,
                "volume": int(q.get("volume") or 0),
            })
        if not rows:
            con.close()
            return 0

        df_live = pd.DataFrame(rows).drop_duplicates(subset=["isin"], keep="first")
        con.register("temp_live", df_live)
        con.execute("""
            INSERT INTO daily_market (isin, trade_date, open, high, low, close, volume, delivery_qty, delivery_pct, turnover_cr)
            SELECT isin, CAST(? AS DATE), open, high, low, close, volume, NULL, NULL, close * volume / 1e7 FROM temp_live
            ON CONFLICT (isin, trade_date) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume;
        """, [str(session_date)])
        con.close()
        return len(df_live)
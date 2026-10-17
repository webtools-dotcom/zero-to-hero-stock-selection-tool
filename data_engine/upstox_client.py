import gzip
import json
import time
from datetime import datetime, timedelta
import pandas as pd
import requests
from config import UPSTOX_ACCESS_TOKEN, UPSTOX_BASE_URL, UPSTOX_INSTRUMENTS_URL
from data_engine.db_manager import get_connection

class UpstoxClient:
    def __init__(self, access_token: str = None):
        self.token = access_token or UPSTOX_ACCESS_TOKEN
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

    def sync_master_instruments(self):
        """Downloads complete NSE_EQ and BSE_EQ equity master and upserts into DuckDB."""
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
                updated_at = CURRENT_TIMESTAMP;
        """)
        con.close()
        print(f"Synced {len(merged)} unique NSE/BSE equities into DuckDB.")

    def fetch_historical_candles(self, instrument_key: str, from_date: str, to_date: str, interval: str = "day") -> pd.DataFrame:
        """Fetches historical daily candles from Upstox API v2."""
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
            resp = requests.get(url, headers=self.headers, timeout=20)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                results.update(data)
            time.sleep(0.25)
        return results
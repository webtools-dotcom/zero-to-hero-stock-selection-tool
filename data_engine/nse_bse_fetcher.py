import io
from datetime import datetime
import pandas as pd
import requests
from data_engine.db_manager import get_connection

class NSEBSEFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.nseindia.com/"
        })
        self._warm_cookies()

    def _warm_cookies(self):
        try:
            self.session.get("https://www.nseindia.com", timeout=10)
        except Exception:
            pass

    def fetch_nse_bhavcopy_delivery(self, date_obj: datetime) -> pd.DataFrame:
        """Downloads NSE Full Bhavcopy with Deliverable Quantity & Delivery %."""
        date_str = date_obj.strftime("%d%m%Y")
        url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date_str}.csv"
        resp = self.session.get(url, timeout=20)
        if resp.status_code != 200 or len(resp.content) < 500:
            return pd.DataFrame()
        
        df = pd.read_csv(io.BytesIO(resp.content))
        df.columns = [c.strip() for c in df.columns]
        for col in ["SYMBOL", "SERIES"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        
        df = df[df["SERIES"].isin(["EQ", "BE", "BZ", "SM", "ST"])].copy()
        df["trade_date"] = pd.to_datetime(date_obj.strftime("%Y-%m-%d")).date()
        df["open"] = pd.to_numeric(df["OPEN_PRICE"], errors="coerce")
        df["high"] = pd.to_numeric(df["HIGH_PRICE"], errors="coerce")
        df["low"] = pd.to_numeric(df["LOW_PRICE"], errors="coerce")
        df["close"] = pd.to_numeric(df["CLOSE_PRICE"], errors="coerce")
        df["volume"] = pd.to_numeric(df["TTL_TRD_QNTY"], errors="coerce").fillna(0).astype("int64")
        df["delivery_qty"] = pd.to_numeric(df["DELIV_QTY"], errors="coerce").fillna(0).astype("int64")
        df["delivery_pct"] = pd.to_numeric(df["DELIV_PER"], errors="coerce").fillna(0.0)
        df["turnover_cr"] = pd.to_numeric(df["TURNOVER_LACS"], errors="coerce").fillna(0.0) / 100.0
        
        # Fallback if delivery_qty is 0 on BE/BZ series (100% trade-for-trade delivery)
        mask_be = (df["SERIES"].isin(["BE", "BZ"])) & (df["delivery_qty"] == 0)
        df.loc[mask_be, "delivery_qty"] = df.loc[mask_be, "volume"]
        df.loc[mask_be, "delivery_pct"] = 100.0
        
        return df[["SYMBOL", "trade_date", "open", "high", "low", "close", "volume", "delivery_qty", "delivery_pct", "turnover_cr"]]

    def sync_bhavcopy_to_db(self, date_obj: datetime) -> int:
        bhav = self.fetch_nse_bhavcopy_delivery(date_obj)
        if bhav.empty:
            return 0
        con = get_connection()
        con.register("temp_bhav", bhav)
        con.execute("""
            INSERT INTO daily_market (isin, trade_date, open, high, low, close, volume, delivery_qty, delivery_pct, turnover_cr)
            SELECT i.isin, b.trade_date, b.open, b.high, b.low, b.close, b.volume, b.delivery_qty, b.delivery_pct, b.turnover_cr
            FROM temp_bhav b
            JOIN instruments i ON i.symbol = b.SYMBOL
            ON CONFLICT (isin, trade_date) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                delivery_qty = EXCLUDED.delivery_qty,
                delivery_pct = EXCLUDED.delivery_pct,
                turnover_cr = EXCLUDED.turnover_cr;
        """)
        con.close()
        return len(bhav)

    def _fetch_announcement_rows(self, days_back: int = 30) -> pd.DataFrame:
        """Network-only: pulls NSE equity corporate filings in 7-day windows across the
        last `days_back` days, attaching the instant deterministic base catalyst score."""
        from datetime import timedelta
        from ai_brain.catalyst_analyzer import deterministic_catalyst_score

        self._warm_cookies()
        rows = []
        today = datetime.now()
        cursor = today - timedelta(days=days_back)
        while cursor < today:
            win_end = min(cursor + timedelta(days=7) - timedelta(seconds=1), today)
            url = (
                "https://www.nseindia.com/api/corporate-announcements?index=equities"
                "&from_date=" + cursor.strftime("%d-%m-%Y") +
                "&to_date=" + win_end.strftime("%d-%m-%Y")
            )
            try:
                resp = self.session.get(url, timeout=20)
                items = resp.json() if resp.status_code == 200 else []
                if not isinstance(items, list):
                    items = []
            except Exception:
                items = []

            for item in items:
                symbol = str(item.get("symbol", "")).strip()
                isin = str(item.get("isin", "")).strip()
                seq_id = str(item.get("seq_id") or f"{symbol}_{item.get('an_dt', '')}")
                dt_str = item.get("an_dt", "")
                try:
                    filing_dt = pd.to_datetime(dt_str)
                except Exception:
                    filing_dt = datetime.now()
                headline = str(item.get("attchmntText", ""))[:280]
                body_text = str(item.get("attchmntText", ""))
                rows.append({
                    "filing_id": seq_id,
                    "isin": isin,
                    "symbol": symbol,
                    "filing_datetime": filing_dt,
                    "category": str(item.get("desc", "Announcement")),
                    "headline": headline,
                    "body_text": body_text,
                    "ai_catalyst_score": deterministic_catalyst_score(body_text),
                    "ai_summary": "",
                })
            cursor = win_end + timedelta(seconds=1)
            self._warm_cookies()

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).drop_duplicates(subset=["filing_id"], keep="last")

    def _insert_filings(self, df_filings: pd.DataFrame) -> int:
        """Deterministic single-writer DuckDB batch insert of parsed filings."""
        con = get_connection()
        con.register("temp_filings", df_filings)
        con.execute("""
            INSERT INTO corporate_filings (filing_id, isin, symbol, filing_datetime, category, headline, body_text, ai_catalyst_score, ai_summary)
            SELECT
                COALESCE(f.filing_id, f.symbol || '_' || CAST(f.filing_datetime AS VARCHAR)),
                COALESCE(NULLIF(f.isin, ''), i.isin),
                f.symbol,
                f.filing_datetime,
                f.category,
                f.headline,
                f.body_text,
                COALESCE(f.ai_catalyst_score, 0.0),
                COALESCE(f.ai_summary, '')
            FROM temp_filings f
            LEFT JOIN instruments i ON i.symbol = f.symbol
            WHERE COALESCE(NULLIF(f.isin, ''), i.isin) IS NOT NULL
            ON CONFLICT (filing_id) DO NOTHING;
        """)
        con.close()
        return len(df_filings)

    def sync_recent_corporate_announcements(self, days_back: int = 30) -> int:
        """Full sync: fetch 7-day windows of NSE corporate filings + store to DuckDB."""
        df_filings = self._fetch_announcement_rows(days_back=days_back)
        if df_filings.empty:
            return 0
        return self._insert_filings(df_filings)
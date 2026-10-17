import time
import pandas as pd
import yfinance as yf
from data_engine.db_manager import get_connection

class FundamentalsSync:
    """Syncs quarterly P&L, OPM%, Free Float Shares, and Valuation/Quality metrics."""

    def sync_ticker_fundamentals(self, isin: str, symbol: str):
        yf_ticker = f"{symbol}.NS"
        try:
            t = yf.Ticker(yf_ticker)
            info = t.info or {}
            if not info.get("marketCap"):
                t = yf.Ticker(f"{symbol}.BO")
                info = t.info or {}
        except Exception:
            return False

        mcap_cr = (info.get("marketCap") or 0) / 1e7
        total_shares = int(info.get("sharesOutstanding") or 0)
        float_shares = int(info.get("floatShares") or int(total_shares * 0.45))
        promoter_pct = float(info.get("heldPercentInsiders") or 0.50) * 100.0
        roe_pct = float(info.get("returnOnEquity") or 0.0) * 100.0
        roce_pct = float(info.get("returnOnAssets") or 0.0) * 160.0  # Proxy if ROCE not directly exposed
        debt_to_eq = float(info.get("debtToEquity") or 0.0) / 100.0
        sector = str(info.get("sector") or "Industrial")
        sub_industry = str(info.get("industry") or "General")

        con = get_connection()
        con.execute("""
            UPDATE instruments SET
                sector = ?,
                sub_industry = ?,
                market_cap_cr = ?,
                total_shares = ?,
                public_float_shares = CASE WHEN ? > 0 THEN ? ELSE GREATEST(CAST(? * 0.45 AS BIGINT), 100000) END,
                promoter_pct = ?,
                roe_pct = ?,
                roce_pct = ?,
                debt_to_equity = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE isin = ?;
        """, [sector, sub_industry, mcap_cr, total_shares, float_shares, float_shares, total_shares,
              promoter_pct, roe_pct, roce_pct, debt_to_eq, isin])

        # Quarterly Income Statement Sync
        try:
            q_inc = t.quarterly_income_stmt
            if q_inc is not None and not q_inc.empty:
                for col_date in q_inc.columns:
                    q_end = pd.to_datetime(col_date).date()
                    # Assume filing date is 40 days after quarter end for point-in-time backtesting safety
                    filing_dt = (pd.to_datetime(col_date) + pd.Timedelta(days=40)).date()
                    col_series = q_inc[col_date]
                    sales = float(col_series.get("Total Revenue") or col_series.get("Operating Revenue") or 0.0) / 1e7
                    ebit = float(col_series.get("Operating Income") or col_series.get("EBITDA") or 0.0) / 1e7
                    pat = float(col_series.get("Net Income") or 0.0) / 1e7
                    eps = float(col_series.get("Basic EPS") or col_series.get("Diluted EPS") or 0.0)
                    opm = (ebit / sales * 100.0) if sales > 0 else 0.0

                    con.execute("""
                        INSERT INTO quarterly_results (isin, quarter_end, filing_date, sales_cr, op_profit_cr, opm_pct, net_profit_cr, eps)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (isin, quarter_end) DO UPDATE SET
                            sales_cr = EXCLUDED.sales_cr,
                            op_profit_cr = EXCLUDED.op_profit_cr,
                            opm_pct = EXCLUDED.opm_pct,
                            net_profit_cr = EXCLUDED.net_profit_cr,
                            eps = EXCLUDED.eps;
                    """, [isin, q_end, filing_dt, sales, ebit, opm, pat, eps])
        except Exception:
            pass

        con.close()
        return True

    def batch_sync_universe(self, limit: int = 200):
        con = get_connection()
        df = con.execute("""
            SELECT isin, symbol FROM instruments
            ORDER BY market_cap_cr ASC, updated_at ASC
            LIMIT ?
        """, [limit]).df()
        con.close()

        for _, row in df.iterrows():
            self.sync_ticker_fundamentals(row["isin"], row["symbol"])
            time.sleep(0.15)
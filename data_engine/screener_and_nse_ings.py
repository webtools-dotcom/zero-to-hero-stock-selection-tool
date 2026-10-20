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

    def parse_screener_company(self, symbol: str) -> dict | None:
        """
        Pure network + HTML parse (thread-safe, NO database access).
        Returns instrument ratios, shareholding, debt/cash-flow metrics and the last
        12 quarters P&L, or None when Screener.in is unreachable for the symbol.
        """
        urls = [
            f"https://www.screener.in/company/{symbol}/consolidated/",
            f"https://www.screener.in/company/{symbol}/"
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
            return None

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

        # 4. Extract Quarterly Results Table (Last 12 Quarters)
        q_rows = []
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

                    q_rows.append((q_end, filing_dt, sales, op_profit, opm, pat, eps))
            except Exception:
                pass

        return {
            "mcap_cr": float(mcap_cr),
            "total_shares": int(total_shares),
            "public_float_shares": int(public_float_shares),
            "promoter_pct": float(promoter_pct),
            "promoter_change_qoq": float(promoter_change_qoq),
            "roce_pct": float(roce_pct),
            "roe_pct": float(roe_pct),
            "debt_to_eq": float(debt_to_eq),
            "cfo_to_pat": float(cfo_to_pat),
            "quarterly": q_rows,
        }

    def write_screener_company(self, isin: str, data: dict):
        """Main-thread DB writer: upserts ratios + quarterly rows from parse_screener_company()."""
        if not data:
            return
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
        """, [data["mcap_cr"], data["mcap_cr"], data["total_shares"], data["total_shares"],
              data["public_float_shares"], data["public_float_shares"],
              data["promoter_pct"], data["promoter_change_qoq"], data["roce_pct"], data["roe_pct"],
              data["debt_to_eq"], data["cfo_to_pat"], isin])

        for q_end, filing_dt, sales, op_profit, opm, pat, eps in data.get("quarterly", []):
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
        con.close()

    def sync_screener_company(self, isin: str, symbol: str) -> bool:
        """Convenience wrapper: parse (network) then write (DB). Used by single-thread paths."""
        data = self.parse_screener_company(symbol)
        if data is None:
            return False
        self.write_screener_company(isin, data)
        return True

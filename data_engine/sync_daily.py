import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timedelta
from data_engine.db_manager import init_db, get_connection
from data_engine.upstox_client import UpstoxClient
from data_engine.nse_bse_fetcher import NSEBSEFetcher
from quant_engine.feature_factory import compute_and_store_daily_scores

def run_daily_eod_pipeline(days_back: int = 5):
    """Master daily sync: updates Bhavcopy delivery data, NSE announcements, and recomputes all Quant Scores."""
    init_db()
    con = get_connection()
    inst_count = con.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
    con.close()

    if inst_count == 0:
        UpstoxClient().sync_master_instruments()

    fetcher = NSEBSEFetcher()
    today = datetime.now()
    synced_dates = []
    for offset in range(days_back, -1, -1):
        dt = today - timedelta(days=offset)
        if dt.weekday() < 5:  # Monday–Friday
            rows = fetcher.sync_bhavcopy_to_db(dt)
            if rows >= 1000:
                synced_dates.append(dt.date())
                print(f"[{dt.strftime('%Y-%m-%d')}] Synced {rows} equities with NSE Delivery Bhavcopy.")

    ann_count = fetcher.sync_recent_corporate_announcements()
    print(f"Synced {ann_count} recent NSE corporate announcements.")

    con = get_connection()
    if synced_dates:
        latest_date = max(synced_dates)
    else:
        latest_date = con.execute("""
            SELECT trade_date FROM daily_market
            GROUP BY trade_date
            HAVING COUNT(*) >= 1000
            ORDER BY trade_date DESC
            LIMIT 1
        """).fetchone()[0]
    con.close()

    if latest_date:
        print(f"Computing Mode A, Mode B, and Master Quant Scores for {latest_date}...")
        compute_and_store_daily_scores(str(latest_date))
        try:  # paper log must never break the EOD sync itself
            from backtest.paper_trades import log_daily_picks, update_outcomes
            print(f"Paper log: {log_daily_picks(str(latest_date))} picks frozen for {latest_date}, "
                  f"{update_outcomes()} open/pending trades re-checked.")
        except Exception:
            import traceback
            traceback.print_exc()
        print("Daily EOD Pipeline completed successfully.")
    else:
        print("No complete bhavcopy session available; skipping rescore.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-back", type=int, default=10,
                        help="Calendar days of NSE Bhavcopy to (re)sync; use ~550 to load real delivery history")
    run_daily_eod_pipeline(days_back=parser.parse_args().days_back)
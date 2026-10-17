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
    synced_days = 0
    for offset in range(days_back, -1, -1):
        dt = today - timedelta(days=offset)
        if dt.weekday() < 5:  # Monday–Friday
            rows = fetcher.sync_bhavcopy_to_db(dt)
            if rows > 0:
                synced_days += 1
                print(f"[{dt.strftime('%Y-%m-%d')}] Synced {rows} equities with NSE Delivery Bhavcopy.")

    ann_count = fetcher.sync_recent_corporate_announcements()
    print(f"Synced {ann_count} recent NSE corporate announcements.")

    con = get_connection()
    latest_date = con.execute("SELECT MAX(trade_date) FROM daily_market").fetchone()[0]
    con.close()

    if latest_date:
        print(f"Computing Mode A, Mode B, and Master Quant Scores for {latest_date}...")
        compute_and_store_daily_scores(str(latest_date))
        print("Daily EOD Pipeline completed successfully.")

if __name__ == "__main__":
    run_daily_eod_pipeline(days_back=10)
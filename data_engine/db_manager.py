import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import duckdb
from config import DB_PATH

def get_connection(read_only: bool = False, memory_limit: str = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(DB_PATH, read_only=read_only)
    if memory_limit:
        con.execute(f"SET memory_limit='{memory_limit}'")
        con.execute("SET threads=1")
    return con

def init_db():
    con = get_connection(read_only=False)
    
    con.execute("""
    CREATE TABLE IF NOT EXISTS instruments (
        isin VARCHAR PRIMARY KEY,
        symbol VARCHAR,
        company_name VARCHAR,
        nse_key VARCHAR,
        bse_key VARCHAR,
        sector VARCHAR DEFAULT 'Unknown',
        sub_industry VARCHAR DEFAULT 'Unknown',
        market_cap_cr DOUBLE DEFAULT 0.0,
        total_shares BIGINT DEFAULT 0,
        public_float_shares BIGINT DEFAULT 0,
        promoter_pct DOUBLE DEFAULT 50.0,
        promoter_change_qoq DOUBLE DEFAULT 0.0,
        pledge_pct DOUBLE DEFAULT 0.0,
        pledge_change_qoq DOUBLE DEFAULT 0.0,
        roce_pct DOUBLE DEFAULT 0.0,
        roe_pct DOUBLE DEFAULT 0.0,
        debt_to_equity DOUBLE DEFAULT 0.0,
        cfo_to_pat_ratio DOUBLE DEFAULT 1.0,
        asm_gsm_stage VARCHAR DEFAULT 'NONE',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS daily_market (
        isin VARCHAR,
        trade_date DATE,
        open DOUBLE,
        high DOUBLE,
        low DOUBLE,
        close DOUBLE,
        volume BIGINT,
        delivery_qty BIGINT DEFAULT 0,
        delivery_pct DOUBLE DEFAULT 0.0,
        turnover_cr DOUBLE DEFAULT 0.0,
        PRIMARY KEY (isin, trade_date)
    );
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS quarterly_results (
        isin VARCHAR,
        quarter_end DATE,
        filing_date DATE,
        sales_cr DOUBLE DEFAULT 0.0,
        op_profit_cr DOUBLE DEFAULT 0.0,
        opm_pct DOUBLE DEFAULT 0.0,
        net_profit_cr DOUBLE DEFAULT 0.0,
        eps DOUBLE DEFAULT 0.0,
        PRIMARY KEY (isin, quarter_end)
    );
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS corporate_filings (
        filing_id VARCHAR PRIMARY KEY,
        isin VARCHAR,
        symbol VARCHAR,
        filing_datetime TIMESTAMP,
        category VARCHAR,
        headline TEXT,
        body_text TEXT,
        ai_catalyst_score DOUBLE DEFAULT 0.0,
        ai_summary TEXT DEFAULT ''
    );
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS daily_quant_scores (
        isin VARCHAR,
        trade_date DATE,
        symbol VARCHAR,
        close DOUBLE,
        market_cap_cr DOUBLE,
        sub_industry VARCHAR,
        mode_a_eligible BOOLEAN,
        mode_b_eligible BOOLEAN,
        mode_a_score DOUBLE,
        mode_b_score DOUBLE,
        master_score DOUBLE,
        primary_mode VARCHAR,
        float_absorption_10d_pct DOUBLE,
        delivery_spike_mult DOUBLE,
        op_leverage_score DOUBLE,
        catalyst_score DOUBLE,
        dormancy_score DOUBLE,
        dvm_quality_score DOUBLE,
        rs_percentile DOUBLE,
        vcp_coil_score DOUBLE,
        sector_sympathy_score DOUBLE,
        entry_trigger DOUBLE,
        pullback_zone VARCHAR,
        max_chase_price DOUBLE,
        stop_loss DOUBLE,
        risk_pct DOUBLE,
        emergency_intraday_sl DOUBLE,
        target_1 DOUBLE,
        target_2 DOUBLE,
        trailing_sl_ema50 DOUBLE,
        runner_trail_ema65 DOUBLE,
        live_price DOUBLE,
        live_price_date DATE,
        live_updated_at TIMESTAMP,
        PRIMARY KEY (isin, trade_date)
    );
    """)
    try:
        con.execute("ALTER TABLE daily_quant_scores ADD COLUMN IF NOT EXISTS runner_trail_ema65 DOUBLE;")
        con.execute("ALTER TABLE daily_quant_scores ADD COLUMN IF NOT EXISTS emergency_intraday_sl DOUBLE;")
        con.execute("ALTER TABLE daily_quant_scores ADD COLUMN IF NOT EXISTS live_price DOUBLE;")
        con.execute("ALTER TABLE daily_quant_scores ADD COLUMN IF NOT EXISTS live_price_date DATE;")
        con.execute("ALTER TABLE daily_quant_scores ADD COLUMN IF NOT EXISTS live_updated_at TIMESTAMP;")
    except Exception:
        pass
    scrub_estimated_delivery(con)
    con.close()

def scrub_estimated_delivery(con: duckdb.DuckDBPyConnection) -> None:
    """Older backfills stored delivery as a flat 45% of volume. NULL those rows so they read as
    missing (scored 0) instead of real; a later NSE Bhavcopy sync fills in the true values."""
    con.execute("""
        UPDATE daily_market SET delivery_qty = NULL, delivery_pct = NULL
        WHERE delivery_pct = 45.0 AND delivery_qty = FLOOR(volume * 0.45);
    """)

if __name__ == "__main__":
    init_db()
    print("DuckDB initialized successfully at:", DB_PATH)
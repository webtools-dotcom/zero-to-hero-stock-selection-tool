import re
import pandas as pd
from data_engine.db_manager import get_connection
from ai_brain.llm_router import LLMRouter
from ai_brain.prompts import SYSTEM_ANALYST_PROMPT

def get_top_candidates_df(mode: str = "MASTER", top_n: int = 5, trade_date: str = None) -> pd.DataFrame:
    con = get_connection()
    if not trade_date:
        trade_date = con.execute("SELECT MAX(trade_date) FROM daily_quant_scores").fetchone()[0]
    if not trade_date:
        con.close()
        return pd.DataFrame()

    mode_upper = mode.upper()
    if mode_upper == "A":
        order_col = "mode_a_score"
        where_clause = "AND s.mode_a_eligible = TRUE"
    elif mode_upper == "B":
        order_col = "mode_b_score"
        where_clause = "AND s.mode_b_eligible = TRUE"
    else:
        order_col = "master_score"
        where_clause = "AND (s.mode_a_eligible = TRUE OR s.mode_b_eligible = TRUE)"

    query = f"""
        SELECT s.*,
               COALESCE(
                   (SELECT headline FROM corporate_filings f
                    WHERE f.isin = s.isin
                    ORDER BY f.filing_datetime DESC LIMIT 1),
                   'No recent exchange filing in last 30d'
               ) AS latest_filing
        FROM daily_quant_scores s
        WHERE s.trade_date = CAST(? AS DATE)
          {where_clause}
        ORDER BY s.{order_col} DESC
        LIMIT ?
    """
    df = con.execute(query, [str(trade_date), int(top_n)]).df()
    con.close()
    return df

def parse_user_intent_and_run(user_query: str, llm: LLMRouter, default_top_n: int = 5) -> tuple[pd.DataFrame, str]:
    """
    Detects whether user asked for Master Scan, Mode A, Mode B, or a specific ticker,
    retrieves the exact quantitative table, and generates the AI Analyst response.
    """
    q_lower = user_query.lower()
    nums = re.findall(r"\btop\s+(\d+)\b|\b(\d+)\s+stocks\b", q_lower)
    top_n = default_top_n
    if nums:
        extracted = [int(x) for tup in nums for x in tup if x.isdigit()]
        if extracted:
            top_n = min(max(extracted[0], 1), 25)

    if "mode a" in q_lower or "turnaround" in q_lower or "cupid" in q_lower or "multibagger" in q_lower:
        mode = "A"
    elif "mode b" in q_lower or "compounder" in q_lower or "momentum" in q_lower:
        mode = "B"
    else:
        mode = "MASTER"

    df_picks = get_top_candidates_df(mode=mode, top_n=top_n)
    if df_picks.empty:
        return pd.DataFrame(), "No scored data found in local DuckDB yet. Click **[Run Daily EOD Sync]** in the sidebar first."

    payload_records = df_picks.to_dict(orient="records")
    user_payload = (
        f"User Query: {user_query}\n"
        f"Selected Scan Mode: {mode} | Requested Top N: {top_n}\n"
        f"Pre-Computed Quantitative Candidates & Trade Architect Levels:\n{payload_records}"
    )
    ai_answer = llm.generate(SYSTEM_ANALYST_PROMPT, user_payload, temperature=0.2)
    return df_picks, ai_answer
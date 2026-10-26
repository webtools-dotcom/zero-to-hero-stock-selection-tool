import re
import pandas as pd
from data_engine.db_manager import get_connection
from ai_brain.llm_router import LLMRouter
from ai_brain.prompts import SYSTEM_ANALYST_PROMPT

def get_top_candidates_df(mode: str = "MASTER", top_n: int = 5, trade_date: str = None,
                          max_price: float = None) -> pd.DataFrame:
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

    price_clause = ""
    params = [str(trade_date)]
    if max_price is not None:
        price_clause = "AND s.close <= ?"
        params.append(float(max_price))
    params.append(int(top_n))

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
          {price_clause}
        ORDER BY s.{order_col} DESC
        LIMIT ?
    """
    df = con.execute(query, params).df()
    con.close()
    return df

def build_fallback_trade_plan(df_picks: pd.DataFrame, mode: str = "MASTER", top_n: int = None,
                              max_price: float = None) -> str:
    """
    Zero-LLM institutional trade plan: renders every Top-N pick with full trade
    architecture straight from the quant columns, so the chat panel is always complete.
    """
    if df_picks is None or df_picks.empty:
        return "No scored candidates yet. Click **[Run Daily EOD Sync]** in the sidebar to populate the database."
    n = int(top_n) if top_n else len(df_picks)
    mode_label = {"A": "Growth (Mode A)", "B": "Momentum (Mode B)"}.get(mode, "Master")
    lines = [f"## {mode_label} · top {n}", "Plain quant plan (no AI commentary)."]
    if max_price is not None:
        lines.append(f"Price filter: up to ₹{float(max_price):,.2f}")
    lines.append("")
    for rank, (_, r) in enumerate(df_picks.iterrows(), start=1):
        try:
            m_pp = re.search(r"([\d.]+)", str(r["pullback_zone"]))
            zone = f"₹{float(m_pp.group(1)):,.2f}–₹{float(r['entry_trigger']):,.2f}" if m_pp else "—"
        except Exception:
            zone = "—"
        filing = str(r.get("latest_filing") or "")[:120]
        lines += [
            f"### {rank}. {r['symbol']} · score {float(r.get('master_score') or 0):.0f}",
            f"- Entry ₹{float(r['entry_trigger']):,.2f} (pullback zone {zone}), max chase ₹{float(r['max_chase_price']):,.2f}",
            f"- Stop ₹{float(r['stop_loss']):,.2f} ({r.get('risk_pct', '—')}% risk) · T1 ₹{float(r['target_1']):,.2f} · T2 ₹{float(r['target_2']):,.2f}",
        ]
        if filing and not filing.startswith("No recent"):
            lines.append(f"- Latest filing: {filing}")
        lines.append("")
    lines += ["*Stops are on a daily-close basis. Book 30% at T1 and trail the rest on the 65-day EMA.*"]
    return "\n".join(lines)

def parse_query_intent(user_query: str, default_top_n: int = 5) -> tuple[str, int, float | None]:
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

    price_match = re.search(
        r"(?:under|below|less than|<)\s*(?:rs\.?|inr|₹|\?)?\s*(\d+(?:\.\d+)?)",
        q_lower,
    )
    max_price = float(price_match.group(1)) if price_match else None
    return mode, top_n, max_price


def parse_user_intent_and_run(user_query: str, llm: LLMRouter, default_top_n: int = 5) -> tuple[pd.DataFrame, str]:
    """
    Detects whether user asked for Master Scan, Mode A, Mode B, or a specific ticker,
    retrieves the exact quantitative table, and generates the AI Analyst response.
    """
    mode, top_n, max_price = parse_query_intent(user_query, default_top_n)

    df_picks = get_top_candidates_df(mode=mode, top_n=top_n, max_price=max_price)
    if df_picks.empty:
        if max_price is not None:
            label = f"Mode {mode}" if mode in ("A", "B") else "Master"
            return pd.DataFrame(), (
                f"No {label} candidates under ₹{max_price:,.2f} on the latest score date. "
                "Try a higher cap or run an EOD sync."
            )
        return pd.DataFrame(), "No scored data found in local DuckDB yet. Run an EOD sync first."

    payload_records = df_picks.to_dict(orient="records")
    user_payload = (
        f"User Query: {user_query}\n"
        f"Selected Scan Mode: {mode} | Requested Top N: {top_n}\n"
        f"Pre-Computed Quantitative Candidates & Trade Architect Levels:\n{payload_records}"
    )
    ai_answer = llm.generate(SYSTEM_ANALYST_PROMPT, user_payload, temperature=0.2)
    if isinstance(ai_answer, str) and ai_answer.startswith("⚠️ LLM API Error"):
        ai_answer = build_fallback_trade_plan(df_picks, mode=mode, top_n=top_n, max_price=max_price)
    return df_picks, ai_answer
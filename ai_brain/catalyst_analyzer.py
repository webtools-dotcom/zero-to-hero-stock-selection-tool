import json
import time
import pandas as pd
from data_engine.db_manager import get_connection
from ai_brain.llm_router import LLMRouter
from ai_brain.prompts import CATALYST_SCORER_PROMPT

ORDER_KEYWORDS = [
    "order", "letter of award", "loa", "bagged", "contract", "work order",
    "ntpc", "railways", "defence", "data center",
]
EXPANSION_KEYWORDS = [
    "capacity expansion", "commercial production", "commissioned",
    "joint venture", "acquisition", "debt reduction", "preferential", "warrant",
]
RED_FLAG_KEYWORDS = [
    "rights issue", "qip", "resignation of auditor", "default",
    "forensic", "insolvency", "show cause",
]


def deterministic_catalyst_score(text: str) -> float:
    """
    Fast keyword scorer applied to every filing at sync time (base ai_catalyst_score):
      +16.0 order wins / contracts, +14.0 expansion / turnaround, -18.0 dilution / red flags.
    `score_unprocessed_filings` later refines the top-scoring candidates with the LLM.
    """
    t = (text or "").lower()
    if not t:
        return 0.0
    score = 0.0
    if any(k in t for k in ORDER_KEYWORDS):
        score += 16.0
    if any(k in t for k in EXPANSION_KEYWORDS):
        score += 14.0
    if any(k in t for k in RED_FLAG_KEYWORDS):
        score -= 18.0
    if score == 0.0 and len(t) > 40:
        score = 1.0
    return score


def score_unprocessed_filings(llm: LLMRouter, limit: int = 40):
    con = get_connection()
    df = con.execute("""
        SELECT f.filing_id, f.symbol, f.category, f.body_text, i.market_cap_cr,
               COALESCE(f.ai_catalyst_score, 0.0) AS base_score
        FROM corporate_filings f
        LEFT JOIN instruments i ON i.isin = f.isin
        WHERE f.ai_summary = ''
        ORDER BY base_score DESC, f.filing_datetime DESC
        LIMIT ?
    """, [limit]).df()

    for _, row in df.iterrows():
        time.sleep(4.0)
        try:
            mcap_val = float(row["market_cap_cr"]) if pd.notna(row["market_cap_cr"]) else 0.0
            payload = (
                f"Symbol: {row['symbol']} | Market Cap: ₹{mcap_val:.1f} Cr | Category: {row['category']} | "
                f"Keyword base score: {row['base_score']:.0f}\nFiling: {row['body_text']}"
            )
            raw = llm.generate(CATALYST_SCORER_PROMPT, payload, temperature=0.1)
            try:
                clean = raw.strip().removeprefix("```json").removesuffix("```").strip()
                parsed = json.loads(clean)
                score = float(parsed.get("score", row["base_score"]))
                summary = str(parsed.get("summary", row["category"]))
            except Exception:
                # LLM returned unparseable text or hit the API rate limit: keep the filing
                # retryable (empty summary) with its deterministic base score intact.
                score = float(row["base_score"])
                summary = ""
        except Exception:
            score = float(row["base_score"])
            summary = ""

        con.execute("""
            UPDATE corporate_filings
            SET ai_catalyst_score = ?, ai_summary = ?
            WHERE filing_id = ?
        """, [score, summary, row["filing_id"]])
    con.close()

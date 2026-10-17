import json
from data_engine.db_manager import get_connection
from ai_brain.llm_router import LLMRouter
from ai_brain.prompts import CATALYST_SCORER_PROMPT

def score_unprocessed_filings(llm: LLMRouter, limit: int = 30):
    con = get_connection()
    df = con.execute("""
        SELECT f.filing_id, f.symbol, f.category, f.body_text, i.market_cap_cr
        FROM corporate_filings f
        LEFT JOIN instruments i ON i.isin = f.isin
        WHERE f.ai_summary = ''
        ORDER BY f.filing_datetime DESC
        LIMIT ?
    """, [limit]).df()

    for _, row in df.iterrows():
        payload = f"Symbol: {row['symbol']} | Market Cap: ₹{row['market_cap_cr']:.1f} Cr | Category: {row['category']}\nFiling: {row['body_text']}"
        raw = llm.generate(CATALYST_SCORER_PROMPT, payload, temperature=0.1)
        try:
            clean = raw.strip().removeprefix("```json").removesuffix("```").strip()
            parsed = json.loads(clean)
            score = float(parsed.get("score", 0.0))
            summary = str(parsed.get("summary", row["category"]))
        except Exception:
            score = 2.0
            summary = str(row["body_text"])[:140]

        con.execute("""
            UPDATE corporate_filings
            SET ai_catalyst_score = ?, ai_summary = ?
            WHERE filing_id = ?
        """, [score, summary, row["filing_id"]])
    con.close()
import argparse
import numpy as np
import pandas as pd
from data_engine.db_manager import get_connection
from quant_engine.feature_factory import compute_and_store_daily_scores
from ai_brain.agent_tools import get_top_candidates_df

def run_time_machine_validation(as_of_date: str, mode: str = "A", top_n: int = 10) -> pd.DataFrame:
    """
    Runs Mode A, Mode B, or Master Scan strictly as of `as_of_date` (zero look-ahead bias)
    and evaluates actual forward 30d, 90d, Max Peak Multibagger Return, and Trailing Stop Return.
    """
    compute_and_store_daily_scores(as_of_date)
    picks = get_top_candidates_df(mode=mode, top_n=top_n, trade_date=as_of_date)
    if picks.empty:
        return pd.DataFrame()

    con = get_connection()
    results = []
    for idx, row in picks.iterrows():
        fwd = con.execute("""
            SELECT trade_date, open, high, low, close
            FROM daily_market
            WHERE isin = ? AND trade_date > CAST(? AS DATE)
            ORDER BY trade_date ASC
            LIMIT 252
        """, [row["isin"], as_of_date]).df()

        if fwd.empty:
            continue

        entry_px = float(fwd.iloc[0]["open"])
        ret_30d = ((fwd.iloc[min(20, len(fwd)-1)]["close"] - entry_px) / entry_px) * 100.0
        ret_90d = ((fwd.iloc[min(62, len(fwd)-1)]["close"] - entry_px) / entry_px) * 100.0
        max_peak_px = float(fwd["high"].max())
        max_multibagger_ret = ((max_peak_px - entry_px) / entry_px) * 100.0

        # Simulate 30% booked at 2.5R + 70% riding Daily 50-EMA
        fwd["ema_50"] = fwd["close"].ewm(span=50, adjust=False).mean()
        below_ema50 = fwd.iloc[15:][fwd.iloc[15:]["close"] < fwd.iloc[15:]["ema_50"]]
        runner_exit_px = float(below_ema50.iloc[0]["close"]) if not below_ema50.empty else float(fwd.iloc[-1]["close"])
        runner_ret = ((runner_exit_px - entry_px) / entry_px) * 100.0

        results.append({
            "Rank": idx + 1,
            "Symbol": row["symbol"],
            "Mode": row["primary_mode"],
            "Score": row["mode_a_score"] if mode == "A" else (row["mode_b_score"] if mode == "B" else row["master_score"]),
            "Entry_Date": str(fwd.iloc[0]["trade_date"]),
            "Entry_Price": round(entry_px, 2),
            "Return_30D_%": round(ret_30d, 2),
            "Return_90D_%": round(ret_90d, 2),
            "Max_Peak_Return_%": round(max_multibagger_ret, 2),
            "Trailing_Runner_Return_%": round(runner_ret, 2)
        })
    con.close()
    return pd.DataFrame(results)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AlphaSniper Point-in-Time Time Machine Backtester")
    parser.add_argument("--date", type=str, required=True, help="Historical test date YYYY-MM-DD")
    parser.add_argument("--mode", type=str, default="A", choices=["A", "B", "MASTER"])
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    df_res = run_time_machine_validation(args.date, args.mode, args.top)
    print(f"\n=== TIME MACHINE RESULTS AS OF {args.date} (MODE: {args.mode}) ===")
    print(df_res.to_string(index=False))
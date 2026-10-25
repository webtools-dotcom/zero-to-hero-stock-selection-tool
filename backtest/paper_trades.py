"""
Forward paper-trading log.

After each EOD sync the day's top picks per mode are frozen into `paper_trades` with their
levels; later syncs fill in what actually happened using the SAME fill + 2-part plan
simulation as the backtester, so live results compare like-for-like with the walk-forward.

    python backtest/paper_trades.py           # update outcomes and print the report
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
from data_engine.db_manager import get_connection, init_db
from backtest.time_machine_test import FILL_WINDOW_SESSIONS, ROUND_TRIP_COST_PCT, evaluate_picks

MODES = {"A": ("mode_a_score", "s.mode_a_eligible"), "B": ("mode_b_score", "s.mode_b_eligible"),
         "MASTER": ("master_score", "(s.mode_a_eligible OR s.mode_b_eligible)")}
LEVEL_COLS = ["isin", "symbol", "primary_mode", "close", "entry_trigger", "max_chase_price",
              "stop_loss", "emergency_intraday_sl", "target_1", "target_2"]


def log_daily_picks(trade_date: str, top_n: int = 10) -> int:
    """Freeze the top `top_n` picks per mode for `trade_date` (pure score order, like the
    backtest). Re-running for the same date keeps the first record."""
    con = get_connection()
    n = 0
    for mode, (col, elig) in MODES.items():
        con.execute(f"""
            INSERT INTO paper_trades (signal_date, mode, rank, score, {", ".join(LEVEL_COLS)})
            SELECT trade_date, ?, ROW_NUMBER() OVER (ORDER BY {col} DESC), {col}, {", ".join("s." + c for c in LEVEL_COLS)}
            FROM (SELECT * FROM daily_quant_scores s
                  WHERE s.trade_date = CAST(? AS DATE) AND {elig} AND s.entry_trigger > 0
                  ORDER BY {col} DESC LIMIT ?) s
            ON CONFLICT (signal_date, mode, isin) DO NOTHING;
        """, [mode, trade_date, top_n])
        n += con.execute("SELECT COUNT(*) FROM paper_trades WHERE signal_date = CAST(? AS DATE) AND mode = ?",
                         [trade_date, mode]).fetchone()[0]
    con.close()
    return n


def classify(r: dict | None) -> dict:
    """Map one evaluate_picks() row to the stored outcome fields."""
    if r is None:                                           # no session after the signal yet
        return {"status": "pending"}
    if str(r.get("Exit_Detail", "")).startswith("No fill"):
        return {"status": "pending" if r["Sessions_After_Signal"] < FILL_WINDOW_SESSIONS else "no_fill",
                "exit_detail": r["Exit_Detail"]}
    held = int(r["Sessions_Held"])
    return {
        "status": "open" if "data end" in r["Exit_Detail"] else "closed",
        "entry_date": r["Entry_Date"], "entry_price": r["Entry_Price"], "sessions_held": held,
        "ret_30d": r["Return_30D_%"] if held >= 21 else None,
        "ret_90d": r["Return_90D_%"] if held >= 63 else None,
        "plan_return_pct": r["Trailing_Runner_Return_%"], "exit_detail": r["Exit_Detail"],
    }


def update_outcomes() -> int:
    """Re-simulate every pending/open paper trade against all data now in daily_market."""
    con = get_connection(read_only=True)
    todo = con.execute("SELECT * FROM paper_trades WHERE status IN ('pending', 'open')").df()
    con.close()
    if todo.empty:
        return 0
    updates = []
    for (signal_date, mode), grp in todo.groupby(["signal_date", "mode"]):
        picks = grp.reset_index(drop=True)
        res = evaluate_picks(picks, str(pd.Timestamp(signal_date).date()), "score")
        by_symbol = {row["Symbol"]: row for row in res.to_dict("records")} if not res.empty else {}
        for p in picks.to_dict("records"):
            updates.append({"signal_date": p["signal_date"], "mode": mode, "isin": p["isin"],
                            **classify(by_symbol.get(p["symbol"]))})
    cols = ["status", "entry_date", "entry_price", "sessions_held", "ret_30d", "ret_90d", "plan_return_pct", "exit_detail"]
    df = pd.DataFrame(updates).reindex(columns=["signal_date", "mode", "isin", *cols])
    df["entry_date"] = pd.to_datetime(df["entry_date"]).dt.date
    con = get_connection()
    con.register("temp_paper", df)
    con.execute(f"""
        UPDATE paper_trades AS p SET {", ".join(f"{c} = t.{c}" for c in cols)}, updated_at = CURRENT_TIMESTAMP
        FROM temp_paper t
        WHERE p.signal_date = t.signal_date AND p.mode = t.mode AND p.isin = t.isin;
    """)
    con.close()
    return len(df)


def report() -> pd.DataFrame:
    con = get_connection(read_only=True)
    df = con.execute("SELECT * FROM paper_trades").df()
    con.close()
    if df.empty:
        return pd.DataFrame()

    def summ(g):
        filled = g[g["status"].isin(["open", "closed"])]
        decided = g[g["status"].isin(["open", "closed", "no_fill"])]
        closed = g[g["status"] == "closed"]
        return pd.Series({
            "signal_days": g["signal_date"].nunique(), "picks": len(g),
            "pending": int((g["status"] == "pending").sum()), "fill_%": len(filled) / len(decided) * 100 if len(decided) else None,
            "open": int((g["status"] == "open").sum()), "closed": len(closed),
            "closed_mean_%": closed["plan_return_pct"].mean(), "closed_win_%": (closed["plan_return_pct"] > 0).mean() * 100 if len(closed) else None,
            "open_mtm_%": filled.loc[filled["status"] == "open", "plan_return_pct"].mean(),
            "ret_30d_%": filled["ret_30d"].mean(), "n_30d": int(filled["ret_30d"].notna().sum()),
            "ret_90d_%": filled["ret_90d"].mean(), "n_90d": int(filled["ret_90d"].notna().sum()),
        })
    return df.groupby("mode").apply(summ, include_groups=False).round(2)


if __name__ == "__main__":
    init_db()
    print(f"Updated {update_outcomes()} open/pending paper trades.")
    out = report()
    if out.empty:
        print("No paper trades logged yet; they are recorded after each EOD sync.")
    else:
        print(f"\n=== LIVE PAPER TRADES (net of {ROUND_TRIP_COST_PCT}% cost per entry) ===")
        print(out.to_string())
        print("\nCompare with the backtest: python backtest/time_machine_test.py --start <date> --end <date> --mode MASTER")

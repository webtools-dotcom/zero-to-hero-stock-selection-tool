import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import argparse
import numpy as np
import pandas as pd
from data_engine.db_manager import get_connection
from quant_engine.feature_factory import score_point_in_time

FILL_WINDOW_SESSIONS = 5     # SL-L buy order stays live for 5 sessions, then is cancelled
ROUND_TRIP_COST_PCT = 0.30   # STT + brokerage + exchange charges + slippage, per entry
MIN_FULL_UNIVERSE = 1000     # sessions with fewer scored stocks = backfilled survivors only

SCORE_COLS = {"A": "mode_a_score", "B": "mode_b_score", "MASTER": "master_score"}


def find_fill(fwd: pd.DataFrame, entry_trigger: float, max_chase: float,
              window: int = FILL_WINDOW_SESSIONS) -> tuple[int, float] | None:
    """
    First session within `window` where the SL-L buy at `entry_trigger` fills.
    Fill price = max(open, trigger). Sessions that open above `max_chase` are skipped
    (the card's SKIP_GAP_UP rule). Returns (session_index, fill_price) or None if never filled.
    """
    for i in range(min(window, len(fwd))):
        op, hi = float(fwd["open"].iloc[i]), float(fwd["high"].iloc[i])
        if op > max_chase:
            continue
        if hi >= entry_trigger:
            return i, max(op, entry_trigger)
    return None


def simulate_two_part_plan(
    fwd: pd.DataFrame,
    entry_px: float,
    stop_loss: float,
    target_1: float,
    entry_trigger: float = None,
    emergency_sl: float = None,
    max_reentries: int = 1,
    cost_pct: float = ROUND_TRIP_COST_PCT,
) -> tuple[float, str]:
    """
    Mirrors the real AlphaSniper institutional 2-part execution plan with operator
    wick-shakeout protection:
      a) The structural stop fires ONLY on a daily closing basis (close <= stop_loss).
         An intraday exit happens only on the -12.5% catastrophe guard
         (low <= emergency_intraday_sl = entry_trigger * 0.875).
      b) On the first session where high >= target_1 (2.5R), book 30% at target_1 and move
         the 70% runner stop to the entry price (breakeven floor). Once the stock closes
         more than 25% above entry, from day 30 onward trail the runner and exit at the
         2nd consecutive daily close below the 65-Day EMA (Weekly 13-EMA).
      c) Wyckoff Spring / Shakeout-and-Reclaim: if the stock is stopped out before
         target_1 and its close reclaims entry_trigger within the next 15 trading
         sessions, one automatic re-entry is taken at entry_trigger and the plan
         replays from there.
    Stopped-out legs accrue at full position size; the surviving leg is blended per the
    2-part plan. `cost_pct` is charged on the first entry and on every re-entry.
    Returns (total_blended_return_pct, exit_detail).
    """
    if entry_trigger is None or not np.isfinite(entry_trigger) or entry_trigger <= 0:
        entry_trigger = entry_px * 1.0025
    if emergency_sl is None or not np.isfinite(emergency_sl) or emergency_sl <= 0:
        emergency_sl = entry_trigger * 0.875
    t1 = max(target_1, entry_px * 1.02)

    entry_basis = float(entry_px)
    prior_leg = -cost_pct
    leg_open = None
    phase = "PRE"
    t1_day = -1
    trail_on = False
    awaiting = False
    stop_day = -1
    reentries_used = 0
    details = []

    for i in range(len(fwd)):
        op = float(fwd["open"].iloc[i])
        hi = float(fwd["high"].iloc[i])
        lo = float(fwd["low"].iloc[i])
        cl = float(fwd["close"].iloc[i])

        if awaiting:
            if cl >= entry_trigger:
                awaiting = False
                entry_basis = float(entry_trigger)
                prior_leg -= cost_pct
                phase = "PRE"
                trail_on = False
                details.append(f"Shakeout-reclaim re-entry at trigger on day {i + 1}")
                continue
            if i - stop_day > 15:
                details.append("No reclaim within 15 sessions")
                leg_open = 0.0
                phase = "DEAD"
                break
            continue

        if phase == "PRE":
            if lo <= emergency_sl:
                exit_px = op if op <= emergency_sl else emergency_sl
                prior_leg += ((exit_px / entry_basis) - 1.0) * 100.0
                details.append(f"Intraday -12.5% catastrophe stop on day {i + 1}")
                if reentries_used < max_reentries:
                    awaiting = True
                    stop_day = i
                    reentries_used += 1
                else:
                    leg_open = 0.0
                    phase = "DEAD"
                    break
                continue
            if cl <= stop_loss:
                prior_leg += ((cl / entry_basis) - 1.0) * 100.0
                details.append(f"Stop-loss exit on day {i + 1} (daily close)")
                if reentries_used < max_reentries:
                    awaiting = True
                    stop_day = i
                    reentries_used += 1
                else:
                    leg_open = 0.0
                    phase = "DEAD"
                    break
                continue
            if hi >= t1:
                t1_day = i
                phase = "POST"

        if phase == "POST":
            if not trail_on and i >= 30 and cl > entry_basis * 1.25:
                trail_on = True
            if not trail_on and i > t1_day:
                if op <= entry_basis:
                    leg_open = (0.30 * ((t1 / entry_basis) - 1.0) + 0.70 * ((op / entry_basis) - 1.0)) * 100.0
                    details.append(f"Gap-down through breakeven floor on day {i + 1}")
                    phase = "DEAD"
                    break
                if lo <= entry_basis:
                    leg_open = 0.30 * ((t1 / entry_basis) - 1.0) * 100.0
                    details.append(f"Breakeven floor exit on 70% runner (day {i + 1})")
                    phase = "DEAD"
                    break
            if trail_on:
                e = float(fwd["ema_65"].iloc[i])
                e0 = float(fwd["ema_65"].iloc[i - 1]) if i > 0 else e
                c0 = float(fwd["close"].iloc[i - 1]) if i > 0 else cl
                if cl < e and c0 < e0:
                    leg_open = (0.30 * ((t1 / entry_basis) - 1.0) + 0.70 * ((cl / entry_basis) - 1.0)) * 100.0
                    details.append(f"EMA-65 double-close trail exit on day {i + 1}")
                    phase = "DEAD"
                    break

    if phase != "DEAD":
        if awaiting:
            details.append("Re-entry window still open at data end")
            return prior_leg, " -> ".join(details) + " | Flat cash at data end"
        end_px = float(fwd["close"].iloc[-1])
        if phase == "POST":
            leg_open = (0.30 * ((t1 / entry_basis) - 1.0) + 0.70 * ((end_px / entry_basis) - 1.0)) * 100.0
            return prior_leg + leg_open, (" -> ".join(details) or "Runner still above trail") + " | Runner open at data end"
        leg_open = ((end_px / entry_basis) - 1.0) * 100.0
        return prior_leg + leg_open, (" -> ".join(details) + " | " if details else "") + "Target-1 never reached at data end"

    total = prior_leg + (leg_open or 0.0)
    return total, " -> ".join(details) if details else "Plan open at data end"


def run_time_machine_validation(as_of_date: str, mode: str = "A", top_n: int = 10) -> pd.DataFrame:
    """
    Runs Mode A, Mode B, or Master Scan strictly as of `as_of_date` (zero look-ahead bias)
    and evaluates actual forward 30d, 90d, Max Peak Multibagger Return, and the blended
    return of the real 2-part execution plan (30% booked at 2.5R, 70% trailed on EMA-65).
    Scores are computed in memory with today's snapshot fundamentals neutralized, and nothing
    is written to the live daily_quant_scores table. A pick only trades if its SL-L trigger
    fills within FILL_WINDOW_SESSIONS; returns are measured from the fill, net of costs.
    """
    mode = mode.upper()
    snap = score_point_in_time(as_of_date, historical=True)
    if snap.empty:
        return pd.DataFrame()
    if len(snap) < MIN_FULL_UNIVERSE:
        print(f"WARNING: only {len(snap)} stocks have data on {as_of_date}. The universe is the "
              "stocks backfilled from today's active list (survivorship bias). Run "
              "`python data_engine/sync_daily.py --days-back N` to load full NSE Bhavcopy history.")

    eligible = {
        "A": snap["mode_a_eligible"],
        "B": snap["mode_b_eligible"],
        "MASTER": snap["mode_a_eligible"] | snap["mode_b_eligible"],
    }[mode]
    score_col = SCORE_COLS[mode]
    picks = snap[eligible].sort_values(score_col, ascending=False).head(top_n).reset_index(drop=True)
    if picks.empty:
        return pd.DataFrame()

    con = get_connection()
    results = []
    as_of = pd.to_datetime(as_of_date).date()
    for idx, row in picks.iterrows():
        hist = con.execute("""
            SELECT trade_date, open, high, low, close
            FROM daily_market
            WHERE isin = ?
            ORDER BY trade_date ASC
        """, [row["isin"]]).df()
        if hist.empty:
            continue
        hist["ema_65"] = hist["close"].ewm(span=65, adjust=False).mean()
        hist["trade_date"] = pd.to_datetime(hist["trade_date"]).dt.date

        fwd_mask = np.array([d > as_of for d in hist["trade_date"]])
        fwd = hist[fwd_mask].reset_index(drop=True).iloc[:260]
        if fwd.empty:
            continue

        entry_trigger_lvl = float(row["entry_trigger"])
        max_chase = float(row["max_chase_price"]) if pd.notna(row.get("max_chase_price")) else np.inf
        base = {
            "Rank": idx + 1,
            "Symbol": row["symbol"],
            "Mode": row["primary_mode"],
            "Score": row[score_col],
            "Entry_Trigger": round(entry_trigger_lvl, 2),
        }
        fill = find_fill(fwd, entry_trigger_lvl, max_chase)
        if fill is None:
            results.append({**base, "Exit_Detail": f"No fill: trigger not hit within {FILL_WINDOW_SESSIONS} sessions"})
            continue
        fill_idx, entry_px = fill
        fwd = fwd.iloc[fill_idx:].reset_index(drop=True)

        stop_loss = float(row["stop_loss"]) if pd.notna(row["stop_loss"]) else round(entry_px * 0.92, 2)
        target_1 = float(row["target_1"]) if pd.notna(row["target_1"]) else round(entry_px * 1.15, 2)
        emergency_lvl = float(row["emergency_intraday_sl"]) if pd.notna(row.get("emergency_intraday_sl")) else None

        ret_30d = ((fwd.iloc[min(20, len(fwd) - 1)]["close"] - entry_px) / entry_px) * 100.0
        ret_90d = ((fwd.iloc[min(62, len(fwd) - 1)]["close"] - entry_px) / entry_px) * 100.0
        max_peak_px = float(fwd["high"].max())
        max_multibagger_ret = ((max_peak_px - entry_px) / entry_px) * 100.0

        plan_ret_pct, plan_detail = simulate_two_part_plan(
            fwd, entry_px, stop_loss, target_1,
            entry_trigger=entry_trigger_lvl, emergency_sl=emergency_lvl,
        )

        results.append({
            **base,
            "Entry_Date": str(fwd.iloc[0]["trade_date"]),
            "Entry_Price": round(entry_px, 2),
            "Stop_Loss": round(stop_loss, 2),
            "Target_1": round(target_1, 2),
            "Return_30D_%": round(ret_30d, 2),
            "Return_90D_%": round(ret_90d, 2),
            "Max_Peak_Return_%": round(max_multibagger_ret, 2),
            "Trailing_Runner_Return_%": round(plan_ret_pct, 2),
            "Exit_Detail": plan_detail
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
    if not df_res.empty and "Trailing_Runner_Return_%" in df_res:
        traded = df_res["Trailing_Runner_Return_%"].dropna()
        print(f"\nFilled {len(traded)}/{len(df_res)} | net plan return mean {traded.mean():.2f}% "
              f"| median {traded.median():.2f}% | win rate {(traded > 0).mean() * 100:.0f}% "
              f"(after {ROUND_TRIP_COST_PCT}% cost per entry)")

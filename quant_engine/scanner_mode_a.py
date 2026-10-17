import numpy as np
import pandas as pd

def score_mode_a(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mode A (0–100 pts): The CUPID / STLTECH Ground-Floor Multibagger & Turnaround Sniper.
    1. Free-Float Delivery Absorption (35 pts)
    2. Turnaround & Operating Leverage Velocity (30 pts)
    3. AI Corporate Filing Catalyst Asymmetry (20 pts)
    4. Stage-1 Dormancy Breakout (15 pts)
    """
    out = df.copy()

    # 1. Free-Float Delivery Absorption (35 pts)
    float_shares = out["public_float_shares"].replace(0, np.nan).fillna(out["volume"] * 25).clip(lower=50000)
    out["float_absorption_10d_pct"] = ((out["deliv_10d_sum"] / float_shares) * 100.0).clip(0.0, 25.0)
    float_pts = np.interp(out["float_absorption_10d_pct"], [1.0, 7.5], [0.0, 20.0])

    out["delivery_spike_mult"] = (out["deliv_5d_mean"] / out["deliv_60d_median"].clip(lower=100)).clip(0.0, 20.0)
    spike_pts = np.interp(out["delivery_spike_mult"], [1.5, 6.0], [0.0, 15.0])
    deliv_total_pts = float_pts + spike_pts

    # 2. Turnaround & Operating Leverage Velocity (30 pts)
    flip_pts = np.where(
        out["loss_to_profit"],
        12.0,
        np.interp(out["pat_yoy_pct"], [15.0, 120.0], [0.0, 10.0])
    )
    opm_pts = np.interp(out["delta_opm"], [0.5, 5.0], [0.0, 12.0])
    ebitda_pts = np.where(out["is_8q_high_ebitda"], 6.0, 0.0)
    out["op_leverage_score"] = np.round(flip_pts + opm_pts + ebitda_pts, 2)

    # 3. AI Catalyst Asymmetry (20 pts)
    out["catalyst_score"] = out["catalyst_raw_score"].clip(-20.0, 20.0)

    # 4. Stage-1 Dormancy Breakout (15 pts)
    tightness_pts = np.interp(out["prior_60d_range_pct"].fillna(0.5), [0.12, 0.40], [8.0, 0.0])
    above_200 = np.where(out["close"] >= out["sma_200"].fillna(0), 4.0, 0.0)
    near_20d_high = np.where(out["close"] >= out["high_20d"] * 0.96, 3.0, 0.0)
    out["dormancy_score"] = np.round(tightness_pts + above_200 + near_20d_high, 2)

    raw_mode_a = deliv_total_pts + out["op_leverage_score"] + out["catalyst_score"] + out["dormancy_score"]
    out["mode_a_score"] = np.where(out["mode_a_eligible"], np.round(raw_mode_a.clip(0.0, 100.0), 2), 0.0)
    return out
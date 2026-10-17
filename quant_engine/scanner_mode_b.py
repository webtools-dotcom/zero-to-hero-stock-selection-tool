import numpy as np
import pandas as pd

def score_mode_b(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mode B (0–100 pts): The HFCL High-Velocity Momentum Compounder.
    1. DVM+ Quality & Earnings Acceleration (30 pts)
    2. Anti-Gravity Relative Strength (25 pts)
    3. Technical Coil & Ignition Trigger (30 pts)
    4. Hot Micro-Sector Sympathy (15 pts)
    """
    out = df.copy()

    # 1. DVM+ Quality & Growth Acceleration (30 pts)
    roce_roe_pts = np.interp(np.maximum(out["roce_pct"], out["roe_pct"]), [10.0, 25.0], [0.0, 10.0])
    debt_cfo_pts = np.interp(out["debt_to_equity"], [0.1, 1.2], [5.0, 0.0]) + np.interp(out["cfo_to_pat_ratio"], [0.5, 1.0], [0.0, 3.0])
    growth_pts = np.interp(out["pat_yoy_pct"], [10.0, 50.0], [0.0, 7.0]) + np.interp(out["sales_yoy_pct"], [10.0, 30.0], [0.0, 5.0])
    out["dvm_quality_score"] = np.round(roce_roe_pts + debt_cfo_pts + growth_pts, 2)

    # 2. Anti-Gravity Relative Strength (25 pts)
    rs_raw = (
        0.50 * out["ret_20d"].fillna(0.0) +
        0.30 * out["ret_60d"].fillna(0.0) +
        0.20 * out["ret_120d"].fillna(0.0)
    )
    out["rs_percentile"] = np.round(rs_raw.rank(pct=True) * 100.0, 2)
    rs_pts = np.interp(out["rs_percentile"], [60.0, 96.0], [0.0, 15.0])
    red_day_pts = np.interp(out["red_day_avg_ret"], [-0.005, 0.015], [0.0, 10.0])
    anti_gravity_total = rs_pts + red_day_pts

    # 3. Technical Coil & Ignition Trigger (30 pts)
    trend_aligned = (out["close"] >= out["ema_21"]) & (out["ema_21"] >= out["ema_50"]) & (out["close"] >= out["sma_200"].fillna(0))
    near_52w = (out["close"] >= out["high_252d"] * 0.85)
    trend_pts = np.where(trend_aligned & near_52w, 10.0, np.where(trend_aligned, 5.0, 0.0))

    vcp_ratio = (out["atr_5"] / out["atr_20"].clip(lower=0.01)).fillna(1.0)
    vcp_pts = np.interp(vcp_ratio, [0.55, 0.95], [10.0, 0.0])

    candle_range = (out["high"] - out["low"]).clip(lower=0.01)
    close_pos = (out["close"] - out["low"]) / candle_range
    pocket_pivot = (out["volume"] > out["max_down_vol_10d"]) & (close_pos >= 0.65)
    pp_pts = np.where(pocket_pivot, 10.0, np.interp(close_pos, [0.5, 0.9], [0.0, 4.0]))
    out["vcp_coil_score"] = np.round(trend_pts + vcp_pts + pp_pts, 2)

    # 4. Hot Micro-Sector Sympathy (15 pts)
    sector_mom = out.groupby("sub_industry")["ret_20d"].transform("mean").fillna(0.0)
    sector_rank = sector_mom.rank(pct=True) * 100.0
    out["sector_sympathy_score"] = np.round(np.interp(sector_rank, [50.0, 92.0], [0.0, 15.0]), 2)

    raw_mode_b = out["dvm_quality_score"] + anti_gravity_total + out["vcp_coil_score"] + out["sector_sympathy_score"]
    out["mode_b_score"] = np.where(out["mode_b_eligible"], np.round(raw_mode_b.clip(0.0, 100.0), 2), 0.0)
    return out
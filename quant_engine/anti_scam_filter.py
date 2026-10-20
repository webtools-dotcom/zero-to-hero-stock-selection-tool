import pandas as pd
from config import (
    MODE_A_MIN_60D_TURNOVER_CR,
    MODE_A_MIN_3D_TURNOVER_CR,
    MODE_B_MIN_20D_TURNOVER_CR,
    MAX_CIRCUIT_DAYS_IN_20D,
    MAX_PROMOTER_PLEDGE_PCT
)

def apply_anti_scam_and_liquidity_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Takes a cross-sectional DataFrame on `as_of_date` and adds boolean columns:
    `is_safe_from_scam`, `mode_a_eligible`, and `mode_b_eligible`.
    """
    out = df.copy()

    # 1. Anti-Circuit Trap: Reject if >10 of last 20 trading sessions had High == Low
    circuit_ok = out["circuit_days_20d"] <= MAX_CIRCUIT_DAYS_IN_20D

    # 2. GSM Surveillance Filter
    gsm_ok = ~out["asm_gsm_stage"].astype(str).str.contains("GSM Stage II|GSM Stage III|GSM Stage IV", case=False, na=False)

    # 3. Promoter Pledge Filter (Allow high pledge ONLY if pledge is actively dropping QoQ)
    pledge_ok = (out["pledge_pct"] <= MAX_PROMOTER_PLEDGE_PCT) | (out["pledge_change_qoq"] < -2.0)

    out["is_safe_from_scam"] = circuit_ok & gsm_ok & pledge_ok

    # 4. Mode A Ignition Liquidity Rule (Catches ₹2 to ₹5000+ stocks waking up)
    out["mode_a_eligible"] = (
        out["is_safe_from_scam"] &
        (out["median_turnover_60d_cr"] >= MODE_A_MIN_60D_TURNOVER_CR) &
        (out["mean_turnover_3d_cr"] >= MODE_A_MIN_3D_TURNOVER_CR)
    )

    # 5. Mode B Liquid Momentum Compounder Rule
    out["mode_b_eligible"] = (
        out["is_safe_from_scam"] &
        (out["median_turnover_20d_cr"] >= MODE_B_MIN_20D_TURNOVER_CR)
    )

    return out
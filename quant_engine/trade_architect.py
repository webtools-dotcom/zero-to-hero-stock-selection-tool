import numpy as np
import pandas as pd

def compute_trade_levels_vectorized(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deterministically computes Entry Trigger, Pullback Zone, Max Chase Price,
    Structural Stop-Loss, Target 1 (2.5R Free-Ride), Target 2 (5R Swing),
    and Multibagger Trailing Stop (Daily 50-EMA) for every candidate.
    """
    out = df.copy()
    close = out["close"].clip(lower=0.05)
    atr = out["atr_14"].fillna(close * 0.035).clip(lower=close * 0.01)

    pivot_high = np.maximum(out["high"], out["high_10d_p85"])
    out["entry_trigger"] = np.round(pivot_high * 1.0025, 2)

    ema10_low = np.round(np.minimum(out["ema_10"], close), 2)
    out["pullback_zone"] = "₹" + ema10_low.astype(str) + " – ₹" + out["entry_trigger"].astype(str)
    out["max_chase_price"] = np.round(out["entry_trigger"] + (1.2 * atr), 2)

    # Institutional stop calibration: volatile small-caps (< ₹5,000 Cr) tolerate up to 10%
    # risk (2.2 x ATR below the 5-day low) to survive operator wick shakeouts; everyone else
    # stays at 9% (1.8 x ATR). A -12.5% intraday catastrophe guard sits below entry always.
    small_caps = (out["market_cap_cr"].fillna(0.0) < 5000.0).to_numpy()
    atr_mult = np.where(small_caps, 2.2, 1.8)
    sl_cap = np.where(small_caps, 0.10, 0.09)
    raw_sl = np.minimum(out["low_5d_min"], close - (atr_mult * atr))
    sl_pct = ((out["entry_trigger"] - raw_sl) / out["entry_trigger"]).clip(lower=0.04)
    sl_pct = np.minimum(sl_pct, sl_cap)
    out["stop_loss"] = np.round(out["entry_trigger"] * (1.0 - sl_pct), 2)
    out["risk_pct"] = np.round(sl_pct * 100.0, 2)
    out["emergency_intraday_sl"] = np.round(out["entry_trigger"] * 0.875, 2)

    risk_per_share = out["entry_trigger"] - out["stop_loss"]
    out["target_1"] = np.round(out["entry_trigger"] + (2.5 * risk_per_share), 2)
    out["target_2"] = np.round(out["entry_trigger"] + (5.0 * risk_per_share), 2)
    out["trailing_sl_ema50"] = np.round(out["ema_50"], 2)
    out["runner_trail_ema65"] = np.round(out["ema_65"], 2)

    return out
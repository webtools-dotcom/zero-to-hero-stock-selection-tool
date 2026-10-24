import numpy as np
import pandas as pd

def compute_master_ranking(df: pd.DataFrame) -> pd.DataFrame:
    """
    Combines Mode A and Mode B into a unified Master Conviction Score.
    Allows all top N picks to come from a single mode if that mode dominates,
    while rewarding stocks that score strongly on both turnaround & momentum.
    """
    out = df.copy()
    max_s = np.maximum(out["mode_a_score"], out["mode_b_score"])
    min_s = np.minimum(out["mode_a_score"], out["mode_b_score"])
    out["master_score"] = np.round((max_s + 0.20 * min_s).clip(0.0, 100.0), 2)
    out["primary_mode"] = np.where(
        out["mode_a_score"] >= out["mode_b_score"],
        "Mode A: Earnings-Growth Sniper",
        "Mode B: Momentum Compounder"
    )
    return out
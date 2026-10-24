"""Rank IC of each score component vs forward 90-day return, inside its mode's eligible universe."""
import sys, contextlib, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from quant_engine.feature_factory import score_point_in_time
from data_engine.db_manager import get_connection

COMPONENTS = {  # component -> universe it is scored in
    "float_absorption_10d_pct": "A", "delivery_spike_mult": "A", "op_leverage_score": "A",
    "loss_to_profit": "A", "pat_yoy_pct": "A", "delta_opm": "A", "catalyst_score": "A", "dormancy_score": "A",
    "mode_a_score": "A",
    "dvm_quality_score": "B", "rs_percentile": "B", "red_day_avg_ret": "B", "vcp_coil_score": "B",
    "sector_sympathy_score": "B", "mode_b_score": "B",
}
dates = [d.strftime("%Y-%m-%d") for d in pd.date_range("2025-06-30", "2026-07-20", freq="W-MON")]

c = get_connection(read_only=True)
m = c.execute("select isin, trade_date, open, close from daily_market where trade_date >= '2025-05-01' order by isin, trade_date").df()
c.close()
m["trade_date"] = pd.to_datetime(m["trade_date"])
g = m.groupby("isin")
m["fwd90"] = ((g["close"].shift(-63) / g["open"].shift(-1) - 1) * 100).clip(-95, 500)

rows, snaps = [], []
for d in dates:
    with contextlib.redirect_stdout(io.StringIO()):
        snap = score_point_in_time(d, historical=True)
    if snap.empty:
        continue
    fwd = m[m["trade_date"] == pd.Timestamp(snap["trade_date"].iloc[0])][["isin", "fwd90"]]
    s = snap.merge(fwd, on="isin").dropna(subset=["fwd90"])
    s["loss_to_profit"] = s["loss_to_profit"].astype(float)
    snaps.append(s[["isin", "mode_a_eligible", "mode_b_eligible", "fwd90", *COMPONENTS]].assign(date=d))
    for comp, uni in COMPONENTS.items():
        e = s[s[f"mode_{uni.lower()}_eligible"]].dropna(subset=[comp])
        cov = len(e) / max(int(s[f"mode_{uni.lower()}_eligible"].sum()), 1)
        ic = e[comp].corr(e["fwd90"], method="spearman") if e[comp].nunique() > 1 and len(e) >= 50 else np.nan
        hi = e[e[comp] >= e[comp].quantile(0.9)]["fwd90"].mean() - e["fwd90"].mean() if len(e) >= 50 else np.nan
        rows.append({"date": d, "component": comp, "universe": uni, "ic": ic, "top10pct_excess": hi,
                     "coverage": cov, "distinct": e[comp].nunique()})
    print(d, flush=True)
pd.DataFrame(rows).to_csv(sys.argv[1], index=False)
pd.concat(snaps).to_csv(sys.argv[1].replace(".csv", "_snaps.csv"), index=False)  # cache for follow-ups

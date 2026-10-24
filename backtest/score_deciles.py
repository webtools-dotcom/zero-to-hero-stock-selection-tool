"""Score-decile test: does a higher score mean a higher forward 90-day return?"""
import sys, contextlib, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from quant_engine.feature_factory import score_point_in_time
from data_engine.db_manager import get_connection

MODES = {"A": ("mode_a_score", "mode_a_eligible"), "B": ("mode_b_score", "mode_b_eligible"), "MASTER": ("master_score", None)}
dates = [d.strftime("%Y-%m-%d") for d in pd.date_range("2025-06-30", "2026-07-20", freq="W-MON")]

c = get_connection(read_only=True)
m = c.execute("select isin, trade_date, open, close from daily_market where trade_date >= '2025-05-01' order by isin, trade_date").df()
c.close()
m["trade_date"] = pd.to_datetime(m["trade_date"])
g = m.groupby("isin")
m["fwd90"] = (g["close"].shift(-63) / g["open"].shift(-1) - 1) * 100   # next open -> ~90d close
m["fwd90"] = m["fwd90"].clip(-95, 500)                                  # guard split/bonus artifacts

rows = []
for d in dates:
    with contextlib.redirect_stdout(io.StringIO()):
        snap = score_point_in_time(d, historical=True)
    if snap.empty:
        continue
    snap_date = pd.Timestamp(snap["trade_date"].iloc[0])
    fwd = m[m["trade_date"] == snap_date][["isin", "fwd90"]]
    s = snap.merge(fwd, on="isin", how="inner").dropna(subset=["fwd90"])
    for mode, (col, elig) in MODES.items():
        e = s[s[elig]] if elig else s[s["mode_a_eligible"] | s["mode_b_eligible"]]
        if len(e) < 100:
            continue
        e = e.assign(decile=pd.qcut(e[col].rank(method="first"), 10, labels=range(1, 11)).astype(int))
        e["excess"] = e["fwd90"] - e["fwd90"].mean()
        ic = e[col].corr(e["fwd90"], method="spearman")
        for dec, grp in e.groupby("decile"):
            rows.append({"date": d, "mode": mode, "decile": dec, "n": len(grp), "excess": grp["excess"].mean(),
                         "median_ret": grp["fwd90"].median(), "ic": ic})
    print(d, flush=True)
pd.DataFrame(rows).to_csv(sys.argv[1], index=False)

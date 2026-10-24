import sys, numpy as np, pandas as pd
df = pd.read_csv(sys.argv[1])
h1 = df["date"] < "2026-01-01"
def summ(x):
    ic = x["ic"].dropna()
    return pd.Series({"dates": len(ic), "IC": ic.mean(), "IC_H1": x.loc[h1[x.index], "ic"].mean(),
                      "IC_H2": x.loc[~h1[x.index], "ic"].mean(), "pos%": (ic > 0).mean() * 100 if len(ic) else np.nan,
                      "top10%_excess": x["top10pct_excess"].mean(), "coverage%": x["coverage"].mean() * 100,
                      "distinct": x["distinct"].median()})
out = df.groupby(["universe", "component"]).apply(summ, include_groups=False).round(3)
print(out.sort_values(["universe", "IC"], ascending=[True, False]).to_string())

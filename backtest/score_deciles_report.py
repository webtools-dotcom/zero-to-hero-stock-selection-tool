import sys, numpy as np, pandas as pd
df = pd.read_csv(sys.argv[1])
df["half"] = np.where(df["date"] < "2026-01-01", "H1", "H2")
for mode in ["A", "B", "MASTER"]:
    d = df[df["mode"] == mode]
    print(f"===== MODE {mode}: avg stocks/date {d.groupby('date')['n'].sum().mean():.0f}, dates {d['date'].nunique()}")
    t = d.pivot_table(index="decile", columns="half", values="excess", aggfunc="mean")
    t["ALL"] = d.groupby("decile")["excess"].mean()
    t["median_ret"] = d.groupby("decile")["median_ret"].mean()
    print("Mean 90D excess return vs the eligible average, by score decile (10 = highest score):")
    print(t.round(2).to_string())
    spread = d[d.decile == 10].set_index("date")["excess"] - d[d.decile == 1].set_index("date")["excess"]
    ic = d.drop_duplicates("date").set_index("date")["ic"]
    tstat = ic.mean() / (ic.std() / np.sqrt(len(ic)))
    print(f"D10 - D1 spread: {spread.mean():.2f}%  (D10 beat D1 on {(spread > 0).mean() * 100:.0f}% of dates)")
    print(f"Rank IC: mean {ic.mean():.3f} | H1 {ic[ic.index < '2026-01-01'].mean():.3f} | H2 {ic[ic.index >= '2026-01-01'].mean():.3f} | "
          f"positive {(ic > 0).mean() * 100:.0f}% of dates | naive t {tstat:.1f} (overlapping 90d windows, real t ~1/3 of this)\n")

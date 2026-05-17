"""Phase 1.5 — Journal × year trend: heatmap + stacked bar."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from collections import Counter
from _common import parse_and_load, get

ctx = parse_and_load()
rows, idx = ctx["rows"], ctx["idx"]
out_dir = ctx["base_dir"] / "1_profiling"; out_dir.mkdir(parents=True, exist_ok=True)

yj = []
for r in rows:
    y = get(r, idx, "year")
    try: yr = int(str(y)[:4])
    except: continue
    j = (get(r, idx, "journal") or "Unknown").strip()
    yj.append((yr, j))

all_j = Counter(j for _, j in yj)
top12 = [j for j, _ in all_j.most_common(12)]
top6 = top12[:6]
years = sorted({y for y, _ in yj})
mat = {j: {y: 0 for y in years} for j in top12}
for y, j in yj:
    if j in mat: mat[j][y] += 1

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
data = np.array([[mat[j][y] for y in years] for j in top12])
im = ax1.imshow(data, cmap="YlOrRd", aspect="auto")
ax1.set_xticks(range(len(years))); ax1.set_xticklabels(years, fontsize=9)
ax1.set_yticks(range(len(top12))); ax1.set_yticklabels([j[:45] for j in top12], fontsize=9)
ax1.set_title("1.5a Journal × Year heatmap", fontsize=13, fontweight="bold")
for i in range(len(top12)):
    for k in range(len(years)):
        v = data[i, k]
        if v > 0:
            tc = "white" if v > data.max()*0.5 else "black"
            ax1.text(k, i, str(v), ha="center", va="center", fontsize=8, color=tc, fontweight="bold")
fig.colorbar(im, ax=ax1, shrink=0.8)

palette = ["#2196F3", "#FF9800", "#4CAF50", "#9C27B0", "#F44336", "#00BCD4"]
x = np.arange(len(years)); bottom = np.zeros(len(years))
for i, j in enumerate(top6):
    vals = [mat[j][y] for y in years]
    bars = ax2.bar(x, vals, 0.7, bottom=bottom, color=palette[i], label=j[:40],
                   edgecolor="white", linewidth=0.5, alpha=0.9)
    for k, (bar, v) in enumerate(zip(bars, vals)):
        if v >= 3:
            ax2.text(bar.get_x()+bar.get_width()/2, bottom[k]+v/2, str(v),
                     ha="center", va="center", fontsize=8, fontweight="bold", color="white")
    bottom += vals
ax2.set_xticks(x); ax2.set_xticklabels(years, fontsize=10)
ax2.set_xlabel("Year", fontsize=12); ax2.set_ylabel("Paper count", fontsize=12)
ax2.set_title("1.5b Top 6 journals — stacked by year", fontsize=13, fontweight="bold")
ax2.legend(fontsize=8, loc="upper left", framealpha=0.9)

plt.suptitle(f"{ctx['sheet_name']} — Journal × Year Trend", fontsize=15, fontweight="bold", y=1.02)
plt.tight_layout()
fig.savefig(out_dir / "1.5_journal_year_trend.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"[{ctx['sheet_name']}] saved {out_dir / '1.5_journal_year_trend.png'}")

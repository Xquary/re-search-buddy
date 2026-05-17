"""Phase 1.1 — Yearly trend: stacked bar by subset (keyword_hit) or simple bar total."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from collections import Counter
from _common import parse_and_load, get

ctx = parse_and_load()
rows, idx = ctx["rows"], ctx["idx"]
subset_order = ctx["subset_order"]
subset_labels = ctx["subset_labels"]
subset_colors = ctx["subset_colors"]
has_kw = "keyword_hit" in idx
sheet_name = ctx["sheet_name"]
out_dir = ctx["base_dir"] / "1_profiling"
out_dir.mkdir(parents=True, exist_ok=True)

if has_kw and subset_order:
    year_subsets = []
    for r in rows:
        y = get(r, idx, "year")
        try: yr = int(str(y)[:4])
        except: continue
        hits = str(get(r, idx, "keyword_hit", "") or "")
        subs = [s for s in subset_order if s in hits]
        if subs: year_subsets.append((yr, subs[0]))  # primary subset

    years = sorted({y for y, _ in year_subsets})
    counts = {s: {y: 0 for y in years} for s in subset_order}
    for yr, s in year_subsets:
        counts[s][yr] += 1
    year_totals = [sum(counts[s][y] for s in subset_order) for y in years]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    x = np.arange(len(years))
    bottom = np.zeros(len(years))
    for s in subset_order:
        vals = [counts[s][y] for y in years]
        bars = ax1.bar(x, vals, 0.7, bottom=bottom, color=subset_colors[s],
                       label=subset_labels[s], edgecolor="white", linewidth=0.5, alpha=0.9)
        for j, (bar, val) in enumerate(zip(bars, vals)):
            if val >= 2:
                ax1.text(bar.get_x()+bar.get_width()/2, bottom[j]+val/2, str(val),
                         ha="center", va="center", fontsize=11, fontweight="bold", color="white")
        bottom += vals
    for j, tot in enumerate(year_totals):
        ax1.text(j, bottom[j] + bottom.max()*0.02, str(tot), ha="center", va="bottom",
                 fontsize=13, fontweight="bold", color="#37474F")
    ax1.set_xticks(x); ax1.set_xticklabels(years, fontsize=13)
    ax1.set_xlabel("Year", fontsize=14); ax1.set_ylabel("Paper count", fontsize=14)
    ax1.set_title("Yearly trend by subset (absolute)", fontsize=15, fontweight="bold")
    ax1.legend(fontsize=11, loc="upper left", framealpha=0.9)
    ax1.set_ylim(0, bottom.max()*1.18)

    bottom_pct = np.zeros(len(years))
    for s in subset_order:
        vals_pct = np.array([counts[s][y]/year_totals[j]*100 if year_totals[j] > 0 else 0
                             for j, y in enumerate(years)])
        ax2.bar(x, vals_pct, 0.7, bottom=bottom_pct, color=subset_colors[s],
                edgecolor="white", linewidth=0.5, alpha=0.9)
        for j, val in enumerate(vals_pct):
            if val >= 8:
                ax2.text(j, bottom_pct[j]+val/2, f"{val:.0f}%", ha="center", va="center",
                         fontsize=10, fontweight="bold", color="white")
        bottom_pct += vals_pct
    ax2.set_xticks(x); ax2.set_xticklabels(years, fontsize=13)
    ax2.set_xlabel("Year", fontsize=14); ax2.set_ylabel("Share of papers (%)", fontsize=14)
    ax2.set_title("Yearly trend by subset (100% stacked)", fontsize=15, fontweight="bold")
    ax2.set_ylim(0, 105)
else:
    yc = Counter()
    for r in rows:
        y = get(r, idx, "year")
        try: yc[int(str(y)[:4])] += 1
        except: pass
    years = sorted(yc)
    vals = [yc[y] for y in years]
    fig, ax = plt.subplots(figsize=(12, 5))
    bars = ax.bar(range(len(years)), vals, 0.6, color="#546E7A", edgecolor="white", alpha=0.85)
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.3, str(val),
                ha="center", fontsize=13, fontweight="bold")
    ax.set_xticks(range(len(years))); ax.set_xticklabels(years, fontsize=13)
    ax.set_xlabel("Year", fontsize=14); ax.set_ylabel("Paper count", fontsize=14)
    ax.set_title(f"Publications per year (n={sum(vals)})", fontsize=16, fontweight="bold")

plt.suptitle(f"{sheet_name}", fontsize=16, y=1.01)
plt.tight_layout()
fig.savefig(out_dir / "1.1_yearly_trend.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"[{sheet_name}] saved {out_dir / '1.1_yearly_trend.png'}")

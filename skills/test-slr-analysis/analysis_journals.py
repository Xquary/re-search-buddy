"""Phase 1.3 — Journal analysis: coverage + year trend (2×2 panel)."""
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
has_kw = "keyword_hit" in idx
out_dir = ctx["base_dir"] / "1_profiling"; out_dir.mkdir(parents=True, exist_ok=True)

year_journal = []
journal_subsets = []
for r in rows:
    j = (get(r, idx, "journal") or "Unknown").strip()
    y = get(r, idx, "year")
    try: yr = int(str(y)[:4])
    except: continue
    year_journal.append((yr, j))
    if has_kw and subset_order:
        hits = str(get(r, idx, "keyword_hit", "") or "")
        for s in subset_order:
            if s in hits: journal_subsets.append((j, s))

all_journals = Counter(j for _, j in year_journal)
top12 = [j for j, _ in all_journals.most_common(12)]
top6 = top12[:6]
years = sorted({y for y, _ in year_journal})
yr_matrix = {j: {y: 0 for y in years} for j in top12}
for y, j in year_journal:
    if j in yr_matrix: yr_matrix[j][y] += 1

if has_kw and journal_subsets:
    top_journals = [j for j, _ in Counter(j for j, _ in journal_subsets).most_common(20)]
    jmat = {j: {s: 0 for s in subset_order} for j in top_journals}
    for j, s in journal_subsets:
        if j in jmat: jmat[j][s] += 1

fig, axes = plt.subplots(2, 2, figsize=(18, 14))
ax1, ax2, ax3, ax4 = axes[0][0], axes[0][1], axes[1][0], axes[1][1]

# Top-left
if has_kw and journal_subsets:
    data = np.array([[jmat[j][s] for s in subset_order] for j in top_journals])
    im = ax1.imshow(data, cmap="YlOrRd", aspect="auto")
    ax1.set_xticks(range(len(subset_order)))
    ax1.set_xticklabels([subset_labels[s] for s in subset_order], fontsize=11, rotation=20)
    ax1.set_yticks(range(len(top_journals)))
    ax1.set_yticklabels([j[:45] for j in top_journals], fontsize=10)
    ax1.set_title("Journals × subsets", fontsize=14, fontweight="bold")
    for i in range(len(top_journals)):
        for k in range(len(subset_order)):
            v = data[i, k]
            if v > 0:
                tc = "white" if v > data.max()*0.5 else "black"
                ax1.text(k, i, str(v), ha="center", va="center", fontsize=10, color=tc, fontweight="bold")
    fig.colorbar(im, ax=ax1, shrink=0.8)
else:
    top20 = all_journals.most_common(20)
    jl = [j for j, _ in top20]; cs = [c for _, c in top20]
    ax1.barh(range(len(jl)), cs, color="#546E7A", edgecolor="white")
    ax1.set_yticks(range(len(jl))); ax1.set_yticklabels([j[:50] for j in jl], fontsize=10)
    ax1.invert_yaxis(); ax1.set_xlabel("Paper count", fontsize=13)
    ax1.set_title(f"Top 20 journals (n={len(all_journals)})", fontsize=14, fontweight="bold")
    for bar, v in zip(ax1.containers[0], cs):
        ax1.text(bar.get_width()+0.3, bar.get_y()+bar.get_height()/2, str(v), va="center", fontsize=11)

# Top-right: totals across top_journals (with_kw) or year heatmap (no_kw)
if has_kw and journal_subsets:
    totals = [sum(jmat[j].values()) for j in top_journals]
    ax2.barh(range(len(top_journals)), totals, color="#546E7A", edgecolor="white")
    ax2.set_yticks(range(len(top_journals))); ax2.set_yticklabels([j[:45] for j in top_journals], fontsize=10)
    ax2.invert_yaxis(); ax2.set_xlabel("Paper count", fontsize=13)
    ax2.set_title("Top 20 journals (totals)", fontsize=14, fontweight="bold")
else:
    data = np.array([[yr_matrix[j][y] for y in years] for j in top12])
    im = ax2.imshow(data, cmap="YlOrRd", aspect="auto")
    ax2.set_xticks(range(len(years))); ax2.set_xticklabels(years, fontsize=12)
    ax2.set_yticks(range(len(top12))); ax2.set_yticklabels([j[:40] for j in top12], fontsize=10)
    ax2.set_title("Journal × Year heatmap", fontsize=14, fontweight="bold")
    fig.colorbar(im, ax=ax2, shrink=0.8)

# Bottom-left: journal × year heatmap
data = np.array([[yr_matrix[j][y] for y in years] for j in top12])
im = ax3.imshow(data, cmap="YlOrRd", aspect="auto")
ax3.set_xticks(range(len(years))); ax3.set_xticklabels(years, fontsize=12)
ax3.set_yticks(range(len(top12))); ax3.set_yticklabels([j[:40] for j in top12], fontsize=10)
ax3.set_title("Journal × Year heatmap (top 12)", fontsize=14, fontweight="bold")
for i in range(len(top12)):
    for k in range(len(years)):
        v = data[i, k]
        if v > 0:
            tc = "white" if v > data.max()*0.5 else "black"
            ax3.text(k, i, str(v), ha="center", va="center", fontsize=9, color=tc, fontweight="bold")
fig.colorbar(im, ax=ax3, shrink=0.8)

# Bottom-right: top 6 journals stacked by year
palette = ["#2196F3", "#FF9800", "#4CAF50", "#9C27B0", "#F44336", "#00BCD4"]
x = np.arange(len(years)); bottom = np.zeros(len(years))
for i, j in enumerate(top6):
    vals = [yr_matrix[j][y] for y in years]
    bars = ax4.bar(x, vals, 0.7, bottom=bottom, color=palette[i],
                   label=j[:35], edgecolor="white", linewidth=0.5, alpha=0.9)
    for k, (bar, v) in enumerate(zip(bars, vals)):
        if v >= 3:
            ax4.text(bar.get_x()+bar.get_width()/2, bottom[k]+v/2, str(v),
                     ha="center", va="center", fontsize=10, fontweight="bold", color="white")
    bottom += vals
ax4.set_xticks(x); ax4.set_xticklabels(years, fontsize=12)
ax4.set_xlabel("Year", fontsize=13); ax4.set_ylabel("Paper count", fontsize=13)
ax4.set_title("Top 6 journals — yearly composition", fontsize=14, fontweight="bold")
ax4.legend(fontsize=9, loc="upper left", framealpha=0.9)

plt.suptitle(f"{ctx['sheet_name']} — Journal Analysis", fontsize=18, fontweight="bold", y=1.01)
plt.tight_layout()
fig.savefig(out_dir / "1.3_journal_coverage.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"[{ctx['sheet_name']}] saved {out_dir / '1.3_journal_coverage.png'}")

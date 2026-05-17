"""Phase 1.4 — Subset overlap: bar chart + chord diagram (keyword_hit required)."""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.path import Path as MPath
import numpy as np
from collections import Counter
from _common import parse_and_load, get

ctx = parse_and_load()
rows, idx = ctx["rows"], ctx["idx"]
subset_order = ctx["subset_order"]
subset_labels = ctx["subset_labels"]
subset_colors = ctx["subset_colors"]
if "keyword_hit" not in idx or not subset_order:
    print(f"[{ctx['sheet_name']}] no keyword_hit / no topics — skipping subset overlap")
    sys.exit(0)

out_dir = ctx["base_dir"] / "1_profiling"; out_dir.mkdir(parents=True, exist_ok=True)

paper_subsets = []
for r in rows:
    hits = str(get(r, idx, "keyword_hit", "") or "")
    ss = {s for s in subset_order if s in hits}
    paper_subsets.append(ss)

singles, combos, pairwise = {}, Counter(), Counter()
for ss in paper_subsets:
    if not ss: continue
    ss_sorted = sorted(ss)
    for s in ss: singles[s] = singles.get(s, 0) + 1
    combos["+".join(ss_sorted)] += 1
    for i in range(len(ss_sorted)):
        for j in range(i+1, len(ss_sorted)):
            pairwise[(ss_sorted[i], ss_sorted[j])] += 1

exclusive = {s: combos.get(s, 0) for s in subset_order}
overlap = {s: singles.get(s, 0) - exclusive[s] for s in subset_order}
total_papers = sum(1 for ss in paper_subsets if ss)
total_instances = sum(singles.values()) or 1
n = len(subset_order)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8))

x = np.arange(n)
exc = [exclusive[s] for s in subset_order]
ovr = [overlap[s] for s in subset_order]
ax1.bar(x, exc, 0.5, label="Exclusive", color="#37474F", edgecolor="white")
ax1.bar(x, ovr, 0.5, bottom=exc, label="Overlapping", color="#90A4AE", edgecolor="white")
ax1.set_xticks(x)
ax1.set_xticklabels([f"{subset_labels[s]}\n({singles.get(s,0)})" for s in subset_order], fontsize=12)
ax1.set_ylabel("Paper count", fontsize=14)
ax1.set_title(f"Exclusive vs overlapping (n={total_papers})", fontsize=15, fontweight="bold")
ax1.legend(fontsize=12)
for i, t in enumerate([singles.get(s, 0) for s in subset_order]):
    ax1.text(i, t + 0.5, str(t), ha="center", fontsize=12, fontweight="bold")

# Chord
ax2.set_aspect("equal")
gap = 0.04
R_outer, R_inner = 1.0, 0.73
total_angle = 2*np.pi - n*gap*2*np.pi
scale = total_angle / total_instances
arcs, cur = {}, 0.0
for s in subset_order:
    span = singles.get(s, 0) * scale
    arcs[s] = {"start": cur, "span": span, "end": cur + span}
    cur += span + gap*2*np.pi
for s in subset_order:
    a = arcs[s]
    ax2.add_patch(mpatches.Arc((0,0), 2*R_outer, 2*R_outer, angle=0,
                               theta1=np.degrees(a["start"]), theta2=np.degrees(a["end"]),
                               color=subset_colors[s], lw=10, alpha=0.9))
    mid = a["start"] + a["span"]/2
    lx, ly = (R_outer+0.15)*np.cos(mid), (R_outer+0.15)*np.sin(mid)
    ha = "left" if lx > 0.1 else ("right" if lx < -0.1 else "center")
    ax2.text(lx, ly, subset_labels[s], fontsize=12, fontweight="bold", ha=ha, va="center", color=subset_colors[s])

max_ov = max(pairwise.values()) if pairwise else 1
for (src, dst), count in pairwise.items():
    s_ang = arcs[src]["start"] + arcs[src]["span"]/2
    d_ang = arcs[dst]["start"] + arcs[dst]["span"]/2
    mid_ang = (s_ang + d_ang)/2
    diff = abs(d_ang - s_ang)
    if diff > np.pi: diff = 2*np.pi - diff
    cf = 0.45 + 0.1*(diff/np.pi)
    cx, cy = cf*R_inner*np.cos(mid_ang), cf*R_inner*np.sin(mid_ang)
    x1, y1 = R_inner*np.cos(s_ang), R_inner*np.sin(s_ang)
    x2, y2 = R_inner*np.cos(d_ang), R_inner*np.sin(d_ang)
    path = MPath([(x1,y1), (cx,cy), (x2,y2)], [MPath.MOVETO, MPath.CURVE3, MPath.CURVE3])
    w = 0.3 + 2.0*(count/max_ov)
    alpha = 0.2 + 0.5*(count/max_ov)
    ax2.add_patch(mpatches.PathPatch(path, fc="none", ec=subset_colors[src], lw=w, alpha=alpha, zorder=0))

ax2.add_patch(plt.Circle((0,0), R_outer, fill=False, color="#CFD8DC", lw=0.5))
ax2.set_xlim(-1.4, 1.4); ax2.set_ylim(-1.4, 1.4); ax2.axis("off")
ax2.set_title("Subset overlap (chord)", fontsize=15, fontweight="bold", pad=15)

plt.suptitle(f"{ctx['sheet_name']} — Subset Overlap", fontsize=17, fontweight="bold", y=1.02)
plt.tight_layout()
fig.savefig(out_dir / "1.4_subset_overlap.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"[{ctx['sheet_name']}] saved {out_dir / '1.4_subset_overlap.png'}")

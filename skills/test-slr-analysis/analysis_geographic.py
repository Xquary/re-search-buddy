"""Phase 2.3 — Geographic distribution (overall + per-subset if keyword_hit)."""
import re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from collections import Counter
from _common import parse_and_load, get

ctx = parse_and_load()
rows, idx = ctx["rows"], ctx["idx"]
subset_order = ctx["subset_order"]
subset_labels = ctx["subset_labels"]
subset_colors = ctx["subset_colors"]
has_kw = "keyword_hit" in idx and bool(subset_order)
out_dir = ctx["base_dir"] / "2_content"; out_dir.mkdir(parents=True, exist_ok=True)

country_norm = {
    "peoples r china": "China", "peoples republic of china": "China", "pr china": "China",
    "china": "China", "people's republic of china": "China",
    "united states": "USA", "usa": "USA", "united states of america": "USA",
    "united kingdom": "UK", "england": "UK",
    "russian federation": "Russia", "russia": "Russia",
    "south korea": "South Korea", "republic of korea": "South Korea",
    "taiwan": "Taiwan", "hong kong": "Hong Kong",
    "the netherlands": "Netherlands", "netherlands": "Netherlands",
}

def extract_countries(text):
    if not text: return set()
    out = set()
    for unit in re.split(r"[|]", str(text)):
        segs = [s.strip() for s in unit.split(";") if s.strip()]
        if segs:
            raw = segs[-1].strip().rstrip(".")
            out.add(country_norm.get(raw.lower(), raw))
    return out

overall = Counter()
subset_c = {s: Counter() for s in subset_order} if has_kw else None
for r in rows:
    aff = get(r, idx, "affiliations", "") or ""
    dom = "none"
    if has_kw:
        hits = str(get(r, idx, "keyword_hit", "") or "")
        for s in subset_order:
            if s in hits: dom = s; break
    cs = extract_countries(aff) or {"Unknown"}
    for c in cs:
        overall[c] += 1
        if has_kw and dom in subset_c: subset_c[dom][c] += 1

print(f"[{ctx['sheet_name']}] countries={len(overall)}")

if has_kw and subset_c and any(subset_c[s] for s in subset_order):
    n = len(subset_order)
    cols = 2; rows_n = (n + 1) // 2
    fig, axes = plt.subplots(rows_n, cols, figsize=(16, 6 * rows_n))
    axes_flat = axes.flatten() if rows_n > 1 else axes
    for i, s in enumerate(subset_order):
        ax = axes_flat[i]
        top = subset_c[s].most_common(10)
        if not top:
            ax.text(0.5, 0.5, f"{subset_labels[s]} — no data", ha="center", va="center", transform=ax.transAxes)
            ax.axis("off"); continue
        cs = [c for c, _ in top]; counts = [n for _, n in top]
        bars = ax.barh(range(len(cs)), counts, color=subset_colors[s], edgecolor="white", alpha=0.85, height=0.65)
        ax.set_yticks(range(len(cs))); ax.set_yticklabels(cs, fontsize=11); ax.invert_yaxis()
        ax.set_xlabel("Paper count", fontsize=12)
        ax.set_title(f"{subset_labels[s]} (top 10 of {len(subset_c[s])})",
                     fontsize=13, fontweight="bold", color=subset_colors[s])
        for bar, v in zip(bars, counts):
            ax.text(bar.get_width()+0.3, bar.get_y()+bar.get_height()/2, str(v), va="center", fontsize=10, fontweight="bold")
    for j in range(n, len(axes_flat)):
        axes_flat[j].axis("off")
    plt.suptitle(f"{ctx['sheet_name']} — Geographic Distribution", fontsize=17, fontweight="bold", y=1.01)
else:
    fig, ax = plt.subplots(figsize=(10, 6))
    top15 = overall.most_common(15)
    cs = [c for c, _ in top15]; counts = [n for _, n in top15]
    ax.barh(range(len(cs)), counts, color="#546E7A", edgecolor="white", alpha=0.85, height=0.65)
    ax.set_yticks(range(len(cs))); ax.set_yticklabels(cs, fontsize=11); ax.invert_yaxis()
    ax.set_xlabel("Paper count", fontsize=12)
    ax.set_title(f"2.3 Geographic Distribution (n={len(rows)})", fontsize=14, fontweight="bold")
    for bar, v in zip(ax.containers[0], counts):
        ax.text(bar.get_width()+0.3, bar.get_y()+bar.get_height()/2, str(v), va="center", fontsize=11, fontweight="bold")

plt.tight_layout()
fig.savefig(out_dir / "2.3_geographic.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"  saved {out_dir / '2.3_geographic.png'}")

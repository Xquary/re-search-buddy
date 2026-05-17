"""Phase 3.2 — Subset-specific TF-IDF distinctive terms."""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from _common import parse_and_load, get

ctx = parse_and_load()
rows, idx = ctx["rows"], ctx["idx"]
subset_order = ctx["subset_order"]
subset_labels = ctx["subset_labels"]
subset_colors = ctx["subset_colors"]
if "keyword_hit" not in idx or not subset_order:
    print(f"[{ctx['sheet_name']}] no keyword_hit — skipping subset TF-IDF")
    sys.exit(0)
out_dir = ctx["base_dir"] / "3_visuals"; out_dir.mkdir(parents=True, exist_ok=True)

stop = list(ENGLISH_STOP_WORDS) + [
    "model", "based", "using", "used", "paper", "study", "research", "analysis",
    "approach", "results", "also", "can", "one", "two", "may", "proposed",
    "different", "new", "system", "systems", "china", "chinese", "steel", "iron",
    "carbon", "emission", "emissions", "industry"
]

texts, masks = [], {s: [] for s in subset_order}
for r in rows:
    texts.append(f"{get(r, idx, 'title', '')} {get(r, idx, 'abstract', '')} {get(r, idx, 'author_keywords', '')}")
    hits = str(get(r, idx, "keyword_hit", "") or "")
    for s in subset_order:
        masks[s].append(s in hits)

tfidf = TfidfVectorizer(max_features=2000, stop_words=stop, max_df=0.85, min_df=3, ngram_range=(1, 2))
X = tfidf.fit_transform(texts)
terms = tfidf.get_feature_names_out()

n = len(subset_order)
cols = 2; rows_n = (n + 1) // 2
fig, axes = plt.subplots(rows_n, cols, figsize=(16, 6 * rows_n))
axes_flat = axes.flatten() if rows_n > 1 else axes
for i, s in enumerate(subset_order):
    ax = axes_flat[i]
    m = np.array(masks[s])
    if m.sum() == 0:
        ax.text(0.5, 0.5, f"{subset_labels[s]} — no data", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off"); continue
    mean_in = X[m].toarray().mean(axis=0)
    mean_out = X[~m].toarray().mean(axis=0) if (~m).any() else np.zeros_like(mean_in)
    dist = mean_in - mean_out
    top_idx = dist.argsort()[-15:][::-1]
    tnames = [terms[j] for j in top_idx]
    ds = [dist[j] for j in top_idx]
    mi = [mean_in[j] for j in top_idx]
    bars = ax.barh(range(len(tnames)), ds, color=subset_colors[s], edgecolor="white", alpha=0.85, height=0.7)
    for bar, val in zip(bars, mi):
        ax.text(bar.get_width()+0.0005, bar.get_y()+bar.get_height()/2, f"{val:.3f}",
                va="center", fontsize=9, color="#37474F")
    ax.set_yticks(range(len(tnames))); ax.set_yticklabels(tnames, fontsize=10); ax.invert_yaxis()
    ax.set_xlabel("Distinctiveness", fontsize=12)
    ax.set_title(f"{subset_labels[s]} (n={int(m.sum())})", fontsize=13, fontweight="bold", color=subset_colors[s])
    ax.set_xlim(0, max(ds)*1.35 if max(ds) > 0 else 1)

for j in range(n, len(axes_flat)):
    axes_flat[j].axis("off")

plt.suptitle(f"{ctx['sheet_name']} — Subset TF-IDF Distinctive Terms", fontsize=17, fontweight="bold", y=1.01)
plt.tight_layout()
fig.savefig(out_dir / "3.2_subset_tfidf.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"[{ctx['sheet_name']}] saved {out_dir / '3.2_subset_tfidf.png'}")

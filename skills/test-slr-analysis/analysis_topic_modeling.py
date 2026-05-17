"""Phase 2.2 — NMF topic modeling: t-SNE + yearly trend."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.decomposition import NMF
from sklearn.manifold import TSNE
from _common import parse_and_load, get

ctx = parse_and_load()
rows, idx = ctx["rows"], ctx["idx"]
subset_order = ctx["subset_order"]
subset_labels = ctx["subset_labels"]
subset_colors_sub = ctx["subset_colors"]
has_kw = "keyword_hit" in idx and bool(subset_order)
out_dir = ctx["base_dir"] / "2_content"; out_dir.mkdir(parents=True, exist_ok=True)

stop_words = list(ENGLISH_STOP_WORDS) + [
    "model", "based", "using", "used", "paper", "study", "research", "analysis",
    "approach", "results", "also", "can", "one", "two", "may", "proposed",
    "different", "new", "system", "systems", "china", "chinese", "steel", "iron",
    "carbon", "emission", "emissions", "industry"
]

texts, years, dominant_subsets = [], [], []
for r in rows:
    y = get(r, idx, "year")
    try: yr = int(str(y)[:4])
    except: continue
    texts.append(f"{get(r, idx, 'title', '')} {get(r, idx, 'abstract', '')} {get(r, idx, 'author_keywords', '')}")
    years.append(yr)
    dom = "none"
    if has_kw:
        hits = str(get(r, idx, "keyword_hit", "") or "")
        for s in subset_order:
            if s in hits: dom = s; break
    dominant_subsets.append(dom)

print(f"[{ctx['sheet_name']}] docs={len(texts)}")
tfidf = TfidfVectorizer(max_features=2000, stop_words=stop_words, max_df=0.85, min_df=3, ngram_range=(1, 2))
X = tfidf.fit_transform(texts)
terms = tfidf.get_feature_names_out()
n_topics = 6
nmf = NMF(n_components=n_topics, random_state=42, max_iter=500, init="nndsvd")
W = nmf.fit_transform(X); H = nmf.components_
dom_topic = W.argmax(axis=1)
topic_colors = ["#2196F3", "#FF9800", "#4CAF50", "#9C27B0", "#F44336", "#00BCD4"]
topic_labels_text = [", ".join([terms[j] for j in H[i].argsort()[-3:][::-1]]) for i in range(n_topics)]

perp = max(5, min(30, len(texts) - 1))
X_tsne = TSNE(n_components=2, random_state=42, perplexity=perp, init="pca").fit_transform(W)

unique_years = sorted(set(years))
ty = np.zeros((n_topics, len(unique_years)), dtype=int)
for y, t in zip(years, dom_topic):
    ty[t, unique_years.index(y)] += 1
year_totals = ty.sum(axis=0)

if has_kw:
    fig, axes = plt.subplots(2, 2, figsize=(16, 13))
    a00, a01, a10, a11 = axes[0][0], axes[0][1], axes[1][0], axes[1][1]
else:
    fig, (a00, a10) = plt.subplots(1, 2, figsize=(16, 6))
    a01 = a11 = None

# t-SNE by NMF topic
for t in range(n_topics):
    m = dom_topic == t
    a00.scatter(X_tsne[m, 0], X_tsne[m, 1], c=topic_colors[t],
                label=f"T{t+1}: {topic_labels_text[t]}", alpha=0.65, s=25, edgecolors="white", linewidth=0.3)
a00.set_title("2.2a t-SNE by NMF topic", fontsize=14, fontweight="bold")
a00.legend(fontsize=9, loc="lower left")
a00.set_xticks([]); a00.set_yticks([])

# t-SNE by subset
if a01 is not None:
    for s in subset_order:
        m = [d == s for d in dominant_subsets]
        a01.scatter(X_tsne[m, 0], X_tsne[m, 1], c=subset_colors_sub[s],
                    label=subset_labels[s], alpha=0.65, s=25, edgecolors="white", linewidth=0.3)
    a01.set_title("2.2b t-SNE by keyword subset", fontsize=14, fontweight="bold")
    a01.legend(fontsize=10); a01.set_xticks([]); a01.set_yticks([])

# Absolute stacked yearly
x = np.arange(len(unique_years))
bottom = np.zeros(len(unique_years))
for i in range(n_topics):
    vals = ty[i]
    bars = a10.bar(x, vals, 0.7, bottom=bottom, color=topic_colors[i],
                   edgecolor="white", linewidth=0.4, alpha=0.9, label=f"T{i+1}")
    for j, (bar, val) in enumerate(zip(bars, vals)):
        if val >= max(3, len(texts) * 0.02):
            a10.text(bar.get_x()+bar.get_width()/2, bottom[j]+val/2, str(val),
                     ha="center", va="center", fontsize=9, fontweight="bold", color="white")
    bottom += vals
a10.set_xticks(x); a10.set_xticklabels(unique_years, fontsize=11)
a10.set_ylabel("Paper count", fontsize=12)
a10.set_title("2.2c Topic prevalence by year (absolute)", fontsize=14, fontweight="bold")
a10.legend(fontsize=8, loc="upper left", ncol=2)

# 100% stacked
if a11 is not None:
    pct = np.zeros_like(ty, dtype=float)
    for j in range(len(unique_years)):
        if year_totals[j] > 0: pct[:, j] = ty[:, j] / year_totals[j] * 100
    bottom = np.zeros(len(unique_years))
    for i in range(n_topics):
        v = pct[i]
        a11.bar(x, v, 0.7, bottom=bottom, color=topic_colors[i], edgecolor="white", linewidth=0.4, alpha=0.9)
        for j, val in enumerate(v):
            if val >= 10:
                a11.text(j, bottom[j]+val/2, f"{val:.0f}%", ha="center", va="center",
                         fontsize=9, fontweight="bold", color="white")
        bottom += v
    a11.set_xticks(x); a11.set_xticklabels(unique_years, fontsize=11)
    a11.set_ylabel("Share (%)", fontsize=12); a11.set_ylim(0, 105)
    a11.set_title("2.2d Topic prevalence by year (100% stacked)", fontsize=14, fontweight="bold")

plt.suptitle(f"{ctx['sheet_name']} — Topic Modeling", fontsize=17, fontweight="bold", y=1.02)
plt.tight_layout()
fig.savefig(out_dir / "2.2_topic_modeling.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"  saved {out_dir / '2.2_topic_modeling.png'}")

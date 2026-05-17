"""Phase 3.1 — Word clouds: per-subset (keyword_hit) or overall."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from wordcloud import WordCloud, STOPWORDS
from _common import parse_and_load, get

ctx = parse_and_load()
rows, idx = ctx["rows"], ctx["idx"]
subset_order = ctx["subset_order"]
subset_labels = ctx["subset_labels"]
subset_colors = ctx["subset_colors"]
has_kw = "keyword_hit" in idx and bool(subset_order)
out_dir = ctx["base_dir"] / "3_visuals"; out_dir.mkdir(parents=True, exist_ok=True)

extra_stops = set(STOPWORDS) | {
    "model", "based", "using", "used", "paper", "study", "research",
    "analysis", "approach", "results", "also", "can", "one", "two", "may",
    "proposed", "different", "new", "system", "systems", "well", "method",
    "methods", "propose", "use", "however", "therefore", "thus",
    "show", "shown", "find", "found", "given", "due", "include", "including",
    "high", "low", "large", "first", "order", "many", "table", "figure",
    "et", "al", "https", "doi", "org", "available",
    "china", "chinese", "steel", "iron", "carbon", "emission", "emissions", "industry"
}

# distinct hue per topic, in order
hues = [210, 30, 120, 280, 350, 180, 60, 320]
hue_map = {s: hues[i % len(hues)] for i, s in enumerate(subset_order)}

def make_color_func(hue):
    def cf(word, font_size, position, orientation, random_state=None, **kw):
        return f"hsl({hue+np.random.randint(-15,15)},{70+np.random.randint(-10,10)}%,{40+np.random.randint(-10,10)}%)"
    return cf

if has_kw:
    subset_texts = {s: [] for s in subset_order}
    for r in rows:
        combined = f"{get(r, idx, 'title', '')} {get(r, idx, 'abstract', '')} {get(r, idx, 'author_keywords', '')}".strip()
        hits = str(get(r, idx, "keyword_hit", "") or "")
        for s in subset_order:
            if s in hits and combined:
                subset_texts[s].append(combined)

    wcs = {}
    for s in subset_order:
        ts = subset_texts[s]
        if not ts: continue
        blob = " ".join(ts)
        print(f"[{ctx['sheet_name']}] {subset_labels[s]}: {len(ts)} papers")
        wcs[s] = WordCloud(width=500, height=380, background_color="white", stopwords=extra_stops,
                           max_words=50, collocations=False, color_func=make_color_func(hue_map[s]),
                           random_state=42, min_font_size=10, max_font_size=90, prefer_horizontal=0.7).generate(blob)

    n = len(subset_order)
    cols = 2; rows_n = (n + 1) // 2
    fig, axes = plt.subplots(rows_n, cols, figsize=(7*cols, 5*rows_n))
    axes_flat = axes.flatten() if rows_n > 1 else axes
    for i, s in enumerate(subset_order):
        ax = axes_flat[i]
        if s in wcs:
            ax.imshow(wcs[s], interpolation="bilinear")
            ax.set_title(f"{subset_labels[s]} ({len(subset_texts[s])} papers)",
                         fontsize=14, fontweight="bold", color=subset_colors[s], pad=6)
        else:
            ax.text(0.5, 0.5, f"{subset_labels[s]} — no data", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
    for j in range(n, len(axes_flat)):
        axes_flat[j].axis("off")
    plt.suptitle(f"{ctx['sheet_name']} — Word Clouds", fontsize=17, fontweight="bold", y=1.01)
    plt.tight_layout()
    fig.savefig(out_dir / "3.1_wordclouds_by_subset.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  saved {out_dir / '3.1_wordclouds_by_subset.png'}")
else:
    blob = " ".join(
        f"{get(r, idx, 'title', '')} {get(r, idx, 'abstract', '')} {get(r, idx, 'author_keywords', '')}".strip()
        for r in rows
    )
    if blob.strip():
        wc = WordCloud(width=1000, height=700, background_color="white", stopwords=extra_stops,
                       max_words=80, collocations=False, color_func=make_color_func(210),
                       random_state=42, min_font_size=10, max_font_size=150, prefer_horizontal=0.7).generate(blob)
        fig, ax = plt.subplots(figsize=(10, 7))
        ax.imshow(wc, interpolation="bilinear"); ax.axis("off")
        ax.set_title(f"3.1 Overall wordcloud — {ctx['sheet_name']} (n={len(rows)})",
                     fontsize=15, fontweight="bold", pad=10)
        fig.savefig(out_dir / "3.1_wordcloud_overall.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  saved {out_dir / '3.1_wordcloud_overall.png'}")

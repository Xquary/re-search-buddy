"""SLR visualisation charts."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Paper


def _save(fig, path: Path, name: str) -> Path:
    import matplotlib.pyplot as plt
    out = path / name
    fig.savefig(out, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  chart → {out}")
    return out


def plot_publications_per_year(papers: list[Paper], out_dir: Path) -> Path:
    import matplotlib.pyplot as plt

    years = [p.year for p in papers if p.year]
    if not years:
        print("  [charts] no year data — skipping publications_per_year")
        return None

    counts = Counter(years)
    xs = sorted(counts)
    ys = [counts[x] for x in xs]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(xs, ys, color="#2c7bb6", edgecolor="white", linewidth=0.5)
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of papers")
    ax.set_title("Publications per Year")
    ax.set_xticks(xs)
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return _save(fig, out_dir, "publications_per_year.png")


def plot_top_journals(papers: list[Paper], out_dir: Path, top_n: int = 15) -> Path:
    import matplotlib.pyplot as plt

    journals = [p.publication for p in papers if p.publication]
    if not journals:
        print("  [charts] no journal data — skipping top_journals")
        return None

    counts = Counter(journals).most_common(top_n)
    labels = [j for j, _ in counts]
    values = [c for _, c in counts]

    fig, ax = plt.subplots(figsize=(10, max(4, len(labels) * 0.45)))
    bars = ax.barh(range(len(labels)), values, color="#1a9641", edgecolor="white")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Number of papers")
    ax.set_title(f"Top {top_n} Journals")
    ax.bar_label(bars, padding=3, fontsize=8)
    fig.tight_layout()
    return _save(fig, out_dir, "top_journals.png")


def plot_thematic_heatmap(
    papers: list[Paper], out_dir: Path, top_terms: int = 20, year_bin: int = 2
) -> Path:
    """Heatmap of top TF-IDF keywords vs year bins."""
    import matplotlib.pyplot as plt
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer

    # Build per-paper text corpus
    docs = [f"{p.title or ''} {p.abstract or ''}" for p in papers]
    years = [p.year for p in papers]

    valid = [(d, y) for d, y in zip(docs, years) if y and d.strip()]
    if len(valid) < 5:
        print("  [charts] too few papers with year+text — skipping thematic_heatmap")
        return None

    docs_v, years_v = zip(*valid)

    # Extract top TF-IDF terms
    tfidf = TfidfVectorizer(
        stop_words="english", max_features=top_terms, ngram_range=(1, 2),
        min_df=2,
    )
    try:
        tfidf_matrix = tfidf.fit_transform(docs_v)
    except ValueError:
        print("  [charts] not enough vocabulary for heatmap — skipping")
        return None

    terms = tfidf.get_feature_names_out()

    # Build year bins
    min_y, max_y = min(years_v), max(years_v)
    bins = list(range(min_y - (min_y % year_bin), max_y + year_bin + 1, year_bin))
    bin_labels = [f"{b}–{b + year_bin - 1}" for b in bins[:-1]]

    # Aggregate TF-IDF scores per bin
    import numpy as np
    heat = np.zeros((len(terms), len(bin_labels)))
    for i, (row, y) in enumerate(zip(tfidf_matrix, years_v)):
        bin_idx = (y - bins[0]) // year_bin
        if 0 <= bin_idx < len(bin_labels):
            heat[:, bin_idx] += row.toarray()[0]

    # Normalise columns so sparse early years don't dominate
    col_max = heat.max(axis=0, keepdims=True)
    col_max[col_max == 0] = 1
    heat = heat / col_max

    import seaborn as sns
    fig, ax = plt.subplots(figsize=(max(8, len(bin_labels) * 0.9), max(6, len(terms) * 0.4)))
    sns.heatmap(
        heat, ax=ax,
        xticklabels=bin_labels, yticklabels=terms,
        cmap="YlOrRd", linewidths=0.3, linecolor="white",
        cbar_kws={"label": "Normalised TF-IDF"},
    )
    ax.set_title("Thematic Changes Over Time")
    ax.set_xlabel("Year bin")
    ax.set_ylabel("Term")
    ax.tick_params(axis="x", rotation=45)
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    return _save(fig, out_dir, "thematic_heatmap.png")


def plot_score_distribution(papers: list[Paper], out_dir: Path) -> Path:
    import matplotlib.pyplot as plt
    import numpy as np

    scores = [p.score for p in papers if p.score > 0]
    if not scores:
        print("  [charts] no scores — skipping score_distribution")
        return None

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(scores, bins=30, color="#d7191c", edgecolor="white", linewidth=0.5)
    ax.axvline(np.median(scores), color="black", linestyle="--", linewidth=1,
               label=f"median={np.median(scores):.3f}")
    ax.set_xlabel("Cosine similarity score")
    ax.set_ylabel("Count")
    ax.set_title("Score Distribution")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return _save(fig, out_dir, "score_distribution.png")


def generate_all(papers: list[Paper], out_dir: Path, top_n_journals: int = 15) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_publications_per_year(papers, out_dir)
    plot_top_journals(papers, out_dir, top_n=top_n_journals)
    plot_thematic_heatmap(papers, out_dir)
    plot_score_distribution(papers, out_dir)

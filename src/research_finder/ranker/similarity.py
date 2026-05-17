from __future__ import annotations

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from ..models import Paper


def rank_papers(
    text_embedding: np.ndarray,
    paper_embeddings: np.ndarray,
    papers: list[Paper],
    *,
    top_n: int = 10,
    threshold: float = 0.3,
) -> list[Paper]:
    """Score papers by cosine similarity to the input text and return the top-N.

    Sets ``paper.score`` on each paper, then returns the top-N papers whose
    score meets *threshold*, sorted descending.
    """
    # text_embedding: (dim,) or (1, dim)  → ensure 2-D for sklearn
    text_vec = text_embedding.reshape(1, -1)

    # Compute cosine similarity: result shape (1, num_papers)
    scores = cosine_similarity(text_vec, paper_embeddings)[0]

    # Assign scores to paper objects
    for paper, score in zip(papers, scores):
        paper.score = float(score)

    # Sort by score descending, filter by threshold, take top_n
    ranked = sorted(papers, key=lambda p: p.score, reverse=True)
    filtered = [p for p in ranked if p.score >= threshold]

    return filtered[:top_n]

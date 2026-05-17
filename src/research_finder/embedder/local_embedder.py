from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

from .base import BaseEmbedder


class LocalEmbedder(BaseEmbedder):
    """Embeds text using a local sentence-transformers model."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", batch_size: int = 32):
        self.model = SentenceTransformer(model_name)
        self.batch_size = batch_size

    def embed_single(self, text: str) -> np.ndarray:
        embedding = self.model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return embedding.astype(np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        embeddings = self.model.encode(
            texts, batch_size=self.batch_size, convert_to_numpy=True, normalize_embeddings=True
        )
        return embeddings.astype(np.float32)

from __future__ import annotations

from typing import Any

import litellm
import numpy as np

from .base import BaseEmbedder


class ApiEmbedder(BaseEmbedder):
    """Embeds text using an API-based embedding model via LiteLLM."""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dimensions: int | None = None,
        batch_size: int = 32,
    ):
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size

    def _call(self, input: list[str]) -> list[list[float]]:
        """Call the embedding API and return raw embedding vectors."""
        input = [t.replace("\n", " ") for t in input]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": input,
            "encoding_format": "float",
        }
        if self.dimensions is not None:
            kwargs["dimensions"] = self.dimensions
        response = litellm.embedding(**kwargs)
        return [d["embedding"] for d in response.data]

    def embed_single(self, text: str) -> np.ndarray:
        vectors = self._call([text])
        return np.array(vectors[0], dtype=np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        all_embeddings: list[np.ndarray] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_vecs = self._call(batch)
            all_embeddings.append(np.array(batch_vecs, dtype=np.float32))
        if not all_embeddings:
            return np.empty((0, 0), dtype=np.float32)
        return np.vstack(all_embeddings)

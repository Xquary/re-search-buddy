from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class BaseEmbedder(ABC):
    """Abstract base class for text embedders."""

    @abstractmethod
    def embed_single(self, text: str) -> np.ndarray:
        """Embed a single string. Returns a 1-D float32 array."""
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Embed a list of strings. Returns a 2-D float32 array (N, dim)."""
        ...

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Paper


class BaseSearcher(ABC):
    """Abstract base class for paper search backends."""

    name: str = "base"

    @abstractmethod
    def search(self, queries: list[str]) -> list[Paper]:
        """Search for papers using the given queries. Returns deduplicated results."""
        ...

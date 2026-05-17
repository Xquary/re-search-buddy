from __future__ import annotations

from typing import Any

from .base import BaseSearcher
from .arxiv_searcher import ArxivSearcher
from .scholar_searcher import ScholarSearcher
from .cnki_searcher import CnkiSearcher
from .semantic_scholar_searcher import SemanticScholarSearcher
from .scopus_searcher import ScopusSearcher
from .springer_searcher import SpringerSearcher


SEARCHERS: dict[str, type[BaseSearcher]] = {
    "arxiv": ArxivSearcher,
    "scholar": ScholarSearcher,
    "cnki": CnkiSearcher,
    "semantic_scholar": SemanticScholarSearcher,
    "scopus": ScopusSearcher,
    "springer": SpringerSearcher,
}


def get_enabled_searchers(config: dict[str, Any]) -> list[BaseSearcher]:
    """Instantiate searchers for all backends enabled in config."""
    enabled = config.get("search", {}).get("backends", ["arxiv"])
    searchers = []
    for name in enabled:
        cls = SEARCHERS.get(name)
        if cls:
            searchers.append(cls(config))
    return searchers


def register_searcher(name: str, cls: type[BaseSearcher]) -> None:
    """Register a custom searcher at runtime."""
    SEARCHERS[name] = cls

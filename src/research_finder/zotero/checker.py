from __future__ import annotations

import json
from typing import Any

from .client_manager import ZoteroClientManager


class ZoteroChecker:
    """Checks whether papers from other sources already exist in the Zotero library.

    Mutates paper.in_library = True and paper.zotero_key for any match found.
    Skips papers that are already from the "zotero" source (already flagged).
    """

    def __init__(self, config: dict[str, Any], manager: ZoteroClientManager):
        self._manager = manager
        self._threshold: float = (
            config.get("zotero", {}).get("duplicate_title_threshold", 0.85)
        )

    def check_and_flag(self, papers: list[Any]) -> list[Any]:
        """Mutate papers in-place: set in_library and zotero_key where matched."""
        return self._manager.run_async(self._check_async(papers))

    async def _check_async(self, papers: list[Any]) -> list[Any]:
        client = self._manager.client

        for paper in papers:
            if paper.source == "zotero":
                # Already from Zotero — already flagged by ZoteroSearcher
                continue
            if paper.in_library:
                # Already flagged by a previous pass
                continue

            matched_key = await self._find_in_library(client, paper)
            if matched_key:
                paper.in_library = True
                paper.zotero_key = matched_key

        return papers

    async def _find_in_library(self, client, paper: Any) -> str | None:
        # Strategy 1: DOI exact match
        if paper.doi:
            raw = await client.call_tool("zotero_search_items", {
                "query": paper.doi,
                "limit": 3,
            })
            for item in _parse_items(raw):
                item_doi = item.get("DOI") or item.get("doi") or ""
                if item_doi.lower() == paper.doi.lower():
                    return item.get("key")

        # Strategy 2: Title keyword search + fuzzy title comparison
        if paper.title:
            raw = await client.call_tool("zotero_search_items", {
                "query": paper.title,
                "limit": 5,
            })
            for item in _parse_items(raw):
                zotero_title = item.get("title", "").lower().strip()
                paper_title = paper.title.lower().strip()
                if zotero_title and _jaccard(zotero_title, paper_title) >= self._threshold:
                    return item.get("key")

        return None


def _parse_items(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "results", "data"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            return [data]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _jaccard(a: str, b: str) -> float:
    """Token-overlap Jaccard similarity — no extra dependencies needed."""
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)

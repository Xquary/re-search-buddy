from __future__ import annotations

import json
from typing import Any

from ..searcher.base import BaseSearcher
from .client_manager import ZoteroClientManager


class ZoteroSearcher(BaseSearcher):
    """Searches the user's Zotero library as an additional search backend.

    Returns Paper objects with source="zotero", in_library=True, and zotero_key set.
    Uses zotero_search_items for keyword search, and optionally zotero_semantic_search.

    Note: This searcher is NOT registered in searcher/registry.py because it requires
    a ZoteroClientManager argument. The Pipeline injects it directly.
    """

    name = "zotero"

    def __init__(self, config: dict[str, Any], manager: ZoteroClientManager):
        zotero_cfg = config.get("zotero", {})
        self.max_results = zotero_cfg.get("max_results_per_query", 20)
        self.use_semantic = zotero_cfg.get("semantic_search", False)
        self._manager = manager

    def search(self, queries: list[str]) -> list[Any]:
        return self._manager.run_async(self._search_async(queries))

    async def _search_async(self, queries: list[str]) -> list[Any]:
        from ..models import Paper

        client = self._manager.client
        papers: list[Paper] = []
        seen_keys: set[str] = set()

        for query in queries:
            # Primary: keyword search
            raw = await client.call_tool("zotero_search_items", {
                "query": query,
                "limit": self.max_results,
            })
            items = _parse_items(raw)

            # Optional: semantic search (union with keyword results)
            if self.use_semantic:
                raw_sem = await client.call_tool("zotero_semantic_search", {
                    "query": query,
                    "limit": self.max_results,
                })
                existing_keys = {i.get("key") for i in items}
                for item in _parse_items(raw_sem):
                    if item.get("key") not in existing_keys:
                        items.append(item)

            for item in items:
                key = item.get("key", "")
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                papers.append(_item_to_paper(item))

        return papers


def _parse_items(raw: str) -> list[dict]:
    """Parse MCP tool response text into a list of item dicts."""
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


def _item_to_paper(item: dict) -> Any:
    """Map a Zotero item dict to a Paper dataclass."""
    from ..models import Paper

    creators = item.get("creators", [])
    authors = [
        f"{c.get('lastName', '')} {c.get('firstName', '')}".strip()
        for c in creators
        if isinstance(c, dict) and c.get("creatorType") == "author"
    ]

    pub_date = item.get("date", "")
    year: int | None = None
    if pub_date and len(str(pub_date)) >= 4:
        try:
            year = int(str(pub_date)[:4])
        except ValueError:
            pass

    return Paper(
        title=item.get("title", ""),
        abstract=item.get("abstractNote") or item.get("abstract") or None,
        authors=authors,
        url=item.get("url") or None,
        doi=item.get("DOI") or item.get("doi") or None,
        year=year,
        source="zotero",
        zotero_key=item.get("key") or None,
        in_library=True,
    )

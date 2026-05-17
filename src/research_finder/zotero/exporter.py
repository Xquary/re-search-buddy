from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .client_manager import ZoteroClientManager


class ZoteroExporter:
    """Adds ranked papers to the user's Zotero library after the pipeline runs.

    Add priority for each paper:
    1. DOI present  -> zotero_add_by_doi
    2. URL present  -> zotero_add_by_url  (handles arXiv links natively)
    3. Local PDF downloaded by the downloader stage -> zotero_add_from_file
    4. Otherwise    -> skip

    Papers already in_library are skipped to avoid duplicates.
    Sets paper.zotero_key on successful add.
    """

    def __init__(self, config: dict[str, Any], manager: ZoteroClientManager):
        self._manager = manager
        zotero_cfg = config.get("zotero", {})
        self.collection_name: str = zotero_cfg.get("export_collection", "")
        self.tags: list[str] = zotero_cfg.get("export_tags", [])
        self.attach_mode: str = zotero_cfg.get("attach_mode", "best")
        self._collection_key: str | None = None  # resolved lazily on first export

    def export(self, papers: list[Any], output_dir: Path | None = None) -> list[Any]:
        """Export papers to Zotero. Mutates paper.zotero_key on success."""
        return self._manager.run_async(self._export_async(papers, output_dir))

    async def _export_async(self, papers: list[Any], output_dir: Path | None) -> list[Any]:
        client = self._manager.client

        # Resolve or create the target collection once
        if self.collection_name:
            self._collection_key = await self._get_or_create_collection(
                client, self.collection_name
            )

        collections = [self._collection_key] if self._collection_key else []

        for paper in papers:
            # Skip papers that are already in the library
            if paper.in_library and paper.zotero_key:
                continue

            key = await self._add_paper(client, paper, collections, output_dir)
            if key:
                paper.zotero_key = key
                paper.in_library = True

        return papers

    async def _add_paper(
        self,
        client,
        paper: Any,
        collections: list[str],
        output_dir: Path | None,
    ) -> str | None:
        common = {
            "collections": collections,
            "tags": self.tags,
            "attach_mode": self.attach_mode,
        }

        # Strategy 1: DOI (most reliable metadata)
        if paper.doi:
            raw = await client.call_tool("zotero_add_by_doi", {
                "doi": paper.doi,
                **common,
            })
            key = _extract_key(raw)
            if key:
                return key

        # Strategy 2: URL (arXiv URLs work natively with zotero-mcp)
        url = paper.url or paper.pdf_url
        if url:
            raw = await client.call_tool("zotero_add_by_url", {
                "url": url,
                **common,
            })
            key = _extract_key(raw)
            if key:
                return key

        # Strategy 3: Local PDF downloaded by the downloader stage
        # Convention: downloader saves files as <sanitized_title>.pdf in output_dir
        if output_dir:
            safe_name = "".join(
                c if c.isalnum() or c in " _-" else "_" for c in paper.title
            )[:80].strip()
            pdf_path = output_dir / f"{safe_name}.pdf"
            if pdf_path.exists():
                raw = await client.call_tool("zotero_add_from_file", {
                    "file_path": str(pdf_path),
                    "collections": collections,
                    "tags": self.tags,
                })
                return _extract_key(raw)

        return None

    async def _get_or_create_collection(self, client, name: str) -> str | None:
        """Return the key of a named collection, creating it if it doesn't exist."""
        raw = await client.call_tool("zotero_get_collections", {})
        try:
            data = json.loads(raw)
            collections = data if isinstance(data, list) else data.get("collections", [])
            for col in collections:
                if isinstance(col, dict) and col.get("name", "").lower() == name.lower():
                    return col.get("key")
        except (json.JSONDecodeError, ValueError, AttributeError):
            pass

        # Collection not found — create it
        raw = await client.call_tool("zotero_create_collection", {"name": name})
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return (
                    data.get("key")
                    or data.get("collection", {}).get("key")
                )
        except (json.JSONDecodeError, ValueError):
            pass
        return None


def _extract_key(raw: str) -> str | None:
    """Extract the Zotero item key from a tool response string."""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return (
                data.get("key")
                or data.get("item_key")
                or (data.get("item") or {}).get("key")
            )
    except (json.JSONDecodeError, ValueError):
        pass
    return None

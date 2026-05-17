from __future__ import annotations

import asyncio
import json
import shutil
from typing import Any

from .base import BaseSearcher
from .mcp_client import MCPClientContext, run_async
from ..models import Paper


class ArxivSearcher(BaseSearcher):
    """Searches arXiv via the arxiv-mcp-server."""

    name = "arxiv"

    def __init__(self, config: dict[str, Any]):
        search_cfg = config.get("search", {})
        arxiv_cfg = search_cfg.get("arxiv", {})
        self.max_results = arxiv_cfg.get("max_results", 50)
        self.storage_path = arxiv_cfg.get("storage_path", "")
        # Global year range (set by CLI) takes precedence over per-backend.
        self.year_from: int | None = (
            search_cfg.get("year_from") if search_cfg.get("year_from") is not None
            else arxiv_cfg.get("year_from")
        )
        self.year_to: int | None = (
            search_cfg.get("year_to") if search_cfg.get("year_to") is not None
            else arxiv_cfg.get("year_to")
        )
        self.query_delay: float = float(arxiv_cfg.get("query_delay", 1.0))
        server_command = shutil.which("arxiv-mcp-server")
        if server_command:
            args: list[str] = []
        else:
            server_command = shutil.which("uvx") or "uvx"
            args = ["arxiv-mcp-server"]

        if self.storage_path:
            args.extend(["--storage-path", self.storage_path])
        self._server_params = {
            "command": server_command,
            "args": args,
        }

    def search(self, queries: list[str]) -> list[Paper]:
        return run_async(self._search_async(queries))

    async def _search_async(self, queries: list[str]) -> list[Paper]:
        client = MCPClientContext(**self._server_params)
        await client.connect()
        try:
            papers = []
            seen_ids = set()
            for i, query in enumerate(queries):
                if i > 0 and self.query_delay > 0:
                    await asyncio.sleep(self.query_delay)
                tool_args: dict[str, Any] = {
                    "query": query,
                    "max_results": self.max_results,
                    "sort_by": "relevance",
                }
                if self.year_from is not None:
                    tool_args["date_from"] = f"{self.year_from}-01-01"
                raw = await client.call_tool("search_papers", tool_args)
                results = self._parse_search_results(raw)
                for r in results:
                    paper_id = r.get("id", r.get("entry_id", ""))
                    if paper_id in seen_ids:
                        continue
                    seen_ids.add(paper_id)
                    entry_url = r.get("url", r.get("entry_id", ""))
                    pdf_url = r.get("pdf_url", "") or (entry_url if "arxiv.org/pdf" in entry_url else "")
                    papers.append(Paper(
                        title=r.get("title", ""),
                        abstract=r.get("abstract", r.get("summary", "")),
                        authors=r.get("authors", []),
                        url=entry_url,
                        pdf_url=pdf_url,
                        source="arxiv",
                        year=self._extract_year(r),
                        doi=r.get("doi", ""),
                        retrieval_query=query,
                    ))
            return papers
        finally:
            await client.disconnect()

    def _parse_search_results(self, raw: str) -> list[dict]:
        """Parse the MCP server's search results response."""
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("papers", "results", "articles"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
                return [data]
        except json.JSONDecodeError:
            return []

    def _extract_year(self, result: dict) -> int | None:
        published = result.get("published", "")
        if published and len(published) >= 4:
            try:
                return int(published[:4])
            except ValueError:
                pass
        return None

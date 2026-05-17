from __future__ import annotations

import asyncio
import os
import re
from typing import Any

import httpx

from .base import BaseSearcher
from ..models import Paper

def _best_publication(item: dict) -> str | None:
    """Return the best available publication name from a Semantic Scholar API item."""
    venue_obj = item.get("publicationVenue") or {}
    name = venue_obj.get("name") or ""
    if name:
        return name
    journal = item.get("journal") or {}
    journal_name = (journal.get("name") or "").strip()
    if journal_name:
        return journal_name
    return item.get("venue") or None


_BASE_URL = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "title,url,abstract,authors,year,citationCount,venue,journal,publicationVenue,publicationTypes,openAccessPdf,externalIds"
_ENRICH_FIELDS = "abstract,tldr,journal,publicationVenue,publicationTypes,externalIds"


class SemanticScholarSearcher(BaseSearcher):
    """Searches Semantic Scholar via its REST API (no MCP server needed).

    Uses /paper/search (relevance-ranked) instead of /paper/search/bulk (token-AND)
    because the bulk endpoint ANDs every token, yielding very few results for
    multi-word queries.  The relevance endpoint uses S2's custom-trained ranker
    and matches the behaviour of the Semantic Scholar website search.
    """

    # Pagination page size for /paper/search (max 100 per request).
    _PAGE_SIZE = 100

    name = "semantic_scholar"

    def __init__(self, config: dict[str, Any]):
        search_cfg = config.get("search", {})
        s2_cfg = search_cfg.get("semantic_scholar", {})

        self.max_results: int = s2_cfg.get("max_results", 50)
        self.query_delay: float = float(s2_cfg.get("query_delay", 1.5))

        # Global year range (set by CLI) takes precedence over per-backend.
        self.year_from: int | None = (
            search_cfg.get("year_from") if search_cfg.get("year_from") is not None
            else s2_cfg.get("year_from")
        )
        self.year_to: int | None = (
            search_cfg.get("year_to") if search_cfg.get("year_to") is not None
            else s2_cfg.get("year_to")
        )

        api_key = s2_cfg.get("api_key") or os.environ.get(
            s2_cfg.get("api_key_env", "SEMANTIC_SCHOLAR_API_KEY"), ""
        )
        self._headers: dict[str, str] = {}
        if api_key:
            self._headers["x-api-key"] = api_key

    # -- public sync interface --------------------------------------------------

    def search(self, queries: list[str]) -> list[Paper]:
        return self._search_sync(queries)

    # -- internal ---------------------------------------------------------------

    def _search_sync(self, queries: list[str]) -> list[Paper]:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        coro = self._search_async(queries)
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return asyncio.run(coro)

    async def _search_async(self, queries: list[str]) -> list[Paper]:
        papers: list[Paper] = []
        seen_ids: set[str] = set()
        # Map paperId → Paper for enrichment
        id_to_paper: dict[str, Paper] = {}

        async with httpx.AsyncClient(
            base_url=_BASE_URL,
            headers=self._headers,
            timeout=30.0,
        ) as client:
            for i, query in enumerate(queries):
                if i > 0 and self.query_delay > 0:
                    await asyncio.sleep(self.query_delay)
                new, id_map = await self._search_relevance(client, query)
                for paper in new:
                    key = paper.doi or paper.title.lower()
                    if key in seen_ids:
                        continue
                    seen_ids.add(key)
                    papers.append(paper)
                id_to_paper.update(id_map)

            # Batch-enrich papers missing publication, document_type, or tldr
            papers_set = set(id(p) for p in papers)
            need_enrich = [
                pid for pid, p in id_to_paper.items()
                if id(p) in papers_set and (not p.publication or not p.document_type or not p.tldr)
            ]
            if need_enrich:
                await self._batch_enrich(client, need_enrich, id_to_paper)

        return papers

    async def _batch_enrich(
        self,
        client: httpx.AsyncClient,
        paper_ids: list[str],
        id_to_paper: dict[str, "Paper"],
    ) -> None:
        """Fill missing publication/document_type via /paper/batch."""
        # Batch endpoint accepts up to 500 ids
        chunk_size = 100
        for i in range(0, len(paper_ids), chunk_size):
            chunk = paper_ids[i : i + chunk_size]
            resp = await client.post(
                "/paper/batch",
                params={"fields": _ENRICH_FIELDS},
                json={"ids": chunk},
            )
            if resp.status_code != 200:
                continue
            for item in resp.json():
                if not item:
                    continue
                pid = item.get("paperId")
                paper = id_to_paper.get(pid)
                if not paper:
                    continue
                if not paper.publication:
                    paper.publication = _best_publication(item)
                if not paper.document_type:
                    pub_types = item.get("publicationTypes") or []
                    paper.document_type = ", ".join(pub_types) if pub_types else None
                if not paper.tldr:
                    paper.tldr = (item.get("tldr") or {}).get("text") or None
                # abstract stays None here; scraping fills it later

    async def _search_relevance(
        self, client: httpx.AsyncClient, query: str,
    ) -> tuple[list[Paper], dict[str, Paper]]:
        """Search via /paper/search (relevance-ranked, website-equivalent)."""
        params: dict[str, Any] = {
            "query": query,
            "fields": _FIELDS,
            "limit": self._PAGE_SIZE,
        }
        year_str = self._year_param()
        if year_str:
            params["year"] = year_str

        collected: list[Paper] = []
        id_map: dict[str, Paper] = {}
        offset: int = 0
        while True:
            if offset > 0:
                params["offset"] = offset
            resp = await client.get("/paper/search", params=params)
            if resp.status_code == 429:
                await asyncio.sleep(2)
                continue
            if resp.status_code != 200:
                break
            data = resp.json()
            for item in data.get("data", []):
                paper = self._parse_result(item, query)
                collected.append(paper)
                if item.get("paperId"):
                    id_map[item["paperId"]] = paper
            if len(collected) >= self.max_results:
                collected = collected[: self.max_results]
                break
            offset += len(data.get("data", []))
            # No more pages when fewer than limit returned or no next link
            if data.get("next") is None:
                break
        return collected, id_map

    def _parse_result(self, item: dict, query: str) -> Paper:
        authors = [a["name"] for a in item.get("authors") or [] if a.get("name")]
        pdf_obj = item.get("openAccessPdf") or {}
        raw_pdf = pdf_obj.get("url") or ""
        # Filter empty strings and DOI redirects — neither is a direct PDF
        pdf_url: str | None = raw_pdf if raw_pdf and "doi.org" not in raw_pdf else None
        # Fallback: parse disclaimer for a direct PDF URL
        if not pdf_url:
            disclaimer = pdf_obj.get("disclaimer") or ""
            m = re.search(r'https?://\S+\.pdf', disclaimer)
            if m:
                pdf_url = m.group(0).rstrip(".,)")
        ext_ids = item.get("externalIds") or {}
        doi = ext_ids.get("DOI")  # API returns uppercase "DOI"
        # Fallback: arXiv PDF URL
        arxiv_id = ext_ids.get("ArXiv")
        if not pdf_url and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
        pub_types = item.get("publicationTypes") or []
        doc_type = ", ".join(pub_types) if pub_types else None
        publication = _best_publication(item)
        citations = item.get("citationCount")

        tldr_text = (item.get("tldr") or {}).get("text") or None

        return Paper(
            title=item.get("title", ""),
            abstract=item.get("abstract"),
            tldr=tldr_text,
            url=item.get("url"),
            pdf_url=pdf_url,
            authors=authors,
            year=item.get("year"),
            publication=publication,
            doi=doi,
            document_type=doc_type,
            metadata_line=f"citations: {citations}" if citations is not None else None,
            source="semantic_scholar",
            retrieval_query=query,
        )

    def _year_param(self) -> str | None:
        if self.year_from and self.year_to:
            return f"{self.year_from}-{self.year_to}"
        if self.year_from:
            return f"{self.year_from}-"
        if self.year_to:
            return f"-{self.year_to}"
        return None

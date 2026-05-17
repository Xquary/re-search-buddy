from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from .base import BaseSearcher
from ..models import Paper

_META_BASE = "https://api.springernature.com/meta/v2/json"
_PAGE_SIZE = 25  # max Springer allows per page is 50; 25 is a safe default


class SpringerSearcher(BaseSearcher):
    """Search Springer Nature via the Meta API (keyword search, all content types).

    Auth: ``?api_key=<SPRINGER_META_API_KEY>`` query parameter.
    OA papers get ``pdf_url`` populated from the record's pdf openurl — Phase 1
    of the downloader will fetch them directly.
    Non-OA papers: no pdf_url; browser or Anna's Archive fallback applies.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        springer_cfg = config.get("search", {}).get("springer", {})
        self.api_key = os.environ.get(
            springer_cfg.get("meta_api_key_env", "SPRINGER_META_API_KEY"), ""
        )
        self.max_results: int = springer_cfg.get("max_results", 50)
        self.query_delay: float = springer_cfg.get("query_delay", 1.5)
        self.year_from: int | None = springer_cfg.get("year_from")
        self.year_to: int | None = springer_cfg.get("year_to")

    def search(self, queries: list[str]) -> list[Paper]:
        return asyncio.run(self._search_async(queries))

    async def _search_async(self, queries: list[str]) -> list[Paper]:
        papers: list[Paper] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=30.0) as client:
            for i, query in enumerate(queries):
                if i > 0 and self.query_delay > 0:
                    await asyncio.sleep(self.query_delay)
                new = await self._search_query(client, query)
                for p in new:
                    key = p.doi or p.title.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    papers.append(p)

        return papers

    async def _search_query(self, client: httpx.AsyncClient, query: str) -> list[Paper]:
        papers: list[Paper] = []
        collected = 0
        start = 1

        # Build optional date constraint
        date_filter = ""
        if self.year_from or self.year_to:
            y_from = str(self.year_from) if self.year_from else "1900"
            y_to = str(self.year_to) if self.year_to else "2100"
            date_filter = f" date-between:\"{y_from}-01-01\" AND \"{y_to}-12-31\""

        while collected < self.max_results:
            page_size = min(_PAGE_SIZE, self.max_results - collected)
            params: dict[str, Any] = {
                "q": query + date_filter,
                "api_key": self.api_key,
                "p": page_size,
                "s": start,
            }
            try:
                resp = await client.get(_META_BASE, params=params)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"  [springer] HTTP error for '{query}': {exc}")
                break

            data = resp.json()
            result_meta = data.get("result", [{}])[0]
            records = data.get("records", [])
            if not records:
                break

            for rec in records:
                p = _record_to_paper(rec, query)
                if p:
                    papers.append(p)
            collected += len(records)

            total = int(result_meta.get("total", 0))
            if collected >= total:
                break
            start += page_size

        return papers


def _record_to_paper(rec: dict, query: str) -> Paper | None:
    title = (rec.get("title") or "").strip()
    doi = (rec.get("doi") or "").strip()
    if not title:
        return None

    authors_raw = rec.get("creators") or []
    authors = ", ".join(c.get("creator", "") for c in authors_raw if c.get("creator"))

    year_str = (rec.get("publicationDate") or rec.get("onlineDate") or "")[:4]
    year = int(year_str) if year_str.isdigit() else None

    abstract = (rec.get("abstract") or "").strip()
    publication = rec.get("publicationName") or ""
    publisher = rec.get("publisherName") or rec.get("publisher") or ""

    is_oa = rec.get("openaccess", "false") == "true"

    # Extract PDF openurl (works for OA; non-OA redirects through auth)
    pdf_url: str | None = None
    if is_oa:
        for u in rec.get("url") or []:
            if u.get("format") == "pdf" and u.get("value"):
                pdf_url = u["value"]
                break

    keywords = "; ".join(rec.get("keyword") or [])
    issn = rec.get("issn") or rec.get("eIssn") or ""
    volume = rec.get("volume") or ""
    issue = rec.get("number") or ""
    start_page = rec.get("startingPage") or ""
    end_page = rec.get("endingPage") or ""
    pages = f"{start_page}-{end_page}".strip("-") if start_page or end_page else ""

    doc_types = rec.get("genre") or []
    document_type = doc_types[0] if doc_types else rec.get("contentType", "")

    meta_parts = [f"citations: N/A", f"type: {document_type}"]
    if is_oa:
        meta_parts.append("open-access")
    metadata_line = " | ".join(meta_parts)

    return Paper(
        title=title,
        authors=authors,
        year=year,
        abstract=abstract,
        doi=doi,
        pdf_url=pdf_url,
        publication=publication,
        publisher=publisher,
        document_type=document_type,
        source="Springer",
        retrieval_query=query,
        metadata_line=metadata_line,
        issn=issn,
        volume=volume,
        issue=issue,
        pages=pages,
        open_access=is_oa,
        author_keywords=keywords,
    )

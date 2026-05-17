from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from .base import BaseSearcher
from ..models import Paper

_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"
_ABSTRACT_URL = "https://api.elsevier.com/content/abstract/scopus_id/{}"
_MAX_PER_REQUEST = 200  # Scopus STANDARD view hard limit


class ScopusSearcher(BaseSearcher):
    """Searches Scopus via direct REST API (STANDARD view, paginated)."""

    name = "scopus"

    def __init__(self, config: dict[str, Any]):
        search_cfg = config.get("search", {})
        scopus_cfg = search_cfg.get("scopus", {})

        self.max_results: int = scopus_cfg.get("max_results", 200)
        self.query_delay: float = float(scopus_cfg.get("query_delay", 1.5))
        self.sort: str = scopus_cfg.get("sort", "relevancy")
        self.enrich_abstracts: bool = scopus_cfg.get("enrich_abstracts", True)

        # Year range — prefer explicit config, fall back to top-level search config
        self.year_from: int | None = (
            search_cfg.get("year_from") if search_cfg.get("year_from") is not None
            else scopus_cfg.get("year_from")
        )
        self.year_to: int | None = (
            search_cfg.get("year_to") if search_cfg.get("year_to") is not None
            else scopus_cfg.get("year_to")
        )

        # Optional query-level field filters
        self.source_title: str | None = scopus_cfg.get("source_title")
        self.subject_area: str | None = scopus_cfg.get("subject_area")
        self.doc_type: str | None = scopus_cfg.get("doc_type")
        self.src_type: str | None = scopus_cfg.get("src_type")
        self.open_access_only: bool = scopus_cfg.get("open_access_only", False)

        api_key = scopus_cfg.get("api_key") or os.environ.get(
            scopus_cfg.get("api_key_env", "SCOPUS_API_KEY"), ""
        )
        self._headers = {
            "X-ELS-APIKey": api_key,
            "Accept": "application/json",
        }

    def search(self, queries: list[str]) -> list[Paper]:
        return asyncio.run(self._search_async(queries))

    async def _search_async(self, queries: list[str]) -> list[Paper]:
        async with httpx.AsyncClient(
            headers=self._headers, timeout=30.0, follow_redirects=True
        ) as client:
            papers: list[Paper] = []
            seen: set[str] = set()

            for i, query in enumerate(queries):
                if i > 0 and self.query_delay > 0:
                    await asyncio.sleep(self.query_delay)

                built_query = self._build_query(query)
                date_param = self._build_date_param()
                batch = await self._fetch_all(client, built_query, date_param)

                for item in batch:
                    key = item.get("doi") or item.get("scopus_id") or item.get("title", "")
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    papers.append(self._item_to_paper(item, query))

            if self.enrich_abstracts:
                await self._enrich_abstracts(client, papers)

        return papers

    async def _fetch_all(
        self, client: httpx.AsyncClient, query: str, date_param: str | None
    ) -> list[dict]:
        """Paginate through results until max_results is reached."""
        results: list[dict] = []
        start = 0

        while len(results) < self.max_results:
            count = min(_MAX_PER_REQUEST, self.max_results - len(results))
            params: dict[str, Any] = {
                "query": query,
                "count": count,
                "start": start,
                "sort": self.sort,
                "view": "STANDARD",
            }
            if date_param:
                params["date"] = date_param
            if self.subject_area:
                params["subj"] = self.subject_area

            try:
                resp = await client.get(_SEARCH_URL, params=params)
                if resp.status_code == 429:
                    reset = int(resp.headers.get("X-RateLimit-Reset", 0))
                    import time
                    wait = max(reset - time.time(), 5)
                    print(f"  [scopus] rate limited — waiting {wait:.0f}s")
                    await asyncio.sleep(wait)
                    resp = await client.get(_SEARCH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"  [scopus] request error: {e}")
                break

            sr = data.get("search-results", {})
            entries = sr.get("entry", [])

            if not entries or (entries and entries[0].get("error")):
                break

            total_available = int(sr.get("opensearch:totalResults", 0))
            results.extend(self._parse_entries(entries))
            start += len(entries)

            if start >= min(total_available, 5000):  # Scopus caps at 5000
                break

            await asyncio.sleep(0.15)  # stay well under 9 req/s throttle

        return results

    def _parse_entries(self, entries: list[dict]) -> list[dict]:
        out = []
        for e in entries:
            # Full author list (only in COMPLETE view; STANDARD has dc:creator = first author)
            raw_authors = e.get("author", [])
            if isinstance(raw_authors, dict):
                raw_authors = [raw_authors]
            if raw_authors:
                authors = [
                    a.get("authname") or f"{a.get('surname', '')} {a.get('given-name', '')}".strip()
                    for a in raw_authors
                ]
            elif e.get("dc:creator"):
                authors = [e["dc:creator"]]
            else:
                authors = []

            # Affiliations: array of {affilname, affiliation-city, affiliation-country}
            raw_affils = e.get("affiliation", [])
            if isinstance(raw_affils, dict):
                raw_affils = [raw_affils]
            affil_parts = []
            for a in raw_affils:
                parts = filter(None, [
                    a.get("affilname"), a.get("affiliation-city"), a.get("affiliation-country")
                ])
                affil_parts.append("; ".join(parts))
            affiliations = " | ".join(affil_parts) if affil_parts else None

            out.append({
                "scopus_id": e.get("dc:identifier", "").replace("SCOPUS_ID:", ""),
                "title": e.get("dc:title") or "",
                "first_author": e.get("dc:creator"),
                "authors": authors,
                "affiliations": affiliations,
                "publication_name": e.get("prism:publicationName"),
                "issn": e.get("prism:issn") or e.get("prism:eissn"),
                "volume": e.get("prism:volume"),
                "issue": e.get("prism:issueIdentifier"),
                "pages": e.get("prism:pageRange"),
                "cover_date": e.get("prism:coverDate"),
                "doi": e.get("prism:doi"),
                "doc_type": e.get("subtypeDescription") or e.get("prism:aggregationType"),
                "src_type": e.get("prism:aggregationType"),
                "cited_by_count": e.get("citedby-count"),
                "author_keywords": e.get("authkeywords"),
                "open_access": bool(int(e.get("openaccessFlag") or e.get("openaccess") or 0)),
                "url": next(
                    (lnk["@href"] for lnk in e.get("link", []) if lnk.get("@ref") == "scopus"),
                    None,
                ),
            })
        return out

    async def _enrich_abstracts(
        self, client: httpx.AsyncClient, papers: list[Paper]
    ) -> None:
        to_fetch = [p for p in papers if not p.abstract and p.scopus_id]
        if not to_fetch:
            return

        total = len(to_fetch)
        fetched = 0
        failed = 0
        empty = 0
        errors: list[tuple[str, str]] = []  # (scopus_id, error_message)
        print(f"  [scopus] fetching abstracts for {total} papers...")

        for i, paper in enumerate(to_fetch):
            try:
                resp = await client.get(
                    _ABSTRACT_URL.format(paper.scopus_id),
                    params={"view": "FULL"},
                )
                resp.raise_for_status()
                data = resp.json()
                root = (
                    data.get("abstracts-retrieval-response")
                    or data.get("abstract-retrieval-response")
                    or {}
                )
                abstract = root.get("coredata", {}).get("dc:description")
                if abstract:
                    paper.abstract = abstract
                    fetched += 1
                else:
                    empty += 1
            except Exception as e:
                failed += 1
                if len(errors) < 3:
                    errors.append((paper.scopus_id, str(e)[:120]))

            # Progress every 100 papers
            if (i + 1) % 100 == 0:
                print(f"  [scopus] abstracts: {i+1}/{total}  "
                      f"(ok={fetched} failed={failed} empty={empty})")

            await asyncio.sleep(0.15)

        # Summary
        print(f"  [scopus] abstracts done: {fetched} fetched, "
              f"{empty} empty, {failed} failed (of {total})")
        if errors:
            print(f"  [scopus] first errors:")
            for sid, msg in errors:
                print(f"    {sid}: {msg}")
        if failed >= total * 0.9 and total > 10:
            print(f"  [scopus] WARNING: {failed}/{total} abstract requests failed — "
                  f"check API key, quota, and institutional IP entitlements")

    def _build_query(self, query: str) -> str:
        """Wrap user query with inline field filters.

        If the query already contains explicit Scopus field codes
        (TITLE, ABS, SUBJAREA, SRCTYPE, DOCTYPE, PUBYEAR, etc.),
        return it as-is — don't add a redundant TITLE-ABS-KEY wrapper.
        """
        # Detect fully-qualified query (already has field codes)
        _field_markers = [
            "TITLE(", "ABS(", "SUBJAREA(", "SRCTYPE(", "DOCTYPE(",
            "PUBYEAR", "SRCTITLE(", "OPENACCESS(", "AFFILCOUNTRY(",
        ]
        if any(marker in query for marker in _field_markers):
            return query

        parts = [f"TITLE-ABS-KEY({query})"]
        if self.source_title:
            parts.append(f'SRCTITLE("{self.source_title}")')
        if self.doc_type:
            parts.append(f"DOCTYPE({self.doc_type})")
        if self.src_type:
            parts.append(f"SRCTYPE({self.src_type})")
        if self.open_access_only:
            parts.append("OPENACCESS(1)")
        return " AND ".join(parts)

    def _build_date_param(self) -> str | None:
        """Build the `date` API parameter (YYYY-YYYY) from year_from/year_to."""
        if self.year_from or self.year_to:
            lo = str(self.year_from) if self.year_from else "1000"
            hi = str(self.year_to) if self.year_to else "2099"
            return f"{lo}-{hi}"
        return None

    def _item_to_paper(self, item: dict, query: str) -> Paper:
        year_str = (item.get("cover_date") or "")[:4]
        year = int(year_str) if year_str.isdigit() else None
        cited = item.get("cited_by_count")

        return Paper(
            title=item.get("title") or "",
            abstract=None,
            url=item.get("url"),
            authors=item.get("authors") or [],
            year=year,
            publication=item.get("publication_name"),
            document_type=item.get("doc_type"),
            doi=item.get("doi"),
            scopus_id=item.get("scopus_id") or None,
            issn=item.get("issn"),
            volume=item.get("volume"),
            issue=item.get("issue"),
            pages=item.get("pages"),
            open_access=item.get("open_access", False),
            author_keywords=item.get("author_keywords"),
            affiliations=item.get("affiliations"),
            metadata_line=f"citations: {cited}" if cited else None,
            source="scopus",
            retrieval_query=query,
        )

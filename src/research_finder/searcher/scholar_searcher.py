from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import unicodedata
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .base import BaseSearcher
from .mcp_client import MCPClientContext, run_async
from ..models import Paper

logger = logging.getLogger(__name__)

# Patterns for extracting abstracts from publisher pages, ordered by reliability.
_ABSTRACT_CSS_SELECTORS = [
    "meta[name='citation_abstract']",
    "meta[name='dc.description']",
    "meta[name='description']",
    "meta[name='citation_description']",
    "div.abstract",
    "div#abstract",
    "section.abstract",
    "div[class*='abstract']",
    "p[class*='abstract']",
]
_ABSTRACT_TEXT_PATTERNS = [
    re.compile(r"Abstract[:\s]*(.*?)(?:\n\n|Keywords|Introduction|1\.\s)", re.DOTALL | re.IGNORECASE),
    re.compile(r"Abstract[:\s]*(.*?)$", re.DOTALL | re.IGNORECASE),
]


class ScholarSearcher(BaseSearcher):
    """Searches Google Scholar via the local Google-Scholar-MCP-Server."""

    name = "scholar"

    def __init__(self, config: dict[str, Any]):
        scholar_cfg = config.get("search", {}).get("scholar", {})
        self.max_results = scholar_cfg.get("max_results", 50)
        self.query_delay: float = float(scholar_cfg.get("query_delay", 3.0))
        self.enrich_abstracts: bool = scholar_cfg.get("enrich_abstracts", True)
        self.enrich_delay: float = float(scholar_cfg.get("enrich_delay", 1.0))
        self._http = httpx.Client(
            timeout=10,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            },
        )
        # Use the active interpreter so the installed package is resolved from the same environment.
        self._server_params = {
            "command": sys.executable,
            "args": ["-m", "google_scholar_server"],
        }

    def search(self, queries: list[str]) -> list[Paper]:
        return run_async(self._search_async(queries))

    async def _search_async(self, queries: list[str]) -> list[Paper]:
        client = MCPClientContext(**self._server_params)
        await client.connect()
        try:
            papers = []
            seen_titles: set[str] = set()
            for i, query in enumerate(queries):
                if i > 0 and self.query_delay > 0:
                    await asyncio.sleep(self.query_delay)
                raw = await client.call_tool("search_google_scholar_key_words", {
                    "query": query,
                    "num_results": self.max_results,
                })
                results = self._parse_results(raw)
                for r in results:
                    raw_title = r.get("Title", r.get("title", ""))
                    title = self._clean_title(raw_title)
                    if not title or title.lower() in seen_titles:
                        continue
                    seen_titles.add(title.lower())
                    authors_raw = r.get("Authors", r.get("authors", ""))
                    metadata = self._parse_metadata(authors_raw)
                    papers.append(Paper(
                        title=title,
                        abstract=self._clean_text(r.get("Abstract", r.get("abstract", ""))),
                        retrieval_query=query,
                        authors=metadata["authors"],
                        publication=metadata["publication"],
                        publisher=metadata["publisher"],
                        metadata_line=metadata["metadata_line"],
                        document_type=self._extract_document_type(raw_title),
                        url=self._clean_text(r.get("URL", r.get("url", ""))),
                        source="scholar",
                        year=metadata["year"],
                    ))
        finally:
            await client.disconnect()

        if self.enrich_abstracts and papers:
            papers = self._enrich_abstracts_sync(papers)
        return papers

    # ── Abstract enrichment ────────────────────────────────────────────────────

    def _enrich_abstracts_sync(self, papers: list[Paper]) -> list[Paper]:
        enriched = 0
        for paper in papers:
            # Try to extract DOI from the URL itself (e.g. /10.xxx/yyy patterns)
            if not paper.doi and paper.url:
                paper.doi = self._extract_doi_from_url(paper.url)

            if paper.abstract and len(paper.abstract) > 300 and self._looks_like_abstract(paper.abstract):
                continue
            if not paper.url:
                continue
            full, doi = self._fetch_abstract_and_doi_from_url(paper.url)
            if full and len(full) > len(paper.abstract or ""):
                paper.abstract = full
                enriched += 1
            if doi and not paper.doi:
                paper.doi = doi
            if self.enrich_delay > 0:
                import time
                time.sleep(self.enrich_delay)
        if enriched:
            logger.info("Enriched %d / %d abstracts from publisher pages", enriched, len(papers))
        return papers

    @staticmethod
    def _looks_like_abstract(text: str, min_chars: int = 80) -> bool:
        """Reject garbage: HTML tags, CSS/JS snippets, navigation boilerplate."""
        if len(text) < min_chars:
            return False
        if "<" in text and ">" in text:
            tag_count = text.count("<") + text.count(">")
            if tag_count / len(text) > 0.05:
                return False
        boilerplate = ("sign in", "log in", "register", "cookie", "subscribe", "cart")
        lower = text[:200].lower()
        if sum(1 for b in boilerplate if b in lower) >= 2:
            return False
        return True

    @staticmethod
    def _extract_doi_from_url(url: str) -> str | None:
        """Try to extract a DOI from a URL path (e.g. scienceirect.com/pii/... → no DOI, but
        doi.org/10.xxx or /article/10.xxx → yes)."""
        # Match DOI patterns in URL path
        m = re.search(r'(10\.\d{4,9}/[^\s"\'<>&?#]+)', url)
        if m:
            doi = m.group(1).rstrip(".,;)")
            if len(doi) > 7:  # sanity: real DOIs are longer than just "10.XXXX/"
                return doi
        return None

    def _fetch_abstract_and_doi_from_url(self, url: str) -> tuple[str | None, str | None]:
        try:
            resp = self._http.get(url)
            resp.raise_for_status()
        except httpx.HTTPError:
            return None, None

        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            return None, None

        try:
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception:
            return None, None

        # Extract DOI from meta tags
        doi = self._extract_doi_from_soup(soup)

        # 1. Try meta tags (most reliable for academic publishers)
        # Ordered: citation_abstract > dc.description > description
        for selector in _ABSTRACT_CSS_SELECTORS:
            if selector.startswith("meta"):
                tag = soup.select_one(selector)
                if tag and tag.get("content"):
                    text = self._clean_text(tag["content"])
                    if text and self._looks_like_abstract(text):
                        return text, doi

        # 2. Try div/section/p with "abstract" in class
        for selector in _ABSTRACT_CSS_SELECTORS:
            if not selector.startswith("meta"):
                el = soup.select_one(selector)
                if el:
                    text = self._clean_text(el.get_text(separator=" ", strip=True))
                    text = re.sub(r"^Abstract[:\s]*", "", text, flags=re.IGNORECASE)
                    if text and self._looks_like_abstract(text):
                        return text, doi

        # 3. Regex fallback on full text
        for pattern in _ABSTRACT_TEXT_PATTERNS:
            m = pattern.search(resp.text[:10000])
            if m:
                text = self._clean_text(m.group(1))
                if text and self._looks_like_abstract(text):
                    return text, doi

        return None, doi

    @staticmethod
    def _extract_doi_from_soup(soup: BeautifulSoup) -> str | None:
        """Extract DOI from publisher page meta tags."""
        for selector in [
            "meta[name='citation_doi']",
            "meta[name='dc.identifier']",
            "meta[name='DOI']",
            "meta[name='dc.Identifier']",
        ]:
            tag = soup.select_one(selector)
            if tag and tag.get("content"):
                doi = tag["content"].strip()
                if doi.startswith("10."):
                    return doi
                # Some publishers prefix with "doi:" or "DOI:"
                if "10." in doi:
                    m = re.search(r'(10\.\d{4,9}/\S+)', doi)
                    if m:
                        return m.group(1).rstrip(".,;)")
        return None

    def _parse_results(self, raw: str) -> list[dict]:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
            return []
        except json.JSONDecodeError:
            # MCP server may return multiple JSON objects concatenated
            results: list[dict] = []
            decoder = json.JSONDecoder()
            pos = 0
            text = raw.strip()
            while pos < len(text):
                match = text.find("{", pos)
                if match == -1:
                    break
                try:
                    obj, end = decoder.raw_decode(text, match)
                    if isinstance(obj, dict):
                        results.append(obj)
                    pos = end
                except json.JSONDecodeError:
                    break
            return results

    def _parse_authors(self, authors: Any) -> list[str]:
        if isinstance(authors, list):
            return [self._clean_text(str(a)) for a in authors if str(a).strip()]
        if isinstance(authors, str) and authors:
            text = self._clean_text(authors)
            primary = text.split(" - ", 1)[0]
            parts = re.split(r",|;|&", primary)
            cleaned = [self._clean_text(part) for part in parts]
            return [part for part in cleaned if part]
        return []

    def _extract_year(self, authors: Any) -> int | None:
        if not isinstance(authors, str):
            return None
        match = re.search(r"\b(19|20)\d{2}\b", authors)
        if match:
            try:
                return int(match.group(0))
            except ValueError:
                return None
        return None

    def _parse_metadata(self, authors: Any) -> dict[str, Any]:
        if not isinstance(authors, str):
            return {
                "authors": self._parse_authors(authors),
                "publication": None,
                "publisher": None,
                "year": None,
                "metadata_line": None,
            }

        text = self._clean_text(authors)
        parts = [part.strip() for part in text.split(" - ") if part.strip()]
        author_part = parts[0] if parts else text
        year = self._extract_year(text)

        publication: str | None = None
        publisher: str | None = None

        if len(parts) >= 2:
            middle = parts[1]
            publication = re.sub(r"[,\s]+(19|20)\d{2}$", "", middle).strip() or None
            if re.fullmatch(r"(19|20)\d{2}", middle):
                publication = None
        if len(parts) >= 3:
            publisher = parts[2]

        return {
            "authors": self._parse_authors(author_part),
            "publication": publication,
            "publisher": publisher,
            "year": year,
            "metadata_line": text,
        }

    def _clean_title(self, text: Any) -> str:
        value = self._clean_text(text)
        value = re.sub(r"^(?:\[[^\]]+\])+", "", value).strip()
        return value

    def _extract_document_type(self, text: Any) -> str | None:
        value = self._clean_text(text)
        badges = re.findall(r"\[([^\]]+)\]", value)
        if not badges:
            return None
        unique_badges: list[str] = []
        for badge in badges:
            cleaned = badge.strip()
            if cleaned and cleaned not in unique_badges:
                unique_badges.append(cleaned)
        return "; ".join(unique_badges) if unique_badges else None

    def _clean_text(self, text: Any) -> str:
        if text is None:
            return ""
        value = str(text).replace("\xa0", " ")
        value = unicodedata.normalize("NFKC", value)
        replacements = {
            "â€¦": "…",
            "â€“": "–",
            "â€”": "—",
            "â€˜": "'",
            "â€™": "'",
            "â€œ": '"',
            "â€\x9d": '"',
            "Krüger": "Krüger",
        }
        for bad, good in replacements.items():
            value = value.replace(bad, good)
        return " ".join(value.split())

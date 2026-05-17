from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from .base import BaseSearcher
from .mcp_client import MCPClientContext, run_async
from ..models import Paper

# ── Selection constants ────────────────────────────────────────────────────────
PAPERS_PER_QUERY = 50   # metadata collected from CNKI per query (round 1)
# Final embedding/ranking top-N is set in the pipeline / test script (FINAL_TOP_N)
# ──────────────────────────────────────────────────────────────────────────────


class CnkiSearcher(BaseSearcher):
    """Searches CNKI via Chrome DevTools MCP (javascript-based extraction).

    Requires Chrome running with --remote-debugging-port=9222.
    Uses the chrome-devtools-mcp server to navigate CNKI and extract
    structured search results via evaluate_script.
    """

    name = "cnki"

    # Base URLs for each region
    _BASE_URLS = {
        "oversea": "https://oversea.cnki.net",
        "china": "https://kns.cnki.net",
    }

    def __init__(self, config: dict[str, Any]):
        cnki_cfg = config.get("search", {}).get("cnki", {})
        self.max_results = cnki_cfg.get("max_results", 50)
        region = cnki_cfg.get("region", "oversea")
        self._base_url = self._BASE_URLS.get(region, self._BASE_URLS["oversea"])
        self._server_params = {
            "command": "npx",
            "args": [
                "-y", "chrome-devtools-mcp@latest",
                "--browserUrl", "http://127.0.0.1:9222",
            ],
        }

    def search(self, queries: list[str]) -> list[Paper]:
        return run_async(self._search_async(queries))

    async def _search_async(self, queries: list[str]) -> list[Paper]:
        client = MCPClientContext(**self._server_params)
        await client.connect()
        try:
            papers: list[Paper] = []
            seen_titles: set[str] = set()

            for query in queries:
                # Navigate to CNKI search page
                await client.call_tool("navigate_page", {
                    "type": "url",
                    "url": f"{self._base_url}/kns8s/search",
                })

                # Page 1: search and extract
                js = self._build_search_js(query)
                raw = await client.call_tool("evaluate_script", {"function": js})
                results = self._parse_results(raw)

                # Paginate until we have PAPERS_PER_QUERY results for this query
                page = 1
                while len(results) < PAPERS_PER_QUERY:
                    has_more = await self._has_next_page(client)
                    if not has_more:
                        break
                    page += 1
                    # Click next and wait for the page indicator to advance before
                    # extracting — avoids race condition with asyncio.sleep
                    raw = await client.call_tool("evaluate_script", {
                        "function": self._build_click_and_extract_js(page),
                    })
                    more = self._parse_results(raw)
                    if not more:
                        break
                    results.extend(more)

                # Deduplicate and add up to PAPERS_PER_QUERY papers from this query
                added = 0
                for r in results:
                    if added >= PAPERS_PER_QUERY:
                        break
                    title = r.get("title", "").lower().strip()
                    if title in seen_titles or not title:
                        continue
                    seen_titles.add(title)
                    href = r.get("href", "")
                    papers.append(Paper(
                        title=r.get("title", ""),
                        abstract="",
                        keywords=self._parse_keywords(r.get("keywords", "")),
                        authors=self._parse_authors(r.get("authors", "")),
                        url=href,
                        source="cnki",
                        year=self._extract_year(r),
                        publication=r.get("journal", ""),
                        doi=r.get("doi", ""),
                        document_type=self._extract_document_type(href),
                        retrieval_query=query,
                        metadata_line=self._build_metadata_line(r),
                    ))
                    added += 1

            # Fetch abstracts from detail pages (rate-limited)
            await self._enrich_abstracts(client, papers)
            return papers[: self.max_results]
        finally:
            await client.disconnect()

    async def _has_next_page(self, client: MCPClientContext) -> bool:
        js = '() => !!document.querySelector("#PageNext")'
        raw = await client.call_tool("evaluate_script", {"function": js})
        return "true" in raw.lower()

    def _build_click_and_extract_js(self, expected_page: int) -> str:
        """Click #PageNext, wait for page indicator to reach expected_page, then extract rows.

        Using a JS-level wait avoids the asyncio.sleep race condition where the old
        page's rows are still in the DOM when we try to scrape.
        """
        return f"""\
async () => {{
  const btn = document.querySelector('#PageNext');
  if (!btn) return [];
  btn.click();

  // Wait for the page indicator to show expected_page (or timeout after 20s)
  await new Promise((resolve, reject) => {{
    let n = 0;
    const check = () => {{
      const text = document.querySelector('.countPageMark')?.innerText || '';
      const cur = parseInt(text.split('/')[0]) || 0;
      const hasRows = document.querySelectorAll('.result-table-list tbody tr').length > 0;
      if (cur >= {expected_page} && hasRows) resolve();
      else if (++n > 40) reject('timeout');
      else setTimeout(check, 500);
    }};
    setTimeout(check, 800);  // give CNKI a head-start before polling
  }});

  // Extract rows (same logic as _build_extract_js)
  const rows = document.querySelectorAll('.result-table-list tbody tr');
  const checkboxes = document.querySelectorAll('.result-table-list tbody input.cbItem');
  return Array.from(rows).map((row, i) => {{
    const titleLink = row.querySelector('td.name a.fz14');
    const authorLabels = Array.from(row.querySelectorAll('td.author div.authorinfo label') || []).map(l => l.innerText?.trim()).filter(Boolean);
    const authorLinks = Array.from(row.querySelectorAll('td.author a.KnowledgeNetLink') || []).map(a => a.innerText?.trim());
    const authors = authorLabels.length ? authorLabels : authorLinks;
    const journal = row.querySelector('td.source a')?.innerText?.trim() || row.querySelector('td.source')?.innerText?.trim() || '';
    const date = row.querySelector('td.date')?.innerText?.trim() || '';
    const citations = row.querySelector('td.quote')?.innerText?.trim() || '';
    const downloads = row.querySelector('td.download')?.innerText?.trim() || '';
    return {{
      title: titleLink?.innerText?.trim() || '',
      href: titleLink?.href || '',
      exportId: checkboxes[i]?.value || '',
      authors: authors.join('; '),
      journal,
      date,
      citations,
      downloads,
    }};
  }});
}}
"""

    def _build_extract_js(self) -> str:
        """JS to extract results from the current page (no search/submit)."""
        return """\
() => {
  const rows = document.querySelectorAll('.result-table-list tbody tr');
  const checkboxes = document.querySelectorAll('.result-table-list tbody input.cbItem');
  return Array.from(rows).map((row, i) => {
    const titleLink = row.querySelector('td.name a.fz14');
    const authorLabels = Array.from(row.querySelectorAll('td.author div.authorinfo label') || []).map(l => l.innerText?.trim()).filter(Boolean);
    const authorLinks = Array.from(row.querySelectorAll('td.author a.KnowledgeNetLink') || []).map(a => a.innerText?.trim());
    const authors = authorLabels.length ? authorLabels : authorLinks;
    const journal = row.querySelector('td.source a')?.innerText?.trim() || row.querySelector('td.source')?.innerText?.trim() || '';
    const date = row.querySelector('td.date')?.innerText?.trim() || '';
    const citations = row.querySelector('td.quote')?.innerText?.trim() || '';
    const downloads = row.querySelector('td.download')?.innerText?.trim() || '';
    return {
      title: titleLink?.innerText?.trim() || '',
      href: titleLink?.href || '',
      exportId: checkboxes[i]?.value || '',
      authors: authors.join('; '),
      journal,
      date,
      citations,
      downloads
    };
  });
}
"""

    def _build_search_js(self, query: str) -> str:
        """Build the JavaScript that searches CNKI and extracts results."""
        escaped = query.replace("\\", "\\\\").replace('"', '\\"')
        return f"""\
async () => {{
  const query = "{escaped}";

  // Wait for search input
  await new Promise((r, j) => {{
    let n = 0;
    const c = () => {{ if (document.querySelector('input.search-input')) r(); else if (++n > 30) j('timeout'); else setTimeout(c, 500); }};
    c();
  }});

  // Check captcha
  const outer = document.querySelector('#tcaptcha_transform_dy');
  if (outer && outer.getBoundingClientRect().top >= 0) return {{ error: 'captcha' }};

  // Fill and submit
  const input = document.querySelector('input.search-input');
  input.value = query;
  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
  document.querySelector('input.search-btn')?.click();

  // Wait for results
  await new Promise((r, j) => {{
    let n = 0;
    const c = () => {{
      const hasRows = document.querySelector('.result-table-list tbody tr');
      const hasCount = document.querySelector('.pagerTitleCell');
      if (hasRows || hasCount) r();
      else if (++n > 40) j('timeout');
      else setTimeout(c, 500);
    }};
    c();
  }});

  // Check captcha again
  const outer2 = document.querySelector('#tcaptcha_transform_dy');
  if (outer2 && outer2.getBoundingClientRect().top >= 0) return {{ error: 'captcha' }};

  // Extract results
  const rows = document.querySelectorAll('.result-table-list tbody tr');
  const checkboxes = document.querySelectorAll('.result-table-list tbody input.cbItem');
  const results = Array.from(rows).map((row, i) => {{
    const titleLink = row.querySelector('td.name a.fz14');
    const authorLabels = Array.from(row.querySelectorAll('td.author div.authorinfo label') || []).map(l => l.innerText?.trim()).filter(Boolean);
    const authorLinks = Array.from(row.querySelectorAll('td.author a.KnowledgeNetLink') || []).map(a => a.innerText?.trim());
    const authors = authorLabels.length ? authorLabels : authorLinks;
    const journal = row.querySelector('td.source a')?.innerText?.trim() || row.querySelector('td.source')?.innerText?.trim() || '';
    const date = row.querySelector('td.date')?.innerText?.trim() || '';
    const citations = row.querySelector('td.quote')?.innerText?.trim() || '';
    const downloads = row.querySelector('td.download')?.innerText?.trim() || '';
    return {{
      title: titleLink?.innerText?.trim() || '',
      href: titleLink?.href || '',
      exportId: checkboxes[i]?.value || '',
      authors: authors.join('; '),
      journal,
      date,
      citations,
      downloads
    }};
  }});

  return {{
    query,
    total: document.querySelector('.pagerTitleCell')?.innerText?.match(/([\\d,]+)/)?.[1] || '0',
    page: document.querySelector('.countPageMark')?.innerText || '1/1',
    results
  }};
}}
"""

    async def _enrich_abstracts(self, client: MCPClientContext, papers: list[Paper]) -> None:
        """Navigate to each paper's detail page and extract abstract + keywords."""
        for paper in papers:
            if not paper.url or paper.abstract:
                continue
            try:
                await client.call_tool("navigate_page", {
                    "type": "url",
                    "url": paper.url,
                })
                await asyncio.sleep(1.5)
                # Click expand button if present, then extract
                raw = await client.call_tool("evaluate_script", {
                    "function": self._build_detail_js(),
                })
                detail = self._parse_detail(raw)
                if detail:
                    if detail.get("abstract"):
                        paper.abstract = detail["abstract"]
                    if detail.get("keywords"):
                        paper.keywords = detail["keywords"]
                    if detail.get("authors") and not paper.authors:
                        paper.authors = detail["authors"]
                await asyncio.sleep(1)  # rate limit
            except Exception:
                continue

    def _build_detail_js(self) -> str:
        """Build JS to extract paper detail from a CNKI paper page."""
        return """\
async () => {
  // Wait for page to load
  await new Promise(r => { let n=0; const c=()=>{ if(document.querySelector('.brief')||document.querySelector('.abstract-text')) r(); else if(++n>30) r(); else setTimeout(c,500); }; c(); });

  // Click "More" / expand buttons to get full abstract
  document.querySelectorAll('a.changhref, span.abstract-top-flag, .zoom').forEach(el => {
    try { el.click(); } catch(e) {}
  });
  // Also click any link/span whose text is exactly "More" or "更多" or "展开"
  document.querySelectorAll('a, span').forEach(el => {
    const t = (el.innerText || '').trim();
    if (/^(More|more|更多|展开)$/.test(t)) { try { el.click(); } catch(e) {} }
  });
  await new Promise(r => setTimeout(r, 500));

  // Get abstract — try multiple selectors, pick the longest
  let abstract = '';
  const absSelectors = ['.abstract-text', '#ChDivSummary'];
  for (const sel of absSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const text = el.innerText?.trim() || '';
      if (text.length > abstract.length) abstract = text;
    }
  }

  // Keywords
  const keywordsP = document.querySelector('p.keywords, .keywords');
  const keywords = keywordsP
    ? Array.from(keywordsP.querySelectorAll('a')).map(a => a.innerText?.replace(/;$/, '').trim()).filter(Boolean)
    : [];

  // Authors from detail page
  const authorH3s = document.querySelectorAll('h3.author');
  const authors = [];
  if (authorH3s[0]) {
    authorH3s[0].querySelectorAll('a').forEach(a => {
      authors.push(a.innerText?.replace(/\\d+$/, '').trim());
    });
  }

  const journal = document.querySelector('.doc-top a')?.innerText?.trim() || '';
  const pubInfo = document.querySelector('.head-time')?.innerText?.trim() || '';
  const title = document.querySelector('.brief h1')?.innerText?.trim() || '';

  return { title, authors, abstract, keywords, journal, pubInfo };
}
"""

    def _parse_results(self, raw: str) -> list[dict]:
        """Parse the JSON returned by the search JavaScript."""
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
        text = m.group(1).strip() if m else raw.strip()
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                if data.get("error") == "captcha":
                    raise RuntimeError(
                        "CNKI captcha detected — solve it in Chrome, then retry"
                    )
                return data.get("results", [])
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return []

    def _parse_detail(self, raw: str) -> dict | None:
        """Parse the JSON returned by the detail page JavaScript."""
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
        text = m.group(1).strip() if m else raw.strip()
        try:
            data = json.loads(text)
            if isinstance(data, dict) and not data.get("error"):
                return data
        except json.JSONDecodeError:
            pass
        return None

    def _parse_authors(self, authors: Any) -> list[str]:
        if isinstance(authors, list):
            return [str(a) for a in authors]
        if isinstance(authors, str) and authors:
            return [a.strip() for a in authors.split(";")]
        return []

    def _parse_keywords(self, keywords: Any) -> list[str]:
        if isinstance(keywords, list):
            return [str(k) for k in keywords]
        if isinstance(keywords, str) and keywords:
            return [k.strip().rstrip(";") for k in keywords.split(";") if k.strip()]
        return []

    def _extract_year(self, result: dict) -> int | None:
        for key in ("year", "date", "publication_date"):
            val = result.get(key, "")
            if isinstance(val, int):
                return val
            if isinstance(val, str) and val:
                try:
                    return int(val[:4])
                except ValueError:
                    pass
        return None

    # CNKI dbcode → human-readable document type
    _DBCODE_TYPE: dict[str, str] = {
        "CJFD": "journal",
        "CJFQ": "journal",
        "CMFD": "master thesis",
        "CDFD": "doctoral thesis",
        "CPFD": "conference paper",
        "SCPD": "conference paper",
        "CCND": "newspaper",
        "CBDMD": "yearbook",
        "SNAD":  "standard",
        "SCOD":  "research result",
    }

    def _extract_document_type(self, url: str) -> str | None:
        """Infer document type from the dbcode parameter in the CNKI detail URL."""
        m = re.search(r"[?&]dbcode=([A-Z]+)", url, re.IGNORECASE)
        if not m:
            return None
        return self._DBCODE_TYPE.get(m.group(1).upper())

    def _build_metadata_line(self, result: dict) -> str:
        parts = []
        if result.get("journal"):
            parts.append(f"Journal: {result['journal']}")
        if result.get("date"):
            parts.append(f"Date: {result['date']}")
        if result.get("citations"):
            parts.append(f"Citations: {result['citations']}")
        if result.get("downloads"):
            parts.append(f"Downloads: {result['downloads']}")
        return " | ".join(parts)

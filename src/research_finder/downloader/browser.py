from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path

import httpx

from ..models import Paper
from ..searcher.mcp_client import MCPClientContext, run_async
from .fulltext import _sanitize_filename

# ── JS to find PDF download URLs on a page ─────────────────────────────────────

_FIND_PDF_JS = """
() => {
    const results = [];
    const seen = new Set();

    function abs(url) {
        if (!url) return '';
        if (/^https?:\\/\\//i.test(url)) return url;
        if (url.startsWith('//')) return window.location.protocol + url;
        if (url.startsWith('/')) return window.location.origin + url;
        return new URL(url, window.location.href).href;
    }

    function add(url, priority, label) {
        url = abs(url);
        if (!url || seen.has(url)) return;
        seen.add(url);
        results.push({url, priority, label: (label || '').trim().slice(0, 80)});
    }

    // Priority 1: direct .pdf links (el.href is always absolute)
    document.querySelectorAll('a[href$=".pdf"], a[href*=".pdf?"], a[href*=".pdf&"]')
        .forEach(a => add(a.href, 1, a.textContent));

    // Priority 2: /pdf/ path links
    document.querySelectorAll('a[href*="/pdf/"]')
        .forEach(a => add(a.href, 2, a.textContent));

    // Priority 3: download / full-text / PDF text elements
    document.querySelectorAll('a, button, [role="button"]').forEach(el => {
        const text = (el.textContent || '').toLowerCase();
        const href = el.href || el.getAttribute('data-url') || el.getAttribute('data-href');
        if (href && /pdf|download|full.text|view.paper|get.pdf/i.test(text))
            add(href, 3, text);
    });

    // Priority 3b: publisher-specific CSS class selectors
    const selectors = [
        // ScienceDirect / Elsevier
        '.pdf-download-btn', '.download-pdf-link', '.PdfButton',
        'a[class*="pdf-download"]', 'a[class*="download-pdf"]',
        'a[class*="pdf-article"]',
        // Springer / Nature
        '.c-pdf-download__link', 'a[data-test="pdf-link"]',
        'a[data-track-action="download PDF"]',
        // IEEE
        '.stats-document-lh-download-pdf', 'a[id*="download-pdf"]',
        // ACS
        '.pdf-download-article-link',
        // Taylor & Francis
        '.show-pdf', 'a[href*="/doi/pdf/"]',
        // Wiley
        'a[href*="/doi/pdfdirect/"]', '.pdf-download-btn',
        // Generic
        '[id*="download-pdf"]', '[id*="pdf-download"]',
        '[class*="download-pdf"]', '[class*="pdf-download"]',
        'a[aria-label*="PDF"]', 'a[aria-label*="Download"]',
        'a[title*="PDF"]', 'a[title*="Download PDF"]',
    ];
    selectors.forEach(sel => {
        try {
            document.querySelectorAll(sel).forEach(el => {
                const href = el.href || el.getAttribute('data-url') || '';
                if (href) add(href, 3, el.textContent);
            });
        } catch (_) {}
    });

    // Priority 4: citation_pdf_url meta (may be relative)
    const meta = document.querySelector('meta[name="citation_pdf_url"]');
    if (meta && meta.content) add(meta.content, 4, 'meta tag');

    // Priority 5: .pdf strings in inline scripts
    try {
        document.querySelectorAll('script:not([src])').forEach(s => {
            for (const m of (s.textContent || '').matchAll(
                /https?:\\/\\/[^"'\\s]+\\.pdf[^"'\\s]*/gi
            )) {
                add(m[0], 5, 'script');
            }
        });
    } catch (_) {}

    results.sort((a, b) => a.priority - b.priority);
    return results;
}
"""

# ── JS to fetch a PDF URL in-browser and return base64 ────────────────────────
#  Placeholder __PDF_URL__ is replaced via string formatting (JSON-encoded).

_FETCH_PDF_JS_TEMPLATE = """
async () => {{
    const url = {};
    try {{
        const resp = await fetch(url, {{ credentials: 'include' }});
        if (!resp.ok) return {{ error: 'HTTP ' + resp.status }};
        const blob = await resp.blob();
        if (blob.size > 20 * 1024 * 1024)
            return {{ error: 'too_large', size: blob.size }};
        return new Promise(resolve => {{
            const reader = new FileReader();
            reader.onloadend = () => resolve({{
                type: blob.type,
                size: blob.size,
                data: reader.result
            }});
            reader.readAsDataURL(blob);
        }});
    }} catch (e) {{
        return {{ error: e.message || String(e) }};
    }}
}}
"""


class BrowserDownloader:
    """Download papers via Chrome browser (institutional access / cookies)."""

    def __init__(self, browser_url: str = "http://127.0.0.1:9222"):
        self._browser_url = browser_url

    # ── public API ────────────────────────────────────────────────────────────

    def download_papers(
        self,
        papers: list[Paper],
        output_dir: Path,
        delay: float = 2.0,
    ) -> dict[str, Path]:
        """Download *missing* papers via browser.  Returns {title: path}."""
        missing = [p for p in papers
                   if (p.url or p.doi) and not (output_dir / (_sanitize_filename(p.title) + ".pdf")).exists()]

        if not missing:
            return {}

        return run_async(self._download_async(missing, output_dir, delay))

    # ── async internals ───────────────────────────────────────────────────────

    async def _download_async(
        self,
        papers: list[Paper],
        output_dir: Path,
        delay: float,
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\nBrowser-based download: attempting {len(papers)} papers ...")
        downloaded: dict[str, Path] = {}

        # Resolve WebSocket endpoint from Chrome debugging URL
        ws_endpoint = self._fetch_ws_endpoint()
        if not ws_endpoint:
            print(f"Browser download skipped (Chrome not reachable at {self._browser_url})")
            print("  Start Chrome with: --headless --remote-debugging-port=9222")
            return downloaded

        client = MCPClientContext(
            command="npx",
            args=["-y", "chrome-devtools-mcp@latest", "--no-usage-statistics",
                  "--wsEndpoint", ws_endpoint],
        )
        try:
            await client.connect()
        except Exception as exc:
            print(f"Browser download skipped (Chrome MCP connection failed): {exc}")
            return downloaded

        try:
            for i, paper in enumerate(papers):
                stem = _sanitize_filename(paper.title)
                dest = output_dir / f"{stem}.pdf"
                if dest.exists():
                    downloaded[paper.title] = dest
                    continue

                if i > 0 and delay > 0:
                    time.sleep(delay)

                print(f"  [{i + 1}/{len(papers)}] {paper.title[:70]} ...")
                result = await self._download_one(client, paper, dest)
                if result:
                    downloaded[paper.title] = result
                    size_kb = result.stat().st_size / 1024
                    print(f"    -> OK  {result.name} ({size_kb:.0f} KB)")
                else:
                    print(f"    -> FAIL (no PDF found via browser)")
        finally:
            await client.disconnect()

        print(f"Browser download: {len(downloaded)} ok, "
              f"{len(papers) - len(downloaded)} failed.")
        return downloaded

    def _fetch_ws_endpoint(self) -> str | None:
        """Fetch the WebSocket debugger URL from Chrome's HTTP endpoint."""
        try:
            resp = httpx.get(
                f"{self._browser_url}/json/version", timeout=5,
                headers={"User-Agent": "curl/8.0"},
            )
            resp.raise_for_status()
            return resp.json().get("webSocketDebuggerUrl")
        except Exception:
            return None

    async def _download_one(
        self, client: MCPClientContext, paper: Paper, dest: Path
    ) -> Path | None:
        """Try all strategies for a single paper."""
        url = paper.url or (f"https://doi.org/{paper.doi}" if paper.doi else None)
        if not url:
            return None

        # ── Strategy A: extract PDF URLs from DOM, try httpx ──────────────
        pdf_urls = await self._find_pdf_urls(client, url)
        for pdf_url in pdf_urls[:5]:  # try up to 5 candidates
            result = self._http_download(pdf_url, dest)
            if result:
                return result

        # ── Strategy B: in-browser fetch (uses browser cookies) ───────────
        if pdf_urls:
            result = await self._browser_fetch_pdf(client, pdf_urls[0], dest)
            if result:
                return result

        # ── Strategy C: navigate directly to PDF URL in browser, then
        #    check network requests for the actual PDF response
        if pdf_urls:
            for pdf_url in pdf_urls[:3]:
                result = await self._browser_navigate_and_detect(client, pdf_url, dest)
                if result:
                    return result

        return None

    # ── Strategy A helpers ────────────────────────────────────────────────────

    async def _find_pdf_urls(self, client: MCPClientContext, url: str) -> list[str]:
        """Navigate to *url*, run DOM inspection JS, return candidate PDF URLs."""
        try:
            await client.call_tool("navigate_page", {"type": "url", "url": url})
            # Allow redirect + JS rendering
            await self._sleep(3)
            raw = await client.call_tool("evaluate_script", {"function": _FIND_PDF_JS})
            parsed = self._unwrap_result(raw)
            items = json.loads(parsed) if parsed else []
            return [item["url"] for item in items]
        except Exception as exc:
            print(f"    [browser/find] navigation/parse error: {exc}")
            return []

    @staticmethod
    def _http_download(pdf_url: str, dest: Path) -> Path | None:
        """Try a direct httpx download of *pdf_url*."""
        try:
            resp = httpx.get(
                pdf_url,
                follow_redirects=True,
                timeout=30,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
                    ),
                },
            )
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "pdf" not in ct and "octet-stream" not in ct:
                return None
            dest.write_bytes(resp.content)
            return dest
        except Exception:
            return None

    # ── Strategy B helpers ────────────────────────────────────────────────────

    async def _browser_fetch_pdf(
        self, client: MCPClientContext, pdf_url: str, dest: Path
    ) -> Path | None:
        """Fetch *pdf_url* in-browser via JS fetch() + base64-encode result."""
        try:
            url_json = json.dumps(pdf_url)
            js = _FETCH_PDF_JS_TEMPLATE.format(url_json)
            raw = await client.call_tool("evaluate_script", {"function": js})
            parsed = self._unwrap_result(raw)
            if not parsed:
                return None

            data = json.loads(parsed)
            if "error" in data:
                return None

            pdf_bytes = base64.b64decode(data["data"].split(",", 1)[1])
            if not pdf_bytes:
                return None

            dest.write_bytes(pdf_bytes)
            return dest
        except Exception as exc:
            print(f"    [browser/fetch] error: {exc}")
            return None

    # ── Strategy C helpers ────────────────────────────────────────────────────

    async def _browser_navigate_and_detect(
        self, client: MCPClientContext, pdf_url: str, dest: Path
    ) -> Path | None:
        """Navigate to *pdf_url* directly.  If Chrome renders it, use
        list_network_requests to find the PDF response body and save it."""
        try:
            await client.call_tool("navigate_page", {"type": "url", "url": pdf_url})
            await self._sleep(3)

            # Try extracting PDF via in-page JS (for pages that embed PDFs)
            raw = await client.call_tool("evaluate_script", {"function": _FIND_PDF_JS})
            parsed = self._unwrap_result(raw)
            if parsed:
                items = json.loads(parsed)
                for item in items:
                    result = self._http_download(item["url"], dest)
                    if result:
                        return result

            # Fallback: check network requests for PDF content
            try:
                raw = await client.call_tool("list_network_requests", {})
                for req in self._parse_network_requests(raw):
                    if req.get("url") and (
                        ".pdf" in req["url"] or req.get("mimeType") == "application/pdf"
                    ):
                        result = self._http_download(req["url"], dest)
                        if result:
                            return result
            except Exception:
                pass

            return None
        except Exception as exc:
            print(f"    [browser/navigate] error: {exc}")
            return None

    # ── utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _unwrap_result(raw: str) -> str | None:
        """Strip markdown code fences / prefixes that chrome-devtools-mcp
        may wrap evaluate_script output in."""
        if not raw:
            return None
        # Try regex for ``` fence (same approach as cnki_searcher.py)
        m = re.search(r"```(?:json|javascript|js)?\s*\n?(.*?)```", raw, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # Fallback: find first JSON array/object, strip any preceding text
        text = raw.strip()
        first_json = -1
        for start_char in ("[", "{"):
            idx = text.find(start_char)
            if idx != -1 and (first_json == -1 or idx < first_json):
                first_json = idx
        if first_json > 0:
            text = text[first_json:]
        return text.strip()

    @staticmethod
    def _parse_network_requests(raw: str) -> list[dict]:
        """Parse the output of list_network_requests into a list of dicts."""
        try:
            text = BrowserDownloader._unwrap_result(raw) or raw
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        return []

    @staticmethod
    async def _sleep(seconds: float) -> None:
        import asyncio
        await asyncio.sleep(seconds)

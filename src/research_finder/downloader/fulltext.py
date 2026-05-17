from __future__ import annotations

import os
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

import httpx

from ..models import Paper


def _sanitize_filename(title: str) -> str:
    """Sanitize a paper title into a filesystem-safe stem (same convention as Zotero exporter)."""
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)
    return safe[:80].strip()


def download_papers(
    papers: list[Paper],
    output_dir: Path,
    delay: float = 1.0,
    elsevier_delay: float = 2.0,
    wiley_delay: float = 2.0,
    springer_delay: float = 2.0,
    annas_delay: float = 3.0,
    browser_download: bool = False,
    elsevier_download: bool = True,
    wiley_download: bool = True,
    springer_download: bool = True,
) -> dict[str, Path]:
    """Download PDFs for a list of papers using a tiered strategy:

    Phase 1   — Direct HTTP (papers with ``pdf_url`` set)
    Phase 1.5 — Elsevier Full Text API (DOI-based; works from institutional IPs)
    Phase 1.6 — Wiley TDM API (DOI-based; requires WILEY_TDM_TOKEN + institutional IP)
    Phase 1.7 — Springer Nature OA API (DOI-based; SPRINGER_OA_API_KEY; OA papers only)
    Phase 2   — Browser-based download via Chrome DevTools (institutional cookies)
    Phase 3   — Anna's Archive CLI fallback

    Each phase only attempts papers not yet downloaded.  All phases are
    idempotent — files already on disk are skipped.

    Args:
        papers:           List of Paper objects to download.
        output_dir:       Directory to save PDFs.
        delay:            Seconds between direct HTTP requests (default 1.0).
        elsevier_delay:   Seconds between Elsevier API requests (default 2.0).
        wiley_delay:      Seconds between Wiley TDM API requests (default 2.0).
        annas_delay:      Seconds between Anna's Archive attempts (default 3.0).
        browser_download: Enable Chrome browser fallback (needs remote debug port).
        elsevier_download: Enable Elsevier Full Text API phase (default True).
        wiley_download:    Enable Wiley TDM API phase (default True).
        springer_download: Enable Springer Nature OA API phase (default True).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded: dict[str, Path] = {}
    skipped = 0
    http_ok = 0
    http_fail = 0

    # ── Phase 1: direct HTTP download for papers with pdf_url ──────────────
    downloadable = [p for p in papers if p.pdf_url]
    if downloadable:
        print(f"Phase 1: direct HTTP — {len(downloadable)} papers with pdf_url ...")
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            for i, paper in enumerate(downloadable):
                stem = _sanitize_filename(paper.title)
                dest = output_dir / f"{stem}.pdf"

                if dest.exists():
                    skipped += 1
                    downloaded[paper.title] = dest
                    continue

                if i > 0 and delay > 0:
                    time.sleep(delay)

                try:
                    resp = client.get(paper.pdf_url)
                    resp.raise_for_status()
                    ct = resp.headers.get("content-type", "")
                    if "pdf" not in ct and "octet-stream" not in ct:
                        http_fail += 1
                        print(f"  [{i+1}/{len(downloadable)}] SKIP (content-type: {ct}): {paper.title[:60]}")
                        continue
                    dest.write_bytes(resp.content)
                    downloaded[paper.title] = dest
                    http_ok += 1
                    size_kb = len(resp.content) / 1024
                    print(f"  [{i+1}/{len(downloadable)}] OK ({size_kb:.0f} KB): {paper.title[:60]}")
                except httpx.HTTPError as exc:
                    http_fail += 1
                    print(f"  [{i+1}/{len(downloadable)}] FAIL: {paper.title[:60]} — {exc}")

        print(f"  → {http_ok} ok, {skipped} existing, {http_fail} failed.")
    else:
        print("Phase 1: no papers with direct pdf_url — skipping.")

    # ── Phase 1.5: Elsevier Full Text API (institutional IP or OA) ─────────
    if elsevier_download:
        missing = [p for p in papers if p.title not in downloaded and p.doi]
        if missing:
            _elsevier_download(missing, output_dir, downloaded, delay=elsevier_delay)

    # ── Phase 1.6: Wiley TDM API (TDM_API_TOKEN + institutional IP) ────────
    if wiley_download:
        missing = [p for p in papers if p.title not in downloaded and p.doi]
        if missing:
            _wiley_download(missing, output_dir, downloaded, delay=wiley_delay)

    # ── Phase 1.7: Springer Nature OA API ─────────────────────────────────
    if springer_download:
        missing = [p for p in papers if p.title not in downloaded and p.doi]
        if missing:
            _springer_oa_download(missing, output_dir, downloaded, delay=springer_delay)

    # ── Phase 2: browser-based download (institutional access via Chrome) ──
    if browser_download:
        missing = [p for p in papers if p.title not in downloaded]
        if missing:
            from .browser import BrowserDownloader
            browser = BrowserDownloader()
            result = browser.download_papers(missing, output_dir)
            downloaded.update(result)
            print(f"After browser download: {len(downloaded)} total downloaded.")

    # ── Phase 3: Anna's Archive fallback ───────────────────────────────────
    missing = [p for p in papers if p.title not in downloaded]
    if missing:
        _annas_fallback(missing, output_dir, downloaded, delay=annas_delay)

    return downloaded


# ---------------------------------------------------------------------------
# Elsevier Full Text API
# ---------------------------------------------------------------------------

_ELSEVIER_FULLTEXT_URL = "https://api.elsevier.com/content/article/doi/{}"


def _elsevier_download(
    papers: list[Paper],
    output_dir: Path,
    downloaded: dict[str, Path],
    delay: float = 2.0,
) -> None:
    """Download PDFs via the Elsevier Full Text API using the SCOPUS_API_KEY.

    Works automatically from institutional IP addresses (no extra token needed).
    Only covers ScienceDirect/Elsevier journals — non-Elsevier DOIs return 404.
    Rate: max 9 req/s; we use a conservative inter-request delay (default 2s).
    """
    api_key = os.environ.get("SCOPUS_API_KEY", "")
    if not api_key:
        print("Phase 1.5: SCOPUS_API_KEY not set — skipping Elsevier download.")
        return

    headers = {"X-ELS-APIKey": api_key, "Accept": "application/pdf"}
    ok = 0
    skip = 0
    fail = 0

    print(f"Phase 1.5: Elsevier Full Text API — {len(papers)} papers with DOI ...")
    with httpx.Client(headers=headers, follow_redirects=True, timeout=60.0) as client:
        for i, paper in enumerate(papers):
            stem = _sanitize_filename(paper.title)
            dest = output_dir / f"{stem}.pdf"

            if dest.exists():
                downloaded[paper.title] = dest
                skip += 1
                continue

            if i > 0 and delay > 0:
                time.sleep(delay)

            try:
                url = _ELSEVIER_FULLTEXT_URL.format(paper.doi)
                resp = client.get(url)

                if resp.status_code == 404:
                    # Non-Elsevier journal — silently skip, no point retrying
                    fail += 1
                    continue
                if resp.status_code == 403:
                    print(f"  [elsevier] 403 (no entitlement): {paper.title[:60]}")
                    fail += 1
                    continue

                resp.raise_for_status()
                ct = resp.headers.get("content-type", "")
                if "pdf" not in ct and "octet-stream" not in ct:
                    fail += 1
                    continue

                dest.write_bytes(resp.content)
                downloaded[paper.title] = dest
                ok += 1
                size_kb = len(resp.content) / 1024
                print(f"  [elsevier] OK ({size_kb:.0f} KB): {paper.title[:60]}")

            except httpx.HTTPError as exc:
                fail += 1
                print(f"  [elsevier] FAIL: {paper.title[:60]} — {exc}")

    print(f"  → {ok} ok, {skip} existing, {fail} failed/non-Elsevier.")


# ---------------------------------------------------------------------------
# Wiley TDM API
# ---------------------------------------------------------------------------

_WILEY_TDM_URL = "https://api.wiley.com/onlinelibrary/tdm/v1/articles/{}"

# Wiley DOI prefixes — all Wiley journals use these
_WILEY_DOI_PREFIXES = (
    "10.1002/", "10.1111/", "10.1113/", "10.1046/",
    "10.1034/", "10.1055/", "10.1065/", "10.1079/",
    "10.1197/", "10.1256/", "10.1300/", "10.1301/",
    "10.1348/", "10.1359/", "10.1365/", "10.1394/",
    "10.1400/", "10.1460/", "10.1501/", "10.1525/",
    "10.1576/", "10.1592/", "10.1684/", "10.1741/",
    "10.1749/", "10.1756/", "10.1763/", "10.1771/",
    "10.1780/", "10.1890/", "10.1897/", "10.1898/",
    "10.1890/", "10.2903/", "10.3322/", "10.4319/",
)


def _is_wiley_doi(doi: str) -> bool:
    return any(doi.startswith(p) for p in _WILEY_DOI_PREFIXES)


def _wiley_download(
    papers: list[Paper],
    output_dir: Path,
    downloaded: dict[str, Path],
    delay: float = 2.0,
) -> None:
    """Download PDFs via the Wiley TDM API using TDM_API_TOKEN.

    Endpoint: GET https://api.wiley.com/onlinelibrary/tdm/v1/articles/{doi}
    Auth: Bearer token in Authorization header.
    Access: also IP-based — must run from a registered institutional IP.
    Only attempts papers with Wiley DOIs (10.1002/, 10.1111/, etc.).
    """
    token = os.environ.get("WILEY_TDM_TOKEN", "")
    if not token:
        print("Phase 1.6: WILEY_TDM_TOKEN not set — skipping Wiley TDM download.")
        return

    wiley_papers = [p for p in papers if p.doi and _is_wiley_doi(p.doi)]
    if not wiley_papers:
        print("Phase 1.6: no Wiley DOIs among remaining papers — skipping.")
        return

    headers = {
        "Wiley-TDM-Client-Token": token,
        "User-Agent": "TDMClient/1.0.0",
        "Accept": "application/pdf",
    }
    ok = 0
    skip = 0
    fail = 0

    print(f"Phase 1.6: Wiley TDM API — {len(wiley_papers)} Wiley-DOI papers ...")
    with httpx.Client(headers=headers, follow_redirects=True, timeout=60.0) as client:
        for i, paper in enumerate(wiley_papers):
            stem = _sanitize_filename(paper.title)
            dest = output_dir / f"{stem}.pdf"

            if dest.exists():
                downloaded[paper.title] = dest
                skip += 1
                continue

            if i > 0 and delay > 0:
                time.sleep(delay)

            try:
                encoded_doi = urllib.parse.quote(paper.doi, safe="")
                url = _WILEY_TDM_URL.format(encoded_doi)
                resp = client.get(url)

                if resp.status_code == 404:
                    fail += 1
                    continue
                if resp.status_code == 403:
                    print(f"  [wiley] 403 (no entitlement): {paper.title[:60]}")
                    fail += 1
                    continue
                if resp.status_code == 429:
                    print("  [wiley] 429 rate-limited — sleeping 30s ...")
                    time.sleep(30)
                    resp = client.get(url)  # url already has encoded DOI

                resp.raise_for_status()
                ct = resp.headers.get("content-type", "")
                if "pdf" not in ct and "octet-stream" not in ct:
                    fail += 1
                    continue

                dest.write_bytes(resp.content)
                downloaded[paper.title] = dest
                ok += 1
                size_kb = len(resp.content) / 1024
                print(f"  [wiley] OK ({size_kb:.0f} KB): {paper.title[:60]}")

            except httpx.HTTPError as exc:
                fail += 1
                print(f"  [wiley] FAIL: {paper.title[:60]} — {exc}")

    print(f"  → {ok} ok, {skip} existing, {fail} failed/non-entitled.")


# ---------------------------------------------------------------------------
# Springer Nature Open Access API
# ---------------------------------------------------------------------------

_SPRINGER_META_URL = "https://api.springernature.com/meta/v2/json"
_SPRINGER_DOI_PREFIXES = ("10.1007/", "10.1038/", "10.1057/", "10.1140/",
                           "10.1208/", "10.1245/", "10.1251/", "10.1385/",
                           "10.1617/", "10.1891/", "10.3758/", "10.3758/")


def _is_springer_doi(doi: str) -> bool:
    return any(doi.startswith(p) for p in _SPRINGER_DOI_PREFIXES)


def _springer_oa_download(
    papers: list[Paper],
    output_dir: Path,
    downloaded: dict[str, Path],
    delay: float = 2.0,
) -> None:
    """Download OA PDFs via the Springer Nature Meta API pdf openurl.

    Strategy: for each remaining Springer DOI, query the Meta API to get the
    pdf openurl and check whether the paper is OA. If OA, follow the openurl
    (which redirects through link.springer.com to the real PDF).

    Auth: ``?api_key=<SPRINGER_META_API_KEY>`` on the Meta API query.
    Only Springer/Nature DOIs are attempted (10.1007/, 10.1038/, etc.).
    Non-OA papers are skipped after the Meta check.
    """
    api_key = os.environ.get("SPRINGER_META_API_KEY", "")
    if not api_key:
        print("Phase 1.7: SPRINGER_META_API_KEY not set — skipping Springer OA download.")
        return

    springer_papers = [p for p in papers if p.doi and _is_springer_doi(p.doi)]
    if not springer_papers:
        print("Phase 1.7: no Springer DOIs among remaining papers — skipping.")
        return

    ok = 0
    skip = 0
    fail = 0

    print(f"Phase 1.7: Springer OA (via Meta API) — {len(springer_papers)} Springer-DOI papers ...")
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        for i, paper in enumerate(springer_papers):
            stem = _sanitize_filename(paper.title)
            dest = output_dir / f"{stem}.pdf"

            if dest.exists():
                downloaded[paper.title] = dest
                skip += 1
                continue

            if i > 0 and delay > 0:
                time.sleep(delay)

            try:
                # Step 1: look up OA status + pdf openurl from Meta API
                meta_resp = client.get(
                    _SPRINGER_META_URL,
                    params={"q": f"doi:{paper.doi}", "api_key": api_key, "p": 1},
                )
                meta_resp.raise_for_status()
                records = meta_resp.json().get("records", [])
                if not records:
                    fail += 1
                    continue

                rec = records[0]
                if rec.get("openaccess", "false") != "true":
                    fail += 1  # not OA — skip quietly
                    continue

                # Step 2: get pdf openurl from record
                pdf_openurl = None
                for u in rec.get("url") or []:
                    if u.get("format") == "pdf" and u.get("value"):
                        pdf_openurl = u["value"]
                        break
                if not pdf_openurl:
                    fail += 1
                    continue

                # Step 3: download — link.springer.com/openurl/pdf redirects to real PDF
                resp = client.get(pdf_openurl)
                resp.raise_for_status()
                ct = resp.headers.get("content-type", "")
                if "pdf" not in ct and "octet-stream" not in ct:
                    fail += 1
                    continue

                dest.write_bytes(resp.content)
                downloaded[paper.title] = dest
                ok += 1
                size_kb = len(resp.content) / 1024
                print(f"  [springer] OK ({size_kb:.0f} KB): {paper.title[:60]}")

            except httpx.HTTPError as exc:
                fail += 1
                print(f"  [springer] FAIL: {paper.title[:60]} — {exc}")

    print(f"  → {ok} ok, {skip} existing, {fail} non-OA/failed.")


# ---------------------------------------------------------------------------
# Anna's Archive CLI fallback
# ---------------------------------------------------------------------------

_ANNAS_BIN = "annas-mcp"


def _annas_bin_path() -> str:
    """Return the annas-mcp binary path, preferring the venv-local copy."""
    venv_bin = Path(__file__).resolve().parents[3] / ".venv" / "bin" / _ANNAS_BIN
    if venv_bin.exists():
        return str(venv_bin)
    return _ANNAS_BIN


def _annas_env(download_dir: Path) -> dict[str, str] | None:
    """Build env dict for annas-mcp.  Returns None if ANNAS_SECRET_KEY is unset."""
    env = os.environ.copy()
    key = env.get("ANNAS_SECRET_KEY")
    if not key:
        return None
    env["ANNAS_DOWNLOAD_PATH"] = str(Path(download_dir).resolve())
    return env


def _annas_fallback(
    papers: list[Paper],
    output_dir: Path,
    downloaded: dict[str, Path],
    delay: float = 3.0,
) -> None:
    """Try to download missing papers via Anna's Archive CLI.

    Strategy per paper:
      1. If paper has a DOI → ``article-download <doi>``
      2. If that fails or no DOI → ``article-search "<title>"`` → parse
         results → download first match via DOI if available
    """
    env = _annas_env(output_dir)
    if env is None:
        print("Anna's Archive fallback skipped (ANNAS_SECRET_KEY not set).")
        return

    bin_path = _annas_bin_path()
    missing = [p for p in papers if p.title not in downloaded]
    if not missing:
        return

    print(f"\nAnna's Archive fallback: attempting {len(missing)} missing papers ...")
    annas_ok = 0
    annas_skip = 0

    for idx, paper in enumerate(missing):
        stem = _sanitize_filename(paper.title)
        dest = output_dir / f"{stem}.pdf"
        if dest.exists():
            downloaded[paper.title] = dest
            annas_skip += 1
            continue

        if idx > 0 and delay > 0:
            time.sleep(delay)

        # Step 1: try DOI download
        if paper.doi:
            ok = _annas_article_download(bin_path, paper.doi, dest, env)
            if ok:
                downloaded[paper.title] = dest
                annas_ok += 1
                print(f"  [annas/doi] OK: {paper.title[:60]}")
                continue

        # Step 2: search by title, then download best match
        ok = _annas_search_and_download(bin_path, paper.title, dest, env)
        if ok:
            downloaded[paper.title] = dest
            annas_ok += 1
            print(f"  [annas/search] OK: {paper.title[:60]}")
        else:
            annas_skip += 1

    print(f"Anna's Archive: {annas_ok} downloaded, "
          f"{annas_skip} not found, out of {len(missing)} missing.")


def _annas_article_download(
    bin_path: str, doi: str, dest: Path, env: dict[str, str]
) -> bool:
    """Run ``annas-mcp article-download <doi>`` and check if a file landed."""
    try:
        dl_dir = Path(env["ANNAS_DOWNLOAD_PATH"])
        before = {f.name for f in dl_dir.iterdir() if f.is_file()}
        subprocess.run(
            [bin_path, "article-download", doi],
            env=env, capture_output=True, text=True, timeout=120,
        )
        time.sleep(1.5)
        for f in dl_dir.iterdir():
            if f.is_file() and f.name not in before:
                # Accept any format (pdf, ehtml, epub, djvu, …); rename dest to match
                actual_dest = dest.with_suffix(f.suffix)
                actual_dest.write_bytes(f.read_bytes())
                f.unlink()
                return True
        if dest.exists() and dest.stat().st_size > 0:
            return True
        return False
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"  [annas/doi] error for {doi}: {exc}")
        return False


def _annas_web_search_doi(title: str, base_url: str = "annas-archive.gl") -> str | None:
    """Search Anna's Archive website directly and return the first DOI found.

    The annas-mcp CLI article-search has poor recall; scraping the web search
    returns the same results the browser sees and surfaces DOIs reliably.
    Uses the first ~60 chars of the title to avoid query-length issues.
    """
    try:
        import httpx as _httpx
        query = title[:60]
        url = f"https://{base_url}/search?q={_httpx.URL('', params={'q': query}).params}&sort="
        resp = _httpx.get(
            f"https://{base_url}/search",
            params={"q": query, "sort": ""},
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        # Extract DOIs from page — deduplicate preserving order
        raw_dois = re.findall(r'(10\.\d{4,9}/[^\s"\'<>&?#|]+)', resp.text)
        seen: set[str] = set()
        for doi in raw_dois:
            doi = doi.rstrip(".,;)\"/")
            if doi not in seen and len(doi) > 8:
                seen.add(doi)
                return doi
    except Exception:
        pass
    return None


def _annas_search_and_download(
    bin_path: str, title: str, dest: Path, env: dict[str, str]
) -> bool:
    """Search Anna's Archive by title, find DOI via web scrape, then download."""
    base_url = os.environ.get("ANNAS_BASE_URL", "annas-archive.gl")
    doi = _annas_web_search_doi(title, base_url)
    if doi:
        return _annas_article_download(bin_path, doi, dest, env)
    return False


def _annas_book_search_download(
    bin_path: str, title: str, dest: Path, env: dict[str, str]
) -> bool:
    """Search books by title, parse MD5, download via book-download."""
    try:
        r = subprocess.run(
            [bin_path, "book-search", title[:200]],
            env=env, capture_output=True, text=True, timeout=60,
        )
        output = r.stdout.strip()
        if not output or "no books found" in output.lower():
            return False

        # Look for MD5 hash in output (32 hex chars)
        md5_match = re.search(r'[0-9a-fA-F]{32}', output)
        if not md5_match:
            return False

        md5 = md5_match.group(0)
        safe_name = _sanitize_filename(title) + ".pdf"
        r2 = subprocess.run(
            [bin_path, "book-download", md5, safe_name],
            env=env, capture_output=True, text=True, timeout=120,
        )
        dl_dir = Path(env["ANNAS_DOWNLOAD_PATH"])
        time.sleep(0.5)
        for f in dl_dir.iterdir():
            if f.is_file() and f.stem in safe_name or safe_name in f.name:
                actual_dest = dest.with_suffix(f.suffix)
                actual_dest.write_bytes(f.read_bytes())
                f.unlink()
                return True
        return False
    except (subprocess.TimeoutExpired, OSError):
        return False

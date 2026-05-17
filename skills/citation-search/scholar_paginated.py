"""Paginated Google Scholar fetcher.

Workaround for the google_scholar_server MCP server, which only fetches
Scholar's first results page (~10 hits per query). This module iterates
&start=0,10,20,... up to a target count, parsing the same DOM the MCP
server parses.

Use when you need >10 results per query. Google Scholar throttles hard:
keep delays >= 6s between pages, expect 429s, and don't hammer.
"""
from __future__ import annotations
import re, time, requests
from bs4 import BeautifulSoup
from research_finder.searcher.base import Paper

_HDR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _parse_authors_year(meta: str) -> tuple[list[str], int | None, str]:
    # gs_a is like: "A Author, B Author - Journal Name, 2021 - publisher.com"
    parts = meta.split(" - ")
    authors = [a.strip() for a in parts[0].split(",") if a.strip()] if parts else []
    publication = ""
    year: int | None = None
    if len(parts) >= 2:
        mid = parts[1]
        m = _YEAR_RE.search(mid)
        if m:
            year = int(m.group(0))
            publication = mid[: m.start()].rstrip(", ").strip()
        else:
            publication = mid.strip()
    return authors, year, publication


def _parse_page(html: str, query: str) -> list[Paper]:
    soup = BeautifulSoup(html, "html.parser")
    papers: list[Paper] = []
    for item in soup.find_all("div", class_="gs_ri"):
        title_tag = item.find("h3", class_="gs_rt")
        if not title_tag:
            continue
        title = title_tag.get_text(" ", strip=True)
        # strip leading "[PDF][C]" type prefixes scholarly adds
        title = re.sub(r"^\[[A-Z]+\]\s*", "", title)
        link_el = title_tag.find("a")
        url = link_el["href"] if link_el and link_el.has_attr("href") else None
        abs_tag = item.find("div", class_="gs_rs")
        abstract = abs_tag.get_text(" ", strip=True) if abs_tag else ""
        meta_tag = item.find("div", class_="gs_a")
        authors, year, publication = _parse_authors_year(
            meta_tag.get_text(" ", strip=True) if meta_tag else ""
        )
        papers.append(Paper(
            title=title, authors=authors, abstract=abstract, year=year,
            url=url, publication=publication, retrieval_query=query,
        ))
    return papers


def search_scholar_paginated(
    query: str, target: int = 50, page_delay: float = 8.0,
    max_pages: int = 10, on_429_backoff: float = 60.0,
) -> list[Paper]:
    """Fetch up to `target` Scholar results for `query` by paginating.

    Returns deduped Paper list (by title). Stops on empty page,
    repeated 429s, or after max_pages.
    """
    collected: dict[str, Paper] = {}
    page = 0
    while page < max_pages:
        start = page * 10
        url = f"https://scholar.google.com/scholar?q={query.replace(' ', '+')}&start={start}"
        attempt = 0
        while True:
            r = requests.get(url, headers=_HDR, timeout=25)
            if r.status_code == 200:
                break
            if r.status_code == 429:
                attempt += 1
                print(f"  [scholar] 429 at start={start} (retry {attempt}, sleep {on_429_backoff}s)")
                if attempt >= 3:
                    print("  [scholar] giving up after 3x 429 on same page")
                    return list(collected.values())[:target]
                time.sleep(on_429_backoff)
                continue
            print(f"  [scholar] status={r.status_code} at start={start} — stopping")
            return list(collected.values())[:target]
        page_papers = _parse_page(r.text, query)
        if not page_papers:
            print(f"  [scholar] empty page at start={start} — stopping")
            break
        for p in page_papers:
            collected.setdefault(p.title.lower(), p)
        print(f"  [scholar] start={start}: +{len(page_papers)} (total unique={len(collected)})")
        if len(collected) >= target:
            break
        page += 1
        time.sleep(page_delay)
    return list(collected.values())[:target]


if __name__ == "__main__":
    import argparse, yaml
    from pathlib import Path
    import dotenv; dotenv.load_dotenv()
    from openpyxl import Workbook
    from research_finder.embedder import get_embedder
    from research_finder.ranker import rank_papers
    from research_finder.input_store import InputStore

    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--target", type=int, default=50)
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--threshold", type=float, default=0.0)
    ap.add_argument("--page-delay", type=float, default=8.0)
    ap.add_argument("--query", action="append", required=True,
                    help="repeatable; one per base query")
    args = ap.parse_args()

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    store = InputStore(cfg)
    text_emb, text = store.load(args.input)
    print(f"[input] {args.input}: {len(text)} chars, dim={text_emb.shape}")

    all_papers: dict[str, Paper] = {}
    for q in args.query:
        print(f"\n[query] {q}")
        for p in search_scholar_paginated(q, target=args.target, page_delay=args.page_delay):
            all_papers.setdefault(p.title.lower(), p)
        print(f"  cumulative unique={len(all_papers)}")
        # cross-query delay
        time.sleep(args.page_delay)

    papers = list(all_papers.values())
    print(f"\n[total] {len(papers)} unique papers across {len(args.query)} queries")

    embedder = get_embedder(cfg)
    embs = embedder.embed_batch([f"{p.title}. {p.abstract or ''}" for p in papers])
    ranked = rank_papers(text_emb, embs, papers, top_n=args.top_n, threshold=args.threshold)
    print(f"[rank] kept {len(ranked)} after top_n={args.top_n}, threshold={args.threshold}")

    out_dir = Path("output") / args.input / f"Scholar_paginated_target{args.target}_select{args.top_n}"
    out_dir.mkdir(parents=True, exist_ok=True)
    xlsx = out_dir / f"{out_dir.name}.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = "Results"
    ws.append(["rank","score","title","authors","year","publication",
               "abstract","url","retrieval_query"])
    for i, p in enumerate(ranked, 1):
        ws.append([i, round(p.score,4), p.title, ", ".join(p.authors or []), p.year,
                   getattr(p,"publication","") or "", p.abstract or "", p.url or "",
                   getattr(p,"retrieval_query","") or ""])
    wb.save(xlsx)
    print(f"[xlsx] {xlsx}")
    for i, p in enumerate(ranked, 1):
        print(f"  #{i:2d} [{p.score:.3f}] {p.title[:90]}")

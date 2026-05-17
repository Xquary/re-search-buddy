"""End-to-end test: Semantic Scholar search → embed → rank → output top N.

Queries are generated from the input text via the LLM KeywordExtractor (gpt-4o-mini).
Pass ``--input <name>`` to load a pre-computed embedding from ``input/embeddings/``
and derive queries from that file's text. Run ``scan_input.py`` first.
"""
import argparse
from pathlib import Path

import dotenv
dotenv.load_dotenv()
from openpyxl import Workbook

from research_finder.searcher.semantic_scholar_searcher import SemanticScholarSearcher
from research_finder.embedder import get_embedder
from research_finder.ranker import rank_papers
from research_finder.extractor.keyword_extractor import KeywordExtractor
from research_finder.input_store import InputStore
from research_finder.filters import filter_by_year
from research_finder.downloader.fulltext import download_papers
import yaml

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--input", dest="input_name", default=None)
parser.add_argument("--year-from", dest="year_from", type=int, default=None)
parser.add_argument("--year-to", dest="year_to", type=int, default=None)
parser.add_argument("--max-per-query", dest="max_per_query", type=int, default=50)
parser.add_argument("--top-n", dest="top_n", type=int, default=10)
_args, _ = parser.parse_known_args()

# ── 1. Config & input text ─────────────────────────────────────────────────
with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

cfg.setdefault("search", {}).setdefault("semantic_scholar", {})["max_results"] = _args.max_per_query
cfg.setdefault("embedding", {})["provider"] = "api"
if _args.year_from is not None:
    cfg["search"]["year_from"] = _args.year_from
if _args.year_to is not None:
    cfg["search"]["year_to"] = _args.year_to

TEXT = ""
cached_text_emb = None
if _args.input_name:
    store = InputStore(cfg)
    cached_text_emb, TEXT = store.load(_args.input_name)
    print(f"[input_store] loaded '{_args.input_name}': {len(TEXT)} chars, "
          f"embedding shape={cached_text_emb.shape}\n")
else:
    TEXT = (
        "Recent study argues that steel decarbonization should be understood as a broader "
        "industrial transformation rather than a narrow emissions problem."
    )

# ── 2. Generate queries via LLM ────────────────────────────────────────────
print("=" * 80)
print("STEP 0: Generating search queries from input text")
print("=" * 80)

extractor = KeywordExtractor(cfg)
QUERIES = extractor.extract(TEXT)
print(f"Generated {len(QUERIES)} queries:")
for q in QUERIES:
    print(f"  - {q}")
print()

# ── 3. Search ──────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 1: Searching Semantic Scholar")
print("=" * 80)

print(f"Max results per query: {_args.max_per_query}")
if _args.year_from or _args.year_to:
    print(f"Year filter: [{_args.year_from or '-'}, {_args.year_to or '-'}]")

searcher = SemanticScholarSearcher(cfg)
papers = searcher.search(QUERIES)
print(f"Found {len(papers)} unique papers from Semantic Scholar")
if _args.year_from is not None or _args.year_to is not None:
    before = len(papers)
    papers = filter_by_year(papers, _args.year_from, _args.year_to)
    print(f"  year filter kept {len(papers)} / {before}")
print()

if not papers:
    print("No papers found. Exiting.")
    raise SystemExit(0)

for i, p in enumerate(papers[:5], 1):
    print(f"  {i}. {p.title}")
    if p.abstract:
        print(f"     {p.abstract[:120]}...")
print(f"  ... and {len(papers) - 5} more\n" if len(papers) > 5 else "\n")

# ── 4. Embed ───────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 2: Embedding text and paper metadata")
print("=" * 80)

embedder = get_embedder(cfg)
if cached_text_emb is not None:
    text_emb = cached_text_emb
    print(f"Text embedding: shape={text_emb.shape} (from input_store cache)")
else:
    text_emb = embedder.embed_single(TEXT)
    print(f"Text embedding: shape={text_emb.shape}")

paper_texts = [f"{p.title} {p.abstract or ''}" for p in papers]
paper_embs = embedder.embed_batch(paper_texts)
print(f"Paper embeddings: shape={paper_embs.shape}\n")

# ── 5. Rank ────────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 3: Ranking by cosine similarity")
print("=" * 80)

ranked = rank_papers(text_emb, paper_embs, papers, top_n=_args.top_n, threshold=0.0)
print(f"Top {len(ranked)} papers (threshold=0.0):\n")

for i, p in enumerate(ranked, 1):
    print(f"{'─' * 78}")
    print(f"  #{i}  [score: {p.score:.4f}]  {p.title}")
    if p.authors:
        print(f"  Authors: {', '.join(p.authors[:5])}")
    if p.year:
        print(f"  Year: {p.year}")
    if p.pdf_url:
        print(f"  PDF: {p.pdf_url}")
    if p.url:
        print(f"  URL: {p.url}")
    if p.abstract:
        abstract_preview = p.abstract[:300] + ("..." if len(p.abstract) > 300 else "")
        print(f"  Abstract: {abstract_preview}")
    print()

# ── 6. Export ──────────────────────────────────────────────────────────────
SOURCE_NAME = "SemanticScholar"
per_query = _args.max_per_query
top_n = _args.top_n

if _args.input_name:
    input_stem = Path(_args.input_name).stem
    base_dir = Path("output") / input_stem
else:
    base_dir = Path("output") / "default"

search_dir_name = f"{SOURCE_NAME}_top{per_query}_select{top_n}"
search_dir = base_dir / search_dir_name
downloads_dir = search_dir / "downloads"
search_dir.mkdir(parents=True, exist_ok=True)
downloads_dir.mkdir(parents=True, exist_ok=True)

xlsx_path = search_dir / f"{search_dir_name}.xlsx"

wb = Workbook()
ws = wb.active
ws.title = "Top10"
headers = [
    "rank",
    "score",
    "title",
    "retrieval_query",
    "authors",
    "year",
    "publication",
    "document_type",
    "doi",
    "citations",
    "source",
    "url",
    "pdf_url",
    "abstract",
]
ws.append(headers)
for i, paper in enumerate(ranked, 1):
    citations = ""
    if paper.metadata_line and paper.metadata_line.startswith("citations: "):
        citations = paper.metadata_line.replace("citations: ", "")
    ws.append(
        [
            i,
            round(paper.score, 6),
            paper.title,
            paper.retrieval_query or "",
            "; ".join(paper.authors),
            paper.year or "",
            paper.publication or "",
            paper.document_type or "",
            paper.doi or "",
            citations,
            paper.source,
            paper.url or "",
            paper.pdf_url or "",
            paper.abstract or "",
        ]
    )
wb.save(xlsx_path)

print("=" * 80)
print(f"XLSX written to: {xlsx_path}")

# ── 7. Download PDFs ──────────────────────────────────────────────────────
print("=" * 80)
print("STEP 4: Downloading PDFs")
print("=" * 80)
download_papers(ranked, downloads_dir)

print("Done.")

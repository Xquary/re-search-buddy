"""Literature search: China energy governance — institutional constraints & agency.
Run: PYTHONPATH=src .venv/bin/python test_china_energy.py
"""
import argparse
from pathlib import Path
import dotenv
dotenv.load_dotenv()
from openpyxl import Workbook
from research_finder.searcher.scholar_searcher import ScholarSearcher
from research_finder.embedder import get_embedder
from research_finder.ranker import rank_papers
from research_finder.input_store import InputStore
from research_finder.filters import filter_by_year
from research_finder.downloader.fulltext import download_papers
import yaml

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--year-from", dest="year_from", type=int, default=None)
parser.add_argument("--year-to", dest="year_to", type=int, default=None)
parser.add_argument("--max-per-query", dest="max_per_query", type=int, default=10)
parser.add_argument("--top-n", dest="top_n", type=int, default=10)
_args, _ = parser.parse_known_args()

INPUT_NAME = "china_energy_governance"

QUERIES = [
    "China energy governance institutional landscape policy design regulatory framework central-local relations",
    "fragmented authoritarianism China energy policy implementation subnational",
    "China central local relations policy implementation energy sector bureaucracy",
    "subnational actors firms implementation space China environmental energy governance",
    "China energy transition institutional constraints political economy",
]

SOURCE_NAME = "Scholar"
per_query = _args.max_per_query
top_n = _args.top_n

# ── Config ──────────────────────────────────────────────────────────────────
with open("config.yaml") as f:
    cfg = yaml.safe_load(f)
cfg.setdefault("search", {}).setdefault("scholar", {})["max_results"] = per_query
cfg.setdefault("embedding", {})["provider"] = "api"

# ── Load cached input ───────────────────────────────────────────────────────
store = InputStore(cfg)
cached_text_emb, TEXT = store.load(INPUT_NAME)
print(f"[input_store] loaded '{INPUT_NAME}': {len(TEXT)} chars, "
      f"embedding shape={cached_text_emb.shape}\n")

# ── Search ──────────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 1: Searching Google Scholar")
print("=" * 80)
print(f"Max results per query: {per_query}")
print(f"Queries ({len(QUERIES)}):")
for q in QUERIES:
    print(f"  - {q}")
print()

searcher = ScholarSearcher(cfg)
papers = searcher.search(QUERIES)
print(f"Found {len(papers)} unique papers from Scholar")
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

# ── Embed ───────────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 2: Embedding text and paper metadata")
print("=" * 80)
embedder = get_embedder(cfg)
text_emb = cached_text_emb
print(f"Text embedding: shape={text_emb.shape} (from input_store cache)")
paper_texts = [f"{p.title} {p.abstract or ''}" for p in papers]
paper_embs = embedder.embed_batch(paper_texts)
print(f"Paper embeddings: shape={paper_embs.shape}\n")

# ── Rank ────────────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 3: Ranking by cosine similarity")
print("=" * 80)
ranked = rank_papers(text_emb, paper_embs, papers, top_n=top_n, threshold=0.0)
print(f"Top {len(ranked)} papers (threshold=0.0):\n")
for i, p in enumerate(ranked, 1):
    print(f"{'─' * 78}")
    print(f"  #{i}  [score: {p.score:.4f}]  {p.title}")
    if p.authors:
        print(f"  Authors: {', '.join(p.authors[:5])}")
    if p.year:
        print(f"  Year: {p.year}")
    if p.url:
        print(f"  URL: {p.url}")
    if p.abstract:
        abstract_preview = p.abstract[:300] + ("..." if len(p.abstract) > 300 else "")
        print(f"  Abstract: {abstract_preview}")
    print()

# ── Export ──────────────────────────────────────────────────────────────────
input_stem = Path(INPUT_NAME).stem
base_dir = Path("output") / input_stem
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
    "rank", "score", "title", "retrieval_query", "authors", "year",
    "publication", "publisher", "document_type", "doi", "source", "url",
    "abstract", "metadata_line",
]
ws.append(headers)
for i, paper in enumerate(ranked, 1):
    ws.append([
        i, round(paper.score, 6), paper.title,
        paper.retrieval_query or "", "; ".join(paper.authors),
        paper.year or "", paper.publication or "", paper.publisher or "",
        paper.document_type or "", paper.doi or "", paper.source,
        paper.url or "", paper.abstract or "", paper.metadata_line or "",
    ])
wb.save(xlsx_path)

print("=" * 80)
print(f"XLSX written to: {xlsx_path}")

# ── Download ────────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 4: Downloading PDFs")
print("=" * 80)
download_papers(ranked, downloads_dir)
print("Done.")

"""Literature search: principal multiplicity in principal-agent theory."""
import argparse
from pathlib import Path
import dotenv
dotenv.load_dotenv()
from openpyxl import Workbook
from research_finder.searcher.scholar_searcher import ScholarSearcher
from research_finder.embedder import get_embedder
from research_finder.ranker import rank_papers
from research_finder.input_store import InputStore
from research_finder.downloader.fulltext import download_papers
import yaml

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--year-from", dest="year_from", type=int, default=None)
parser.add_argument("--year-to", dest="year_to", type=int, default=None)
parser.add_argument("--max-per-query", dest="max_per_query", type=int, default=15)
parser.add_argument("--top-n", dest="top_n", type=int, default=20)
_args, _ = parser.parse_known_args()

INPUT_NAME = "principal_multiplicity"

QUERIES = [
    "multiple principals principal-agent theory competing demands bureaucratic implementation",
    "principal multiplicity agent discretion selective compliance policy implementation",
    "multiple principals bureaucracy strategic latitude formal compliance",
    "common agency competing principals overlapping authority policy",
    "principal-agent coercive authoritarian systems implementation multiple accountability",
]

SOURCE_NAME = "Scholar"
per_query = _args.max_per_query
top_n = _args.top_n

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)
cfg.setdefault("search", {}).setdefault("scholar", {})["max_results"] = per_query
cfg.setdefault("embedding", {})["provider"] = "api"

store = InputStore(cfg)
cached_text_emb, TEXT = store.load(INPUT_NAME)
print(f"[input_store] loaded '{INPUT_NAME}': {len(TEXT)} chars, embedding shape={cached_text_emb.shape}\n")

print("STEP 1: Searching Google Scholar")
searcher = ScholarSearcher(cfg)
papers = searcher.search(QUERIES)
print(f"Found {len(papers)} unique papers from Scholar\n")

if _args.year_from or _args.year_to:
    before = len(papers)
    papers = [p for p in papers if p.year and
              (_args.year_from is None or p.year >= _args.year_from) and
              (_args.year_to is None or p.year <= _args.year_to)]
    print(f"Year filter [{_args.year_from}-{_args.year_to}]: {before} -> {len(papers)} papers\n")

print("STEP 2: Embedding paper metadata")
embedder = get_embedder(cfg)
paper_texts = [f"{p.title}. {p.abstract or ''}" for p in papers]
paper_embs = embedder.embed_batch(paper_texts)

print("STEP 3: Ranking by cosine similarity")
ranked = rank_papers(cached_text_emb, paper_embs, papers, top_n=top_n, threshold=0.0)
print(f"\nTop {len(ranked)} papers:")
for i, p in enumerate(ranked, 1):
    print(f"  #{i:2d}  [score: {p.score:.4f}]  {p.title[:80]}")

input_stem = INPUT_NAME
out_label = f"{SOURCE_NAME}_top{per_query}_select{top_n}"
out_dir = Path("output") / input_stem / out_label
out_dir.mkdir(parents=True, exist_ok=True)
xlsx_path = out_dir / f"{out_label}.xlsx"

wb = Workbook()
ws = wb.active
ws.title = "Results"
headers = ["rank", "score", "title", "authors", "year", "publication",
           "publisher", "document_type", "abstract", "url", "doi",
           "pdf_url", "retrieval_query", "metadata_line"]
ws.append(headers)
for i, p in enumerate(ranked, 1):
    ws.append([
        i, round(p.score, 4), p.title,
        ", ".join(p.authors) if p.authors else "",
        p.year, getattr(p, "publication", ""),
        getattr(p, "publisher", ""),
        getattr(p, "document_type", ""),
        p.abstract or "", p.url or "",
        getattr(p, "doi", "") or "",
        p.pdf_url or "",
        getattr(p, "retrieval_query", "") or "",
        getattr(p, "metadata_line", "") or "",
    ])
wb.save(xlsx_path)
print(f"\nXLSX written to: {xlsx_path}")

print("Done.")

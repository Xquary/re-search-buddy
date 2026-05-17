"""Citation-search runner for china-steel-local-incentives. Dispatches to a chosen searcher."""
import argparse, yaml, importlib
from pathlib import Path
import dotenv; dotenv.load_dotenv()
from openpyxl import Workbook
from research_finder.embedder import get_embedder
from research_finder.ranker import rank_papers
from research_finder.input_store import InputStore

INPUT_NAME = "china-steel-local-incentives"
QUERIES_LOOSE = [
    "China local cadre promotion tournament GDP performance evaluation industrial policy",
    "fragmented authoritarianism Chinese local government incumbent industry protection overcapacity",
    "China steel overcapacity political economy local protectionism central-local relations",
]
QUERIES_BOOLEAN = [
    '("cadre evaluation" OR "promotion tournament" OR "career incentives") AND "local government" AND china',
    '"fragmented authoritarianism" AND china AND (industrial OR overcapacity OR "local protectionism")',
    'china AND ("steel industry" OR overcapacity) AND ("local government" OR "central-local" OR "political economy")',
]
QUERIES_SEMANTIC = [
    "China cadre promotion tournament local government",
    "fragmented authoritarianism China overcapacity",
    "China industrial policy local protectionism overcapacity",
]
QUERIES_BY_SOURCE = {"scopus": QUERIES_BOOLEAN, "semantic": QUERIES_SEMANTIC}

SEARCHERS = {
    "scholar":  ("research_finder.searcher.scholar_searcher", "ScholarSearcher", "Scholar", "scholar"),
    "semantic": ("research_finder.searcher.semantic_scholar_searcher", "SemanticScholarSearcher", "SemanticScholar", "semantic_scholar"),
    "arxiv":    ("research_finder.searcher.arxiv_searcher", "ArxivSearcher", "arXiv", "arxiv"),
    "scopus":   ("research_finder.searcher.scopus_searcher", "ScopusSearcher", "Scopus", "scopus"),
    "cnki":     ("research_finder.searcher.cnki_searcher", "CnkiSearcher", "CNKI", "cnki"),
}

ap = argparse.ArgumentParser()
ap.add_argument("--source", required=True, choices=list(SEARCHERS))
ap.add_argument("--max-per-query", type=int, default=10)
ap.add_argument("--top-n", type=int, default=10)
ap.add_argument("--threshold", type=float, default=0.0)
args = ap.parse_args()

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

mod_path, cls_name, label, cfg_key = SEARCHERS[args.source]
cfg.setdefault("search", {}).setdefault(cfg_key, {})["max_results"] = args.max_per_query
cfg.setdefault("embedding", {})["provider"] = "api"

Searcher = getattr(importlib.import_module(mod_path), cls_name)

store = InputStore(cfg)
text_emb, text = store.load(INPUT_NAME)
print(f"[input] {INPUT_NAME}: {len(text)} chars, dim={text_emb.shape}")

queries = QUERIES_BY_SOURCE.get(args.source, QUERIES_LOOSE)
papers = Searcher(cfg).search(queries)
print(f"[{label}] {len(papers)} unique papers")
if not papers:
    raise SystemExit("No papers returned.")

embedder = get_embedder(cfg)
embs = embedder.embed_batch([f"{p.title}. {p.abstract or ''}" for p in papers])
ranked = rank_papers(text_emb, embs, papers, top_n=args.top_n, threshold=args.threshold)
print(f"[rank] kept {len(ranked)} after top_n={args.top_n}, threshold={args.threshold}")

out_dir = Path("output") / INPUT_NAME / f"{label}_top{args.max_per_query}_select{args.top_n}"
out_dir.mkdir(parents=True, exist_ok=True)
xlsx = out_dir / f"{label}_top{args.max_per_query}_select{args.top_n}.xlsx"
wb = Workbook(); ws = wb.active; ws.title = "Results"
ws.append(["rank","score","title","authors","year","publication","publisher",
           "document_type","abstract","url","doi","pdf_url","retrieval_query"])
for i, p in enumerate(ranked, 1):
    ws.append([i, round(p.score,4), p.title, ", ".join(p.authors or []), p.year,
               getattr(p,"publication",""), getattr(p,"publisher",""),
               getattr(p,"document_type",""), p.abstract or "", p.url or "",
               getattr(p,"doi","") or "", p.pdf_url or "",
               getattr(p,"retrieval_query","") or ""])
wb.save(xlsx)
print(f"[xlsx] {xlsx}")
print("\nTop results:")
for i, p in enumerate(ranked, 1):
    print(f"  #{i:2d} [{p.score:.3f}] {p.title[:90]}")

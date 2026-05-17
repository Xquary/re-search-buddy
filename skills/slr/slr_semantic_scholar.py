"""Systematic Literature Review pipeline — Semantic Scholar source.

Search → embed → rank → XLSX export → visualisation charts.

Usage examples:
  # One-shot mode with multiple queries (semicolon-separated)
  PYTHONPATH=src .venv/bin/python slr_semantic_scholar.py \\
      --input "china_steel_soe_supply_chain.md" \\
      --queries "China steel decarbonization barriers;Chinese steel SOE policy;steel supply chain emissions" \\
      --max-results 100 --year-from 2015

  # With topic labels
  PYTHONPATH=src .venv/bin/python slr_semantic_scholar.py \\
      --input "china_steel_soe_supply_chain.md" \\
      --queries "China steel decarbonization barriers;Chinese steel SOE policy;steel supply chain emissions" \\
      --query-topics "Institutions;SOE;SupplyChain" \\
      --max-results 100 --year-from 2015
"""
import argparse
import sys
from pathlib import Path

import dotenv
dotenv.load_dotenv()

import yaml
from openpyxl import Workbook

from research_finder.searcher.semantic_scholar_searcher import SemanticScholarSearcher
from research_finder.embedder import get_embedder
from research_finder.ranker import rank_papers
from research_finder.extractor.keyword_extractor import KeywordExtractor
from research_finder.input_store import InputStore
from research_finder.filters import filter_by_year
from research_finder.downloader.fulltext import download_papers
from research_finder.slr.charts import generate_all

# ── Args ───────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="SLR via Semantic Scholar", add_help=True)
parser.add_argument("--input", dest="input_name", default=None,
                    help="Cached input name (stem or filename in input/embeddings/)")
parser.add_argument("--query", dest="query", default=None,
                    help="Single query string")
parser.add_argument("--queries", dest="queries", default=None,
                    help="Semicolon-separated list of queries")
parser.add_argument("--query-topics", dest="query_topics", default=None,
                    help="Semicolon-separated topic labels (parallel to --queries)")
parser.add_argument("--max-results", dest="max_results", type=int, default=50,
                    help="Max papers per query (default 50)")
parser.add_argument("--top-n", dest="top_n", type=int, default=None,
                    help="Top-N papers to export after ranking (default: all)")
parser.add_argument("--year-from", dest="year_from", type=int, default=None)
parser.add_argument("--year-to", dest="year_to", type=int, default=None)
parser.add_argument("--threshold", dest="threshold", type=float, default=0.0,
                    help="Minimum cosine similarity score (default 0.0)")
parser.add_argument("--no-download", dest="no_download", action="store_true",
                    help="Skip all PDF download phases")
parser.add_argument("--no-elsevier-download", dest="no_elsevier", action="store_true",
                    help="Skip Elsevier Full Text API phase")
parser.add_argument("--direct-delay", dest="direct_delay", type=float, default=1.0,
                    help="Seconds between direct HTTP download requests")
parser.add_argument("--elsevier-delay", dest="elsevier_delay", type=float, default=2.0,
                    help="Seconds between Elsevier API download requests")
parser.add_argument("--annas-delay", dest="annas_delay", type=float, default=3.0,
                    help="Seconds between Anna's Archive download attempts")
parser.add_argument("--no-charts", dest="no_charts", action="store_true",
                    help="Skip chart generation")
args = parser.parse_args()

# ── Config ─────────────────────────────────────────────────────────────────
with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

ss_cfg = cfg.setdefault("search", {}).setdefault("semantic_scholar", {})
ss_cfg["max_results"] = args.max_results
if args.year_from is not None:
    cfg["search"]["year_from"] = args.year_from
if args.year_to is not None:
    cfg["search"]["year_to"] = args.year_to

cfg["embedding"]["provider"] = "api"

# ── Input text / embedding ─────────────────────────────────────────────────
TEXT = ""
cached_text_emb = None
if args.input_name:
    store = InputStore(cfg)
    cached_text_emb, TEXT = store.load(args.input_name)
    print(f"[input] '{args.input_name}': {len(TEXT)} chars, emb={cached_text_emb.shape}\n")
else:
    TEXT = (
        "Recent study argues that steel decarbonization should be understood as a broader "
        "industrial transformation rather than a narrow emissions problem."
    )

# ── Queries ────────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 0: Queries")
print("=" * 80)

if args.query:
    QUERIES = [args.query]
elif args.queries:
    QUERIES = [q.strip() for q in args.queries.split(";") if q.strip()]
else:
    extractor = KeywordExtractor(cfg)
    QUERIES = extractor.extract(TEXT)

print(f"Queries ({len(QUERIES)}):")
for q in QUERIES:
    print(f"  - {q}")

active_filters = []
if args.year_from or args.year_to:
    lo = str(args.year_from) if args.year_from else "earliest"
    hi = str(args.year_to) if args.year_to else "latest"
    active_filters.append(f"year: {lo}–{hi}")
if args.threshold > 0:
    active_filters.append(f"similarity threshold: {args.threshold}")

if active_filters:
    print(f"Filters: {', '.join(active_filters)}")
print(f"Max results per query: {args.max_results}")
print()

# ── Search ─────────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 1: Searching Semantic Scholar")
print("=" * 80)

searcher = SemanticScholarSearcher(cfg)
papers = searcher.search(QUERIES)
print(f"Found {len(papers)} unique papers")

if args.year_from is not None or args.year_to is not None:
    before = len(papers)
    papers = filter_by_year(papers, args.year_from, args.year_to)
    if len(papers) < before:
        print(f"  year filter: kept {len(papers)} / {before}")
print()

if not papers:
    print("No papers found. Exiting.")
    sys.exit(0)

# ── Embed + rank ───────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 2: Embedding & ranking")
print("=" * 80)

embedder = get_embedder(cfg)
if cached_text_emb is not None:
    text_emb = cached_text_emb
    print(f"Text embedding: {text_emb.shape} (cached)")
else:
    text_emb = embedder.embed_single(TEXT)
    print(f"Text embedding: {text_emb.shape}")

paper_texts = [f"{p.title} {p.abstract or ''}" for p in papers]
paper_embs = embedder.embed_batch(paper_texts)
print(f"Paper embeddings: {paper_embs.shape}")

top_n = args.top_n if args.top_n else len(papers)
ranked = rank_papers(text_emb, paper_embs, papers, top_n=top_n, threshold=args.threshold)
print(f"Ranked {len(ranked)} papers (threshold={args.threshold})\n")

for i, p in enumerate(ranked[:10], 1):
    print(f"  #{i:>3}  [{p.score:.4f}]  {p.title[:80]}")
if len(ranked) > 10:
    print(f"  ... and {len(ranked) - 10} more")
print()

# ── Build output path ─────────────────────────────────────────────────────
parts = [f"q{len(QUERIES)}", f"max{args.max_results}"]
if args.year_from or args.year_to:
    lo = str(args.year_from) if args.year_from else "x"
    hi = str(args.year_to) if args.year_to else "x"
    parts.append(f"y{lo}-{hi}")

tag = "_".join(parts)
input_stem = Path(args.input_name).stem if args.input_name else "default"
out_dir = Path("output") / input_stem / f"SLR_SemanticScholar_{tag}"
charts_dir = out_dir / "charts"
downloads_dir = out_dir / "downloads"
out_dir.mkdir(parents=True, exist_ok=True)

# ── Export XLSX ────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 3: Exporting XLSX")
print("=" * 80)

xlsx_path = out_dir / f"SLR_SemanticScholar_{tag}.xlsx"
wb = Workbook()
ws = wb.active
ws.title = "SLR"

query_topic_map: dict[str, str] = {}
if args.query_topics:
    _topics = [t.strip() for t in args.query_topics.split(";")]
    if len(_topics) == len(QUERIES):
        query_topic_map = dict(zip(QUERIES, _topics))
    else:
        print(f"[warn] --query-topics has {len(_topics)} entries but {len(QUERIES)} queries; skipping topic_label")

headers = [
    "rank", "score", "title", "retrieval_query", "topic_label",
    "authors", "first_author", "year", "venue", "document_type",
    "doi", "citations", "source", "url", "pdf_url", "abstract",
]
ws.append(headers)

for i, p in enumerate(ranked, 1):
    citations = ""
    if p.metadata_line and p.metadata_line.startswith("citations: "):
        citations = p.metadata_line.replace("citations: ", "")
    ws.append([
        i,
        round(p.score, 6),
        p.title,
        p.retrieval_query or "",
        query_topic_map.get(p.retrieval_query or "", ""),
        "; ".join(p.authors),
        (p.authors[0] if p.authors else ""),
        p.year or "",
        p.publication or "",
        p.document_type or "",
        p.doi or "",
        citations,
        p.source,
        p.url or "",
        p.pdf_url or "",
        p.abstract or "",
    ])

wb.save(xlsx_path)
print(f"XLSX written: {xlsx_path}  ({len(ranked)} rows)\n")

# ── Charts ─────────────────────────────────────────────────────────────────
if not args.no_charts:
    print("=" * 80)
    print("STEP 4: Generating charts")
    print("=" * 80)
    generate_all(ranked, charts_dir)
    print()

# ── Download ───────────────────────────────────────────────────────────────
if not args.no_download:
    print("=" * 80)
    print("STEP 5: Downloading PDFs")
    print("=" * 80)
    print(f"  Delays — direct: {args.direct_delay}s  elsevier: {args.elsevier_delay}s  annas: {args.annas_delay}s")
    downloads_dir.mkdir(parents=True, exist_ok=True)
    download_papers(
        ranked,
        downloads_dir,
        delay=args.direct_delay,
        elsevier_delay=args.elsevier_delay,
        annas_delay=args.annas_delay,
        elsevier_download=not args.no_elsevier,
    )

print("Done.")

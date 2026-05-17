"""Systematic Literature Review pipeline — Scopus source.

Search → embed → rank → XLSX export → visualisation charts.

Usage examples:
  # One-shot mode with a single query
  PYTHONPATH=src .venv/bin/python slr_scopus.py \\
      --input "Seeds of Green_Methodology.pdf" \\
      --query "agent-based modelling supply chain decarbonization" \\
      --max-results 200 --year-from 2010 --subject-area COMP --doc-type ar

  # One-shot mode with multiple queries (semicolon-separated)
  PYTHONPATH=src .venv/bin/python slr_scopus.py \\
      --input "Seeds of Green_Methodology.pdf" \\
      --queries "agent-based modelling supply chain;multi-agent systems decarbonization" \\
      --max-results 200 --year-from 2010

  # Interactive calibration mode (LLM generates initial queries)
  PYTHONPATH=src .venv/bin/python slr_scopus.py \\
      --input "Seeds of Green_Methodology.pdf" \\
      --calibrate --max-results 200

  # Interactive calibration starting from user-provided queries
  PYTHONPATH=src .venv/bin/python slr_scopus.py \\
      --input "Seeds of Green_Methodology.pdf" \\
      --calibrate --queries "ABM supply chain;multi-agent decarbonization" \\
      --max-results 200

  # Resume from a previously saved calibration state
  PYTHONPATH=src .venv/bin/python slr_scopus.py \\
      --input "Seeds of Green_Methodology.pdf" \\
      --queries-file output/calibration/calibration_001.yaml \\
      --max-results 200
"""
import argparse
import sys
from pathlib import Path

import dotenv
dotenv.load_dotenv()

import yaml
from openpyxl import Workbook

from research_finder.searcher.scopus_searcher import ScopusSearcher
from research_finder.embedder import get_embedder
from research_finder.ranker import rank_papers
from research_finder.extractor.keyword_extractor import KeywordExtractor
from research_finder.input_store import InputStore
from research_finder.filters import filter_by_year
from research_finder.downloader.fulltext import download_papers
from research_finder.slr.charts import generate_all

# ── Args ───────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="SLR via Scopus", add_help=True)
parser.add_argument("--input", dest="input_name", default=None,
                    help="Cached input name (stem or filename in input/embeddings/)")
parser.add_argument("--query", dest="query", default=None,
                    help="Single Scopus query string")
parser.add_argument("--queries", dest="queries", default=None,
                    help="Semicolon-separated list of Scopus queries")
parser.add_argument("--query-topics", dest="query_topics", default=None,
                    help="Semicolon-separated topic label per query (parallel to --queries). Written as topic_label column.")
parser.add_argument("--max-results", dest="max_results", type=int, default=200,
                    help="Max papers to retrieve per query (default 200)")
parser.add_argument("--top-n", dest="top_n", type=int, default=None,
                    help="Top-N papers to export after ranking (default: all)")
parser.add_argument("--year-from", dest="year_from", type=int, default=None)
parser.add_argument("--year-to", dest="year_to", type=int, default=None)
parser.add_argument("--subject-area", dest="subject_area", default=None,
                    help="Scopus ASJC code: COMP, ENGI, ENER, ENVI, SOCI, ECON, …")
parser.add_argument("--doc-type", dest="doc_type", default=None,
                    help="DOCTYPE filter: ar, re, cp, bk, ch, …")
parser.add_argument("--src-type", dest="src_type", default=None,
                    help="SRCTYPE filter: j, b, k, p, r, d")
parser.add_argument("--source-title", dest="source_title", default=None,
                    help="Restrict to a specific journal title")
parser.add_argument("--open-access", dest="open_access_only", action="store_true",
                    help="Return open-access papers only")
parser.add_argument("--threshold", dest="threshold", type=float, default=0.0,
                    help="Minimum cosine similarity score to include (default 0.0)")
parser.add_argument("--no-download", dest="no_download", action="store_true",
                    help="Skip all PDF download phases")
parser.add_argument("--no-elsevier-download", dest="no_elsevier", action="store_true",
                    help="Skip Elsevier Full Text API phase")
parser.add_argument("--direct-delay", dest="direct_delay", type=float, default=1.0,
                    help="Seconds between direct HTTP download requests (default 1.0)")
parser.add_argument("--elsevier-delay", dest="elsevier_delay", type=float, default=2.0,
                    help="Seconds between Elsevier API download requests (default 2.0)")
parser.add_argument("--annas-delay", dest="annas_delay", type=float, default=3.0,
                    help="Seconds between Anna's Archive download attempts (default 3.0)")
parser.add_argument("--no-charts", dest="no_charts", action="store_true",
                    help="Skip chart generation")
parser.add_argument("--no-abstract-enrich", dest="no_abstract_enrich", action="store_true",
                    help="Skip Abstract Retrieval API calls (conserves weekly quota)")
parser.add_argument("--calibrate", dest="calibrate", action="store_true",
                    help="Enable interactive query calibration loop before full search")
parser.add_argument("--preview-size", dest="preview_size", type=int, default=5,
                    help="Papers per query to fetch during calibration preview (default 5)")
parser.add_argument("--calibrate-rounds", dest="calibrate_rounds", type=int, default=5,
                    help="Maximum calibration rounds before auto-continue (default 5)")
parser.add_argument("--queries-file", dest="queries_file", default=None,
                    help="Load queries & filters from a saved calibration YAML file")
args = parser.parse_args()

# ── Config ─────────────────────────────────────────────────────────────────
with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

scopus_cfg = cfg.setdefault("search", {}).setdefault("scopus", {})
scopus_cfg["max_results"] = args.max_results
scopus_cfg["enrich_abstracts"] = not args.no_abstract_enrich
if args.year_from is not None:
    cfg["search"]["year_from"] = args.year_from
if args.year_to is not None:
    cfg["search"]["year_to"] = args.year_to
if args.subject_area:
    scopus_cfg["subject_area"] = args.subject_area
if args.doc_type:
    scopus_cfg["doc_type"] = args.doc_type
if args.src_type:
    scopus_cfg["src_type"] = args.src_type
if args.source_title:
    scopus_cfg["source_title"] = args.source_title
if args.open_access_only:
    scopus_cfg["open_access_only"] = True

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
        "Agent-based modelling and multi-agent systems for industrial supply chain "
        "simulation and decarbonization decision-making."
    )

# ── Queries ────────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 0: Queries")
print("=" * 80)

# --- Calibration mode or one-shot query setup ---
calibration_filters: dict = {}

if args.queries_file:
    # Load previously saved calibration state
    from research_finder.slr.query_calibrator import load_calibration_state
    QUERIES, calibration_filters = load_calibration_state(Path(args.queries_file))
    print(f"Loaded {len(QUERIES)} queries and filters from: {args.queries_file}")

elif args.calibrate:
    # Interactive calibration loop
    if not sys.stdin.isatty():
        print("[calibrator] stdin is not a TTY — falling back to one-shot query mode")
        if args.query:
            QUERIES = [args.query]
        elif args.queries:
            QUERIES = [q.strip() for q in args.queries.split(";") if q.strip()]
        else:
            extractor = KeywordExtractor(cfg)
            QUERIES = extractor.extract(TEXT)
    else:
        from research_finder.slr.query_calibrator import run_calibration
        # Pass user-provided queries as initial if --query or --queries set
        initial = None
        if args.query:
            initial = [args.query]
        elif args.queries:
            initial = [q.strip() for q in args.queries.split(";") if q.strip()]

        QUERIES, calibration_filters = run_calibration(
            text=TEXT,
            config=cfg,
            initial_queries=initial,
            preview_size=args.preview_size,
            max_rounds=args.calibrate_rounds,
        )
else:
    # One-shot mode (current behavior)
    if args.query:
        QUERIES = [args.query]
    elif args.queries:
        QUERIES = [q.strip() for q in args.queries.split(";") if q.strip()]
    else:
        extractor = KeywordExtractor(cfg)
        QUERIES = extractor.extract(TEXT)

# --- Apply calibration filters to config (if any) ---
if calibration_filters:
    if calibration_filters.get("year_from"):
        cfg["search"]["year_from"] = calibration_filters["year_from"]
        args.year_from = calibration_filters["year_from"]
    if calibration_filters.get("year_to"):
        cfg["search"]["year_to"] = calibration_filters["year_to"]
        args.year_to = calibration_filters["year_to"]
    if calibration_filters.get("subject_area"):
        scopus_cfg["subject_area"] = calibration_filters["subject_area"]
        args.subject_area = calibration_filters["subject_area"]
    if calibration_filters.get("doc_type"):
        scopus_cfg["doc_type"] = calibration_filters["doc_type"]
        args.doc_type = calibration_filters["doc_type"]
    if calibration_filters.get("src_type"):
        scopus_cfg["src_type"] = calibration_filters["src_type"]
        args.src_type = calibration_filters["src_type"]
    if calibration_filters.get("source_title"):
        scopus_cfg["source_title"] = calibration_filters["source_title"]
        args.source_title = calibration_filters["source_title"]
    if calibration_filters.get("open_access_only"):
        scopus_cfg["open_access_only"] = calibration_filters["open_access_only"]
        args.open_access_only = calibration_filters["open_access_only"]

# Print final queries
print(f"Queries ({len(QUERIES)}):")
for q in QUERIES:
    print(f"  - {q}")

active_filters = []
if args.year_from or args.year_to:
    lo = str(args.year_from) if args.year_from else "earliest"
    hi = str(args.year_to) if args.year_to else "latest"
    active_filters.append(f"year: {lo}–{hi}")
if args.subject_area:
    active_filters.append(f"subject area: {args.subject_area}")
if args.doc_type:
    active_filters.append(f"doc type: {args.doc_type}")
if args.src_type:
    active_filters.append(f"src type: {args.src_type}")
if args.source_title:
    active_filters.append(f"journal: {args.source_title}")
if args.open_access_only:
    active_filters.append("open access only")
if args.threshold > 0:
    active_filters.append(f"similarity threshold: {args.threshold}")

if active_filters:
    print(f"Filters: {', '.join(active_filters)}")
print(f"Max results per query: {args.max_results}")
print()

# ── Search ─────────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 1: Searching Scopus")
print("=" * 80)

searcher = ScopusSearcher(cfg)
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

# Print top 10 preview
for i, p in enumerate(ranked[:10], 1):
    score_str = f"{p.score:.4f}"
    print(f"  #{i:>3}  [{score_str}]  {p.title[:80]}")
if len(ranked) > 10:
    print(f"  ... and {len(ranked) - 10} more")
print()

# ── Build output path ─────────────────────────────────────────────────────
parts = [f"q{len(QUERIES)}", f"max{args.max_results}"]
if args.year_from or args.year_to:
    lo = str(args.year_from) if args.year_from else "x"
    hi = str(args.year_to) if args.year_to else "x"
    parts.append(f"y{lo}-{hi}")
if args.subject_area:
    parts.append(args.subject_area)
if args.doc_type:
    parts.append(args.doc_type)

tag = "_".join(parts)
input_stem = Path(args.input_name).stem if args.input_name else "default"
out_dir = Path("output") / input_stem / f"SLR_Scopus_{tag}"
charts_dir = out_dir / "charts"
downloads_dir = out_dir / "downloads"
out_dir.mkdir(parents=True, exist_ok=True)

# ── Export XLSX ────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 3: Exporting XLSX")
print("=" * 80)

xlsx_path = out_dir / f"SLR_Scopus_{tag}.xlsx"
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
    "authors", "first_author", "year", "journal", "issn",
    "volume", "issue", "pages", "doc_type", "doi", "scopus_id",
    "citations", "open_access", "author_keywords", "affiliations",
    "source", "url", "abstract",
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
        p.issn or "",
        p.volume or "",
        p.issue or "",
        p.pages or "",
        p.document_type or "",
        p.doi or "",
        p.scopus_id or "",
        citations,
        "Yes" if p.open_access else "No",
        p.author_keywords or "",
        p.affiliations or "",
        p.source,
        p.url or "",
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

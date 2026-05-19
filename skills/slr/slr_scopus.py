"""Systematic Literature Review — Scopus search + abstract enrichment.

Pipeline order:
  1. slr_scopus.py  → Search Scopus + enrich abstracts → export raw XLSX
  2. slr_rank.py     → Load XLSX → embed → rank → update XLSX with scores
  3. Post-SLR analysis (keyword verification → journal exclusion → 10 analyses)

Usage:
  PYTHONPATH=src .venv/bin/python skills/slr/slr_scopus.py \\
      --input "green_steel_china_slr.md" \\
      --queries "query1;query2" \\
      --query-topics "TopicA;TopicB" \\
      --max-results 1000 --year-from 2015
"""
import argparse
import sys
from pathlib import Path

import dotenv
dotenv.load_dotenv()

import yaml
from openpyxl import Workbook

from research_finder.searcher.scopus_searcher import ScopusSearcher
from research_finder.extractor.keyword_extractor import KeywordExtractor
from research_finder.input_store import InputStore
from research_finder.filters import filter_by_year

# ── Args ───────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="SLR Scopus search + enrich", add_help=True)
parser.add_argument("--input", dest="input_name", default=None,
                    help="Cached input name (stem or filename in input/embeddings/)")
parser.add_argument("--query", dest="query", default=None,
                    help="Single Scopus query string")
parser.add_argument("--queries", dest="queries", default=None,
                    help="Semicolon-separated list of Scopus queries")
parser.add_argument("--query-topics", dest="query_topics", default=None,
                    help="Semicolon-separated topic label per query (parallel to --queries).")
parser.add_argument("--max-results", dest="max_results", type=int, default=200,
                    help="Max papers per query (default 200)")
parser.add_argument("--year-from", dest="year_from", type=int, default=None)
parser.add_argument("--year-to", dest="year_to", type=int, default=None)
parser.add_argument("--subject-area", dest="subject_area", default=None,
                    help="Scopus ASJC code (single value)")
parser.add_argument("--doc-type", dest="doc_type", default=None,
                    help="DOCTYPE filter")
parser.add_argument("--src-type", dest="src_type", default=None,
                    help="SRCTYPE filter")
parser.add_argument("--source-title", dest="source_title", default=None,
                    help="Restrict to a specific journal title")
parser.add_argument("--open-access", dest="open_access_only", action="store_true",
                    help="Return open-access papers only")
parser.add_argument("--no-abstract-enrich", dest="no_abstract_enrich", action="store_true",
                    help="Skip Abstract Retrieval API calls")
parser.add_argument("--calibrate", dest="calibrate", action="store_true",
                    help="Enable interactive query calibration loop")
parser.add_argument("--preview-size", dest="preview_size", type=int, default=5,
                    help="Papers per query during calibration preview")
parser.add_argument("--calibrate-rounds", dest="calibrate_rounds", type=int, default=5,
                    help="Maximum calibration rounds")
parser.add_argument("--queries-file", dest="queries_file", default=None,
                    help="Load queries from saved calibration YAML file")
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

# ── Input text —────────────────────────────────────────────────────────────
TEXT = ""
if args.input_name:
    store = InputStore(cfg)
    _, TEXT = store.load(args.input_name)
    print(f"[input] '{args.input_name}': {len(TEXT)} chars\n")

# ── Queries ────────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 0: Queries")
print("=" * 80)

calibration_filters: dict = {}

if args.queries_file:
    from research_finder.slr.query_calibrator import load_calibration_state
    QUERIES, calibration_filters = load_calibration_state(Path(args.queries_file))
    print(f"Loaded {len(QUERIES)} queries from: {args.queries_file}")

elif args.calibrate:
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
        initial = None
        if args.query:
            initial = [args.query]
        elif args.queries:
            initial = [q.strip() for q in args.queries.split(";") if q.strip()]
        QUERIES, calibration_filters = run_calibration(
            text=TEXT, config=cfg, initial_queries=initial,
            preview_size=args.preview_size, max_rounds=args.calibrate_rounds,
        )
else:
    if args.query:
        QUERIES = [args.query]
    elif args.queries:
        QUERIES = [q.strip() for q in args.queries.split(";") if q.strip()]
    else:
        extractor = KeywordExtractor(cfg)
        QUERIES = extractor.extract(TEXT)

if calibration_filters:
    for k in ["year_from", "year_to", "subject_area", "doc_type", "src_type",
               "source_title", "open_access_only"]:
        if calibration_filters.get(k):
            if k in ("year_from", "year_to"):
                cfg["search"][k] = calibration_filters[k]
                setattr(args, k, calibration_filters[k])
            else:
                scopus_cfg[k] = calibration_filters[k]
                setattr(args, k, calibration_filters[k])

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
print(f"Found {len(papers)} unique papers\n")

if args.year_from is not None or args.year_to is not None:
    before = len(papers)
    papers = filter_by_year(papers, args.year_from, args.year_to)
    if len(papers) < before:
        print(f"  year filter: kept {len(papers)} / {before}")
print()

if not papers:
    print("No papers found. Exiting.")
    sys.exit(0)

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
out_dir.mkdir(parents=True, exist_ok=True)

# ── Export XLSX (unranked raw) ─────────────────────────────────────────────
print("=" * 80)
print("STEP 2: Exporting XLSX (unranked — rank/scores set by slr_rank.py)")
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
        print(f"[warn] --query-topics count mismatch: {len(_topics)} vs {len(QUERIES)} queries")

headers = [
    "rank", "score", "title", "retrieval_query", "topic_label",
    "authors", "first_author", "year", "journal", "issn",
    "volume", "issue", "pages", "doc_type", "doi", "scopus_id",
    "citations", "open_access", "author_keywords", "affiliations",
    "language", "source", "url", "abstract",
]
ws.append(headers)

for i, p in enumerate(papers, 1):
    citations = ""
    if p.metadata_line and p.metadata_line.startswith("citations: "):
        citations = p.metadata_line.replace("citations: ", "")
    ws.append([
        i,                     # rank (raw order; overwritten by slr_rank.py)
        0.0,                   # score (placeholder; overwritten by slr_rank.py)
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
        p.language or "",
        p.source,
        p.url or "",
        p.abstract or "",
    ])

wb.save(xlsx_path)
print(f"XLSX written: {xlsx_path}  ({len(papers)} rows)")
print()
print("Next step: PYTHONPATH=src .venv/bin/python skills/slr/slr_rank.py --xlsx <path> --input <stem>")
print("Done.")

"""Query Calibrator — interactive query refinement for systematic literature review.

Replaces one-shot query generation with an iterative feedback loop:
  1. Draft queries (LLM or user-provided)
  2. Preview search (small sample per query)
  3. Show result counts, sample titles, keyword spread
  4. User refines queries/filters → back to step 2
  5. Continue when satisfied → final queries + filters

Usage:
    from research_finder.slr.query_calibrator import run_calibration

    queries, filters = run_calibration(
        text="your research text...",
        config=config_dict,
        initial_queries=["query 1", "query 2"],
        searcher_class=ScopusSearcher,
    )
"""

from __future__ import annotations

import copy
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ── Data model ──────────────────────────────────────────────────────────────

@dataclass
class QueryPreview:
    """Preview results for a single query from a lightweight search."""
    query: str
    total_count: int
    sample_titles: list[str]       # top-N titles from the preview search
    top_keywords: list[str]        # keywords extracted from this query's sample papers

@dataclass
class CalibrationRound:
    """One complete round of the calibration loop."""
    round_num: int
    queries: list[str]
    filters: dict[str, Any] = field(default_factory=dict)
    previews: list[QueryPreview] = field(default_factory=list)
    action: str = ""               # continue | refine | filters | add | regenerate | save | exit
    action_detail: str = ""        # free-text description of what the user did

@dataclass
class CalibrationState:
    """Accumulated state across all calibration rounds."""
    text: str
    rounds: list[CalibrationRound] = field(default_factory=list)
    final_queries: list[str] = field(default_factory=list)
    final_filters: dict[str, Any] = field(default_factory=dict)


# ── Constants ───────────────────────────────────────────────────────────────

ACTION_OPTIONS = [
    ("continue",  "Use these queries for full search"),
    ("refine",    "Edit / replace specific queries"),
    ("filters",   "Adjust year range, subject area, doc type"),
    ("add",       "Add new queries to supplement coverage"),
    ("regenerate","Ask LLM for a different angle on the topic"),
    ("save",      "Save current queries & filters to YAML, then exit"),
    ("exit",      "Exit without saving"),
]

_DEFAULT_PREVIEW_SIZE = 5
_DEFAULT_MAX_ROUNDS = 5


# ── Public entry point ──────────────────────────────────────────────────────

def run_calibration(
    text: str,
    *,
    config: dict[str, Any],
    initial_queries: list[str] | None = None,
    searcher_class: type | None = None,
    preview_size: int = _DEFAULT_PREVIEW_SIZE,
    max_rounds: int = _DEFAULT_MAX_ROUNDS,
    output_dir: Path | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Run the interactive query calibration loop.

    Parameters
    ----------
    text : str
        The research text / input for the SLR.
    config : dict
        Full configuration dict (same shape as config.yaml).
    initial_queries : list[str] or None
        Starting queries; if None, queries are generated via KeywordExtractor (LLM).
    searcher_class : type or None
        Searcher class to use for preview (default: ScopusSearcher).
    preview_size : int
        Number of sample papers to fetch per query during preview.
    max_rounds : int
        Maximum number of calibration rounds before auto-continuing.
    output_dir : Path or None
        Directory to save calibration state YAML; defaults to output/calibration/.

    Returns
    -------
    (final_queries, final_filters) : tuple[list[str], dict[str, Any]]
        final_queries: the refined query strings.
        final_filters: dict of active filters (year_from, year_to, subject_area,
                       doc_type, src_type, source_title, open_access_only).
    """
    if searcher_class is None:
        from research_finder.searcher.scopus_searcher import ScopusSearcher
        searcher_class = ScopusSearcher

    state = CalibrationState(text=text)

    # Extract current filters from config
    search_cfg = config.get("search", {})
    scopus_cfg = search_cfg.get("scopus", {})
    current_filters = _extract_filters(search_cfg, scopus_cfg)

    # Round 0: generate initial queries if none provided
    if not initial_queries:
        print("\nNo queries provided — generating via LLM keyword extraction...")
        initial_queries = _generate_queries(text, config)
        print(f"Generated {len(initial_queries)} queries.\n")

    queries = list(initial_queries)

    for round_num in range(1, max_rounds + 1):
        cr = CalibrationRound(
            round_num=round_num,
            queries=list(queries),
            filters=copy.deepcopy(current_filters),
        )

        # ── Preview search ────────────────────────────────────────────────
        print(f"\n{'━' * 80}")
        print(f"ROUND {round_num} — Preview Search")
        print(f"{'━' * 80}")

        _print_active_filters(current_filters)

        previews = _run_preview_search(
            queries, config, preview_size, searcher_class, current_filters
        )
        cr.previews = previews

        _display_previews(previews)

        # ── Keyword synthesis across all results ──────────────────────────
        _display_cross_query_keywords(previews)

        # ── Warnings ──────────────────────────────────────────────────────
        _display_warnings(previews)

        # ── User action ───────────────────────────────────────────────────
        action, detail = _get_user_action()
        cr.action = action
        cr.action_detail = detail
        state.rounds.append(cr)

        if action == "continue":
            state.final_queries = queries
            state.final_filters = current_filters
            _save_state(state, output_dir, config)
            return queries, current_filters

        elif action == "refine":
            queries = _handle_refine(queries, previews)

        elif action == "filters":
            current_filters = _handle_filters(current_filters)

        elif action == "add":
            new_queries = _handle_add(queries)
            if new_queries:
                queries.extend(new_queries)

        elif action == "regenerate":
            print("\nRegenerating queries with different angle...")
            new_queries = _generate_queries(text, config)
            print(f"Generated {len(new_queries)} new queries.")
            print("\nKeep:  [a] new only  [b] merge with current  [c] discard")
            choice = input("> ").strip().lower()
            if choice == "a":
                queries = new_queries
            elif choice == "b":
                queries = list(queries) + [q for q in new_queries if q not in queries]
            # else: keep current

        elif action == "save":
            state.final_queries = queries
            state.final_filters = current_filters
            _save_state(state, output_dir, config)
            print("\nState saved. You can resume later with --queries-file <path>.")
            sys.exit(0)

        elif action == "exit":
            print("\nCalibration cancelled.")
            sys.exit(0)

    # Max rounds reached — auto-continue
    print(f"\n[calibrator] Max rounds ({max_rounds}) reached — auto-continuing.")
    state.final_queries = queries
    state.final_filters = current_filters
    _save_state(state, output_dir, config)
    return queries, current_filters


# ── Filter extraction ───────────────────────────────────────────────────────

def _extract_filters(search_cfg: dict, scopus_cfg: dict) -> dict[str, Any]:
    """Extract active filter state from the config."""
    return {
        "year_from": search_cfg.get("year_from") or scopus_cfg.get("year_from"),
        "year_to": search_cfg.get("year_to") or scopus_cfg.get("year_to"),
        "subject_area": scopus_cfg.get("subject_area"),
        "doc_type": scopus_cfg.get("doc_type"),
        "src_type": scopus_cfg.get("src_type"),
        "source_title": scopus_cfg.get("source_title"),
        "open_access_only": scopus_cfg.get("open_access_only", False),
    }


def _print_active_filters(filters: dict) -> None:
    """Print a one-line summary of active filters."""
    parts = []
    if filters.get("year_from") or filters.get("year_to"):
        lo = str(filters["year_from"]) if filters["year_from"] else "earliest"
        hi = str(filters["year_to"]) if filters["year_to"] else "latest"
        parts.append(f"year: {lo}–{hi}")
    if filters.get("subject_area"):
        parts.append(f"subject: {filters['subject_area']}")
    if filters.get("doc_type"):
        parts.append(f"doc type: {filters['doc_type']}")
    if filters.get("src_type"):
        parts.append(f"src type: {filters['src_type']}")
    if filters.get("source_title"):
        parts.append(f"journal: {filters['source_title']}")
    if filters.get("open_access_only"):
        parts.append("OA only")
    if parts:
        print(f"Filters: {', '.join(parts)}")
    else:
        print("Filters: none")


# ── LLM query generation ────────────────────────────────────────────────────

def _generate_queries(text: str, config: dict) -> list[str]:
    """Generate search queries from the input text via LLM."""
    from research_finder.extractor.keyword_extractor import KeywordExtractor
    extractor = KeywordExtractor(config)
    return extractor.extract(text)


# ── Preview search ──────────────────────────────────────────────────────────

def _run_preview_search(
    queries: list[str],
    config: dict,
    preview_size: int,
    searcher_class: type,
    filters: dict,
) -> list[QueryPreview]:
    """Run lightweight search for each query and return previews."""
    # Build a temporary config for preview search
    preview_config = copy.deepcopy(config)
    preview_scopus = preview_config.setdefault("search", {}).setdefault("scopus", {})
    preview_scopus["max_results"] = preview_size
    preview_scopus["enrich_abstracts"] = False  # no abstract API calls during preview
    preview_scopus["query_delay"] = 0.3         # faster inter-query delay for preview

    # Apply current filters to the preview config
    if filters.get("year_from"):
        preview_config["search"]["year_from"] = filters["year_from"]
    if filters.get("year_to"):
        preview_config["search"]["year_to"] = filters["year_to"]
    for key in ("subject_area", "doc_type", "src_type", "source_title"):
        if filters.get(key):
            preview_scopus[key] = filters[key]
    if filters.get("open_access_only"):
        preview_scopus["open_access_only"] = True

    searcher = searcher_class(preview_config)

    previews: list[QueryPreview] = []
    for query in queries:
        print(f"  Searching: {query[:70]}...", end=" ", flush=True)
        papers = searcher.search([query])
        total = len(papers)
        titles = [p.title for p in papers if p.title]

        # Simple keyword extraction from titles
        kw_counter: Counter[str] = Counter()
        for p in papers:
            for word in (p.title or "").lower().split():
                word = word.strip(".,;:()[]{}\"'!?")
                if len(word) > 3:
                    kw_counter[word] += 1

        top_kw = [w for w, _ in kw_counter.most_common(10)]

        previews.append(QueryPreview(
            query=query,
            total_count=total,
            sample_titles=titles,
            top_keywords=top_kw,
        ))
        print(f"{total} results")

    return previews


# ── Display ─────────────────────────────────────────────────────────────────

def _display_previews(previews: list[QueryPreview]) -> None:
    """Print formatted preview results for all queries."""
    for i, pv in enumerate(previews, 1):
        print(f"\n  Query {i}: {pv.query}")
        count_tag = ""
        if pv.total_count == 0:
            count_tag = "  ⚠ zero results — query may be too specific or malformed"
        elif pv.total_count < 20:
            count_tag = "  ⚠ very few results — consider broader terms"
        elif pv.total_count > 2000:
            count_tag = "  ⚠ very many results — consider narrowing filters"
        print(f"  Results: {pv.total_count} total | Showing {len(pv.sample_titles)}/{pv.total_count}{count_tag}")

        if pv.sample_titles:
            for j, title in enumerate(pv.sample_titles, 1):
                print(f"    {j:>2}. {title[:100]}")
        else:
            print("    (no results to display)")


def _display_cross_query_keywords(previews: list[QueryPreview]) -> None:
    """Aggregate and display top keywords across all query previews."""
    all_kw: Counter[str] = Counter()
    for pv in previews:
        for kw in pv.top_keywords:
            all_kw[kw] += 1
    if all_kw:
        top = all_kw.most_common(20)
        terms = ", ".join(f"{w} ({c})" for w, c in top)
        print(f"\n  Top keywords across all results: {terms}")


def _display_warnings(previews: list[QueryPreview]) -> None:
    """Show aggregated warnings about query quality."""
    warnings = []
    for i, pv in enumerate(previews, 1):
        if pv.total_count == 0:
            warnings.append(f"Query {i} returned zero results — remove or rewrite it")
        elif pv.total_count < 10:
            warnings.append(f"Query {i} returned only {pv.total_count} results — may miss relevant papers")
        elif pv.total_count > 5000:
            warnings.append(f"Query {i} returned {pv.total_count}+ results — Scopus caps at 5000; add filters")
    if not warnings:
        print()  # clean spacing
    for w in warnings:
        print(f"  ⚠ {w}")


# ── User interaction ────────────────────────────────────────────────────────

def _get_user_action() -> tuple[str, str]:
    """Prompt the user for next action. Returns (action, detail)."""
    print(f"\n{'─' * 80}")
    print("Actions:")
    for i, (action, desc) in enumerate(ACTION_OPTIONS, 1):
        print(f"  [{i}] {action:<12} — {desc}")
    print(f"{'─' * 80}")

    while True:
        choice = input("Choice [1-7]: ").strip()
        if choice in ("1", "2", "3", "4", "5", "6", "7"):
            action, _ = ACTION_OPTIONS[int(choice) - 1]
            return action, ""
        elif choice:
            print(f"  Invalid choice '{choice}' — enter 1–7")


def _handle_refine(queries: list[str], previews: list[QueryPreview]) -> list[str]:
    """Let the user edit or replace specific queries."""
    print("\nCurrent queries:")
    for i, q in enumerate(queries, 1):
        total = previews[i - 1].total_count if i - 1 < len(previews) else "?"
        print(f"  [{i}] {q}  ({total} results)")

    print("\nRefine options:")
    print("  <N>: <new query>   — replace query N with new text")
    print("  delete <N>         — remove query N")
    print("  done               — return refined list")
    print()

    while True:
        cmd = input("refine> ").strip()
        if not cmd:
            continue
        if cmd.lower() == "done":
            break
        if cmd.lower().startswith("delete "):
            try:
                idx = int(cmd.split()[1]) - 1
                if 0 <= idx < len(queries):
                    removed = queries.pop(idx)
                    print(f"  Removed: {removed}")
                else:
                    print(f"  Invalid index {idx + 1}")
            except (ValueError, IndexError):
                print(f"  Invalid format. Use: delete <N>")
        elif ":" in cmd:
            try:
                idx_str, new_query = cmd.split(":", 1)
                idx = int(idx_str.strip()) - 1
                if 0 <= idx < len(queries):
                    old = queries[idx]
                    queries[idx] = new_query.strip()
                    print(f"  Replaced #{idx + 1}: {old[:60]}... → {queries[idx][:60]}")
                else:
                    print(f"  Invalid index {idx + 1}")
            except ValueError:
                print(f"  Invalid format. Use: <N>: <new query>")
        else:
            print("  Unknown command. Use '<N>: <query>' or 'delete <N>' or 'done'")

    return queries


def _handle_filters(current_filters: dict) -> dict:
    """Interactive filter adjustment."""
    print("\nCurrent filters:")
    _print_active_filters(current_filters)
    print()
    print("Filter options:")
    print("  year <from>-<to>   — set year range (e.g. 'year 2010-2024')")
    print("  subject <code>     — set subject area (COMP, ENGI, ENER, ENVI, ...)")
    print("  doctype <code>     — set doc type (ar, re, cp, bk, ...)")
    print("  srctype <code>     — set source type (j, b, k, p, r, d)")
    print("  journal <title>    — restrict to journal title")
    print("  oa on|off          — toggle open-access only")
    print("  clear <filter>     — remove a specific filter")
    print("  clear all          — remove all filters")
    print("  done               — return with current filters")
    print()

    while True:
        cmd = input("filters> ").strip()
        if not cmd:
            continue
        if cmd.lower() == "done":
            break
        parts = cmd.split(None, 1)
        key = parts[0].lower()
        value = parts[1] if len(parts) > 1 else ""

        if key == "year" and "-" in value:
            lo, hi = value.split("-", 1)
            current_filters["year_from"] = int(lo.strip()) if lo.strip() else None
            current_filters["year_to"] = int(hi.strip()) if hi.strip() else None
            print(f"  Year range: {current_filters['year_from']}–{current_filters['year_to']}")
        elif key == "subject":
            current_filters["subject_area"] = value.strip().upper() if value else None
            print(f"  Subject area: {current_filters['subject_area']}")
        elif key == "doctype":
            current_filters["doc_type"] = value.strip() if value else None
            print(f"  Doc type: {current_filters['doc_type']}")
        elif key == "srctype":
            current_filters["src_type"] = value.strip() if value else None
            print(f"  Source type: {current_filters['src_type']}")
        elif key == "journal":
            current_filters["source_title"] = value.strip() if value else None
            print(f"  Journal: {current_filters['source_title']}")
        elif key == "oa":
            if value.lower() in ("on", "true", "yes", "1"):
                current_filters["open_access_only"] = True
            else:
                current_filters["open_access_only"] = False
            print(f"  Open access only: {current_filters['open_access_only']}")
        elif key == "clear":
            if value.lower() == "all":
                for k in current_filters:
                    current_filters[k] = None
                current_filters["open_access_only"] = False
                print("  All filters cleared")
            else:
                mapped = {
                    "year": ["year_from", "year_to"],
                    "subject": ["subject_area"],
                    "doctype": ["doc_type"],
                    "srctype": ["src_type"],
                    "journal": ["source_title"],
                    "oa": ["open_access_only"],
                }
                for fk in mapped.get(value.lower(), [value.lower()]):
                    if fk in current_filters:
                        if fk == "open_access_only":
                            current_filters[fk] = False
                        else:
                            current_filters[fk] = None
                print(f"  Cleared: {value}")
        else:
            print(f"  Unknown filter command: {cmd}")

    return current_filters


def _handle_add(queries: list[str]) -> list[str]:
    """Let the user add new queries."""
    print("\nEnter new queries (one per line). Empty line to finish.")
    new_queries = []
    i = 1
    while True:
        q = input(f"  query {i}> ").strip()
        if not q:
            break
        new_queries.append(q)
        i += 1
    if new_queries:
        print(f"  Added {len(new_queries)} queries")
    return new_queries


# ── State persistence ───────────────────────────────────────────────────────

def _save_state(
    state: CalibrationState,
    output_dir: Path | None,
    config: dict,
) -> None:
    """Save calibration state to a YAML file for reproducibility."""
    if output_dir is None:
        output_dir = Path(config.get("output", {}).get("dir", "./output"))
    calib_dir = Path(output_dir) / "calibration"
    calib_dir.mkdir(parents=True, exist_ok=True)

    # Find next available filename
    existing = sorted(calib_dir.glob("calibration_*.yaml"))
    next_num = len(existing) + 1
    path = calib_dir / f"calibration_{next_num:03d}.yaml"

    data = {
        "final_queries": state.final_queries,
        "final_filters": state.final_filters,
        "rounds": [
            {
                "round": cr.round_num,
                "queries": cr.queries,
                "filters": cr.filters,
                "action": cr.action,
                "action_detail": cr.action_detail,
                "previews": [
                    {
                        "query": pv.query,
                        "total_count": pv.total_count,
                        "sample_titles": pv.sample_titles,
                        "top_keywords": pv.top_keywords,
                    }
                    for pv in cr.previews
                ],
            }
            for cr in state.rounds
        ],
    }
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    print(f"\nCalibration state saved → {path}")


def load_calibration_state(path: Path) -> tuple[list[str], dict[str, Any]]:
    """Load a previously saved calibration state YAML file.

    Returns (queries, filters) ready to pass to the full search.
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    queries = data.get("final_queries", [])
    filters = data.get("final_filters", {})
    return queries, filters

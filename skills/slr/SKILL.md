---
name: slr
description: Systematic Literature Review. Define research question → build queries with filters → search (Scopus or Semantic Scholar) → embed + rank → export XLSX → generate charts. Use when the user wants a structured literature review.
argument-hint: "[topic or --input <file>]"
---

# Systematic Literature Review — SLR Pipeline

Conducts a structured SLR following standard methodology: scoped queries → database search → embedding-based relevance ranking → XLSX export → visualisation charts.

**Two database backends — both share the same flow.** The workflow is:
1. Pick a database (Scopus or Semantic Scholar)
2. Pick input file and topics
3. Build queries with filters
4. Search → embed → rank → export → charts → download

## Database Choice

| Feature | Scopus | Semantic Scholar |
|---------|--------|-----------------|
| Query syntax | Boolean (`TITLE-ABS-KEY(...)`, `AND/OR`) | Short keywords (3–5, token-ANDed) |
| Filters | Year, subject area, doc type, src type, journal, OA | Year only |
| Abstract enrichment | Separate API call (quota-limited) | Included in bulk search |
| OA PDFs | Via Elsevier API | Direct `openAccessPdf.url` |
| Rate limit | 9 req/s, 20k/week search, 10k/week abstracts | 1 req/s (shared pool) or 1 req/s (API key) |
| Calibration | Interactive loop supported | Not available |
| API key | `SCOPUS_API_KEY` (required) | `SEMANTIC_SCHOLAR_API_KEY` (optional) |
| Speed | Slow (abstract enrichment phase) | Fast |

## Prerequisites

| Requirement | Scopus | Sem. Scholar |
|-------------|--------|-------------|
| API key | `SCOPUS_API_KEY` in `.env` | `SEMANTIC_SCHOLAR_API_KEY` in `.env` (optional) |
| Input embedded | `scan_input.py --list` | `scan_input.py --list` |
| matplotlib + seaborn | `uv pip install matplotlib seaborn` | same |
| scikit-learn | already in deps | already in deps |

## Quick Run

```bash
# Scopus — multiple queries, year + subject area filters
PYTHONPATH=src .venv/bin/python skills/slr/slr_scopus.py \
  --input "china_steel_soe_supply_chain.md" \
  --queries 'TITLE-ABS-KEY("steel" AND decarbon*) AND china;TITLE-ABS-KEY("green steel" OR "low-carbon steel")' \
  --max-results 200 --year-from 2015 --subject-area ENER \
  --no-download

# Semantic Scholar — short keyword queries, year filter
PYTHONPATH=src .venv/bin/python skills/slr/slr_semantic_scholar.py \
  --input "china_steel_soe_supply_chain.md" \
  --queries "China steel decarbonization barriers;Chinese steel SOE policy;steel supply chain emissions" \
  --max-results 100 --year-from 2015 \
  --no-download
```

## Shared CLI Flags (both databases)

| Flag | Default | Description |
|------|---------|-------------|
| `--input <name>` | — | Load cached embedding from `input/embeddings/` |
| `--query <str>` | — | Single query string |
| `--queries <str>` | — | Semicolon-separated list of queries |
| `--query-topics <str>` | — | Semicolon-separated topic labels (parallel to `--queries`) |
| `--max-results <N>` | 200/50 | Max papers per query |
| `--top-n <N>` | all | Top-ranked papers to export |
| `--year-from <YYYY>` | — | Start year |
| `--year-to <YYYY>` | — | End year |
| `--threshold <float>` | 0.0 | Minimum cosine similarity score |
| `--no-download` | false | Skip all PDF download phases |
| `--direct-delay <s>` | 1.0 | Seconds between direct HTTP requests |
| `--elsevier-delay <s>` | 2.0 | Seconds between Elsevier API requests |
| `--annas-delay <s>` | 3.0 | Seconds between Anna's Archive attempts |
| `--no-charts` | false | Skip chart generation |

## Scopus-only CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--subject-area <code>` | — | ASJC code: COMP, ENGI, ENER, ENVI, SOCI, ECON, … |
| `--doc-type <code>` | — | ar, re, cp, bk, ch, … |
| `--src-type <code>` | — | j, b, k, p, r, d |
| `--source-title <str>` | — | Restrict to journal title |
| `--open-access` | false | OA papers only |
| `--no-abstract-enrich` | false | Skip Abstract Retrieval API (conserves quota) |
| `--no-elsevier-download` | false | Skip Elsevier Full Text API download phase |
| `--calibrate` | false | Interactive query calibration loop |
| `--queries-file <path>` | — | Load from saved calibration YAML |

## Query Syntax by Database

### Scopus
Full Boolean syntax with field codes. Key operators: `TITLE-ABS-KEY(...)`, `AND`, `OR`, `AND NOT`, `"..."` loose phrase, `{...}` exact phrase, `*` wildcard.

### Semantic Scholar
`/paper/search/bulk` **ANDs every token** — no Boolean operators:
- **Good**: `China steel decarbonization barriers` (3–5 keywords)
- **Bad**: `China AND steel OR iron AND (decarbonization OR green)`
- Long phrase queries return 0 hits.

## Steps Performed (both databases)

1. **Load input** — read cached embedding + text from `input/embeddings/`
2. **Build queries** — from `--query`/`--queries` or `KeywordExtractor` (LLM)
3. **Confirm queries** — print + filters, **wait for user approval** *(never skip)*
4. **Search** — fetch papers with pagination
5. **Enrich abstracts** (Scopus only) — Abstract Retrieval API (skip with `--no-abstract-enrich`)
6. **Embed + rank** — cosine similarity against input text
7. **Apply threshold** — drop below `--threshold`
8. **Export XLSX** — with `topic_label` column if `--query-topics` set
9. **Generate basic charts** — publications/year, top journals, thematic heatmap, score distribution
10. **Download PDFs** — direct HTTP → Elsevier API → Anna's Archive fallback

### Post-SLR analysis (MANDATORY — 3 phases, run after steps 1-10)

The basic SLR pipeline produces an XLSX and simple charts. For academic-quality output, you MUST continue with the full post-SLR analysis pipeline documented in `skills/test-slr-analysis/SKILL.md`. The flow is:

**Phase 2 — Abstract enrichment & re-rank (MANDATORY for Scopus)**
11. **Recover missing abstracts** — `skills/slr/recover_abstracts.py` fills in papers that lack abstracts via Scopus Abstract Retrieval API
12. **Re-embed + re-rank** — `skills/slr/slr_rank.py` re-computes embeddings for ALL papers using freshly enriched abstracts, then re-ranks by cosine similarity against input text. This produces better scores than the in-search embedding (which used empty abstracts for some papers).

**Phase 3 — Post-SLR analysis (MANDATORY)**
13. **Keyword verification** — `enrich_keyword_clean.py` with term buckets per topic → splits into `keyword_verified_clean` (matched) and `missing_topic_only_clean` (unmatched) sheets
14. **Journal exclusion** — filter noisy journals via `--exclude-journals "Title1|Title2|..."` (pipe-separated, case-insensitive)
15. **Run all 10 analyses** — `run_all_analyses.py` generates 18 charts across both sheets in 3-phase structure

**NEVER stop after step 8.** Always offer Phase 2 (re-rank) → Phase 3 (analysis).

## Output Structure

```
output/<input_stem>/
└── SLR_<Source>_<tag>/
    ├── SLR_<Source>_<tag>.xlsx
    ├── charts/
    │   ├── publications_per_year.png
    │   ├── top_journals.png
    │   ├── thematic_heatmap.png
    │   ├── score_distribution.png
    │   └── analysis/                         ← Post-SLR analysis charts
    │       ├── keyword_clean/               (keyword-matched papers)
    │       │   ├── 1_profiling/  1.1_yearly_trend.png, 1.2_citations.png,
    │       │   │                  1.3_journal_coverage.png, 1.4_subset_overlap.png
    │       │   ├── 2_content/    2.1_keyword_network.png, 2.2_topic_modeling.png,
    │       │   │                  2.3_geographic.png
    │       │   └── 3_visuals/    3.1_wordclouds_by_subset.png, 3.2_subset_tfidf.png
    │       └── missing_clean/               (non-matching papers)
    │           ├── 1_profiling/  1.1_yearly_trend.png, 1.2_citations.png,
    │           │                  1.3_journal_coverage.png
    │           ├── 2_content/    2.1_keyword_network.png, 2.2_topic_modeling.png,
    │           │                  2.3_geographic.png
    │           └── 3_visuals/    3.1_wordcloud_overall.png
    └── downloads/
```

Tag format: `q<N>_max<M>_y<from>-<to>[_<subj>]`

## Interaction Rule

All user prompts MUST be selection-based via `AskUserQuestion` with 2–4 concrete options and a `(Recommended)` default. **Ask parameters first (sequential), then draft queries, then present both together in one final confirmation.** Never bundle parameter defaults into the query-approval prompt. For SLR, default to comprehensive mode: `--max-results 100`, `--top-n` unset (export all), `--threshold 0.0`.

## Topic-label Rule

When generating N queries, also generate N short topic labels and pass via `--query-topics "L1;L2;...;LN"`. Writes `topic_label` column in the xlsx.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Scopus 403 | IP not whitelisted | Check institutional entitlements |
| Scopus abstract enrichment all fail | Quota exhausted | Run `recover_abstracts.py`; check `X-RateLimit-Remaining` |
| Scopus >5000 truncated | Result cap | Split by year range |
| Semantic Scholar 0 results | Query too long | Shorten to 3–5 keywords |
| Semantic Scholar 429 | Rate limit | Increase `query_delay` in config |
| Semantic Scholar PDF fails | Paywalled | Falls through to Elsevier API → Anna's Archive |

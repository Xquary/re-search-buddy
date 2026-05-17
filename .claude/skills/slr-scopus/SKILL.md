---
name: slr-scopus
description: Systematic Literature Review via Scopus. Define research question → build queries with field/year filters → search Scopus with pagination → embed + rank → export full candidate list → generate visualisation charts (publications over time, journals, thematic clusters). Use when the user wants to conduct a structured literature review on a topic.
argument-hint: "[topic or --input <file>]"
---

# Systematic Literature Review — Scopus Pipeline

Conducts a structured SLR following standard methodology: scoped queries with inclusion/exclusion filters → Scopus search → embedding-based relevance ranking → XLSX export → visualisation charts.

## SLR Methodology Mapping

| SLR Step | Implementation |
|----------|---------------|
| 1. Research question (PICOT) | User-defined; drives query construction |
| 2. Inclusion / exclusion criteria | `--year-from/to`, `--subject-area`, `--doc-type`, `--src-type`, `--open-access`, similarity threshold |
| 3. Comprehensive search | Scopus REST API (STANDARD view, up to 200/request), multiple queries, deduplication by DOI/Scopus ID |
| 4. Quality appraisal | Cosine similarity ranking against input text; citation count column |
| 5. Data extraction | Full metadata → XLSX (all STANDARD view fields + author keywords + affiliations) |
| 6. Synthesis / interpretation | Visualisation charts: yearly trend, top journals, thematic heatmap, score distribution |

## Prerequisites

| Requirement | How to check/setup |
|-------------|-------------------|
| Scopus API key | `echo $SCOPUS_API_KEY` — set in `.env` |
| Input file embedded | `PYTHONPATH=src .venv/bin/python scan_input.py --list` |
| matplotlib + seaborn | `uv pip install matplotlib seaborn` |
| scikit-learn (TF-IDF) | already installed via project deps |

## Quick Run

```bash
# Single query, 200 results, all ranked, charts generated
PYTHONPATH=src .venv/bin/python slr_scopus.py \
  --input "Seeds of Green_Methodology.pdf" \
  --query "agent-based modelling supply chain decarbonization" \
  --max-results 200 \
  --year-from 2010 \
  --subject-area COMP \
  --doc-type ar \
  --no-download

# Multiple queries (semicolon-separated)
PYTHONPATH=src .venv/bin/python slr_scopus.py \
  --input "Seeds of Green_Methodology.pdf" \
  --queries "agent-based modelling supply chain;multi-agent systems decarbonization;ABM industrial simulation" \
  --max-results 200 \
  --year-from 2010 \
  --subject-area ENGI
```

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--input <name>` | — | Load cached embedding from `input/embeddings/` |
| `--query <str>` | — | Single Scopus query string |
| `--queries <str>` | — | Semicolon-separated list of queries |
| `--max-results <N>` | 200 | Max papers per query (up to 200 in one request; paginates beyond that) |
| `--top-n <N>` | all | Top-ranked papers to export; defaults to all retrieved |
| `--year-from <YYYY>` | — | Start of year range (uses `date` param: `YYYY-2099`) |
| `--year-to <YYYY>` | — | End of year range (uses `date` param: `1000-YYYY`) |
| `--subject-area <code>` | — | ASJC subject area code (see table below) |
| `--doc-type <code>` | — | Scopus document type code (see table below) |
| `--src-type <code>` | — | Source type: `j` journal, `b` book, `k` book series, `p` conference, `r` report, `d` trade |
| `--source-title <str>` | — | Restrict to specific journal: `SRCTITLE("Nature Energy")` |
| `--open-access` | false | Filter to open-access papers only (`OPENACCESS(1)`) |
| `--threshold <float>` | 0.0 | Minimum cosine similarity score to include |
| `--no-download` | false | Skip **all** PDF download phases |
| `--no-elsevier-download` | false | Skip Elsevier Full Text API phase only |
| `--direct-delay <s>` | 1.0 | Seconds between direct HTTP requests |
| `--elsevier-delay <s>` | 2.0 | Seconds between Elsevier API requests (max 9 req/s) |
| `--annas-delay <s>` | 3.0 | Seconds between Anna's Archive attempts |
| `--no-charts` | false | Skip chart generation |
| `--no-abstract-enrich` | false | Skip abstract retrieval API calls (saves quota) |
| `--calibrate` | false | Enable interactive query calibration loop before full search |
| `--preview-size <N>` | 5 | Papers per query to fetch during calibration preview |
| `--calibrate-rounds <N>` | 5 | Maximum calibration rounds before auto-continue |
| `--queries-file <path>` | — | Load queries & filters from a saved calibration YAML file |

## Scopus Query Syntax

### Key Field Codes

| Code | Searches | Example |
|------|----------|---------|
| `TITLE-ABS-KEY` | Title + abstract + keywords | `TITLE-ABS-KEY(agent-based model)` |
| `TITLE` | Article title only | `TITLE(supply chain decarbonization)` |
| `ABS` | Abstract | `ABS(Markov decision process)` |
| `KEY` | Keywords (author + indexed) | `KEY(green steel)` |
| `AUTHKEY` | Author-assigned keywords only | `AUTHKEY(ABM simulation)` |
| `SRCTITLE` | Journal/source title | `SRCTITLE("Journal of Cleaner Production")` |
| `SUBJAREA` | Subject area code | `SUBJAREA(COMP)` |
| `PUBYEAR` | Publication year | `PUBYEAR > 2009 AND PUBYEAR < 2025` |
| `DOCTYPE` | Document type | `DOCTYPE(ar)` |
| `SRCTYPE` | Source type | `SRCTYPE(j)` |
| `AFFILCOUNTRY` | Author country | `AFFILCOUNTRY(Australia)` |
| `OPENACCESS` | OA status | `OPENACCESS(1)` |
| `FUND-SPONSOR` | Funder name | `FUND-SPONSOR("ARC")` |
| `ALL` | All indexed fields | `ALL(agent-based steel)` |

### Boolean & Proximity Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `AND` | Both terms required | `agent-based AND steel` |
| `OR` | Either term | `ABM OR "agent-based model"` |
| `AND NOT` | Exclude term (use at end) | `steel AND NOT stainless` |
| `pre/n` | Within n words, ordered | `agent pre/3 model` |
| `w/n` | Within n words, any order | `supply w/2 chain` |
| `{...}` | Exact phrase | `{agent-based modelling}` |
| `"..."` | Loose phrase (wildcards ok) | `"agent* model"` |
| `?` | Single character wildcard | `modeli?ation` |
| `*` | Multi-character wildcard | `optim*` |

### Year Filtering
Prefer the `date` API parameter over inline `PUBYEAR` for cleaner queries:
- `date=2010-2024` → papers from 2010 to 2024 inclusive
- `date=2015-` → 2015 to present (use `2015-2099`)

### Document Type Codes (`DOCTYPE`)

| Code | Type |
|------|------|
| `ar` | Article |
| `re` | Review |
| `cp` | Conference paper |
| `bk` | Book |
| `ch` | Book chapter |
| `ed` | Editorial |
| `le` | Letter |
| `no` | Note |
| `sh` | Short survey |
| `ab` | Abstract report |

### Source Type Codes (`SRCTYPE`)

| Code | Type |
|------|------|
| `j` | Journal |
| `b` | Book |
| `k` | Book series |
| `p` | Conference proceedings |
| `r` | Report |
| `d` | Trade publication |

## API Details

### Search Endpoint
`GET https://api.elsevier.com/content/search/scopus`

| Parameter | Notes |
|-----------|-------|
| `query` | Full Boolean query string |
| `count` | Results per request; **max 200 with STANDARD view** |
| `start` | Pagination offset (0-based) |
| `sort` | `coverDate`, `relevancy`, `citedby-count`, `pubyear`, `publicationName` (prefix `-` for desc) |
| `date` | Year range: `YYYY-YYYY` |
| `subj` | Subject area code (same as SUBJAREA field) |
| `view` | `STANDARD` (max 200/req) or `COMPLETE` (max 25/req, more fields) |
| `field` | Comma-delimited list to request specific fields only |

**Total result cap**: 5,000 items per query without cursor-based pagination. For queries returning >5,000, split by year range or add filters.

### STANDARD View Response Fields

| Field | Description |
|-------|-------------|
| `dc:identifier` | Scopus ID |
| `eid` | Electronic ID |
| `dc:title` | Title |
| `dc:creator` | First author |
| `author` | Full author list (id, name, initials) |
| `affiliation` | Affiliation array (org, city, country, id) |
| `prism:publicationName` | Journal/source title |
| `prism:issn` / `prism:eissn` | Print/electronic ISSN |
| `prism:volume` / `prism:issueIdentifier` | Volume / issue |
| `prism:pageRange` | Page range |
| `prism:coverDate` | Publication date (YYYY-MM-DD) |
| `prism:doi` | DOI |
| `subtype` | Document type code |
| `subtypeDescription` | Document type description (full text) |
| `prism:aggregationType` | Source type |
| `citedby-count` | Citation count |
| `authkeywords` | Author keywords |
| `openaccess` / `openaccessFlag` | Open access status |
| `pubmed-id` | PubMed ID (if indexed) |
| `link` | URLs: self, scopus, scopus-citedby |

Note: `dc:description` (abstract) is **not** in STANDARD view — requires Abstract Retrieval API call per paper.

### Abstract Retrieval Endpoint
`GET https://api.elsevier.com/content/abstract/scopus_id/{id}`

- Returns full abstract in `coredata.dc:description`
- Also returns complete author list, affiliations, funding, references
- **Weekly quota: 10,000 requests** — use `--no-abstract-enrich` to conserve

### Rate Limits & Quotas

| API | Weekly quota | Throttle |
|-----|-------------|---------|
| Scopus Search | 20,000 requests | 9 req/s |
| Abstract Retrieval | 10,000 requests | 9 req/s |

Quota headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (epoch seconds).

## Steps Performed

1. **Load input** — read cached embedding + text from `input/embeddings/`
2. **Build queries** — use `--query`/`--queries` if provided; otherwise call `KeywordExtractor` (LLM)
3. **Confirm queries** — print queries + all active filters and **wait for user approval** *(never skip)*
4. **Search Scopus** — fetch up to `--max-results` papers per query using STANDARD view (200/request), paginating if needed; apply `date`, `subj`, and inline query filters
5. **Enrich abstracts** — fetch full abstracts via Abstract Retrieval API (skip with `--no-abstract-enrich`)
6. **Embed + rank** — embed all candidates against input text; rank by cosine similarity
7. **Apply threshold** — drop papers below `--threshold` similarity score
8. **Export XLSX** — write all ranked papers to output directory
9. **Generate charts** — save PNG charts to `charts/` subdirectory
10. **Download PDFs** — four phases, each only attempts papers not yet downloaded:
    - **Phase 1** (direct HTTP, `--direct-delay`): papers with `pdf_url` set
    - **Phase 1.5** (Elsevier Full Text API, `--elsevier-delay`): all papers with DOI; works automatically from institutional IP using `SCOPUS_API_KEY`; covers ScienceDirect journals only
    - **Phase 2** (browser, off by default): Chrome DevTools with institutional cookies
    - **Phase 3** (Anna's Archive, `--annas-delay`): last resort for everything else
    - Skip all with `--no-download`; skip only Elsevier phase with `--no-elsevier-download`

## Query Calibration Workflow

Instead of one-shot queries, use `--calibrate` for an iterative refinement loop:

```bash
# Interactive calibration — LLM generates initial queries
PYTHONPATH=src .venv/bin/python slr_scopus.py \
  --input "Seeds of Green_Methodology.pdf" \
  --calibrate --max-results 200 --year-from 2016

# Start calibration from user-provided queries
PYTHONPATH=src .venv/bin/python slr_scopus.py \
  --input "Seeds of Green_Methodology.pdf" \
  --calibrate --queries "ABM energy market;multi-agent system energy transition" \
  --max-results 200

# Resume from saved calibration state
PYTHONPATH=src .venv/bin/python slr_scopus.py \
  --input "Seeds of Green_Methodology.pdf" \
  --queries-file output/<stem>/slr/<project>/calibration_001.yaml \
  --max-results 200
```

**Calibration loop actions:**
1. **continue** — use current queries for full search
2. **refine** — edit/replace specific queries
3. **filters** — adjust year, subject area, doc type, etc.
4. **add** — append new queries
5. **regenerate** — LLM generates different angle
6. **save** — persist queries + filters to YAML, exit
7. **exit** — discard and exit

**Pre-calibration preview** — use `_preview_slr.py` to check result counts before entering the loop:
```bash
PYTHONPATH=src .venv/bin/python _preview_slr.py
```

**Query records** — each SLR project keeps a `.md` log in `output/<input_stem>/slr/<project>/` recording query variants, result counts, and run history.

## Output Structure

```
output/<input_stem>/
├── search/                            # regular (non-SLR) pipeline runs
│   ├── arXiv_top10_select10/
│   ├── Scholar_top10_select10/
│   └── ...
└── slr/                               # SLR projects
    └── <project>/                     # one SLR project
        ├── slr-scopus-<topic>.md      # query variants, counts, run history
        ├── calibration_<NNN>.yaml     # saved calibration states
        └── SLR_Scopus_<tag>/          # search run output
            ├── SLR_Scopus_<tag>.xlsx
            ├── charts/
            │   ├── publications_per_year.png
            │   ├── top_journals.png
            │   ├── thematic_heatmap.png
            │   └── score_distribution.png
            └── downloads/
                └── <paper>.pdf
```

Tag format: `q<N>_max<N>_y<from>-<to>_<subj>`  
Example: `q3_max200_y2010-2024_COMP`

## XLSX Columns

| Column | Source field |
|--------|-------------|
| `rank` | Cosine similarity rank |
| `score` | Cosine similarity (0–1) |
| `title` | `dc:title` |
| `retrieval_query` | Which query retrieved this paper |
| `authors` | `author` array (full list) |
| `first_author` | `dc:creator` |
| `year` | `prism:coverDate[:4]` |
| `journal` | `prism:publicationName` |
| `issn` | `prism:issn` |
| `volume` | `prism:volume` |
| `issue` | `prism:issueIdentifier` |
| `pages` | `prism:pageRange` |
| `doc_type` | `subtypeDescription` |
| `src_type` | `prism:aggregationType` |
| `doi` | `prism:doi` |
| `scopus_id` | `dc:identifier` |
| `citations` | `citedby-count` |
| `open_access` | `openaccessFlag` |
| `author_keywords` | `authkeywords` |
| `affiliations` | `affiliation` array (org; city; country) |
| `url` | scopus link |
| `abstract` | from Abstract Retrieval API |

## Chart Details

### `publications_per_year.png`
Bar chart of paper count by year across the candidate set.

### `top_journals.png`
Horizontal bar chart of top 15 journals by paper count.

### `thematic_heatmap.png`
Heatmap: rows = top 20 TF-IDF keywords extracted from titles/abstracts, columns = year bins (2-year windows). Shows thematic shifts over time.

### `score_distribution.png`
Histogram of cosine similarity scores. Helps calibrate `--threshold`.

## Script Reference

**`slr_scopus.py`** — main SLR pipeline script. Complete ✓ — one-shot mode, calibration mode, charts, download.  
**`src/research_finder/slr/charts.py`** — chart generation module. Complete ✓ — 4 chart types: publications/year, top journals, thematic heatmap, score distribution.  
**`src/research_finder/slr/query_calibrator.py`** — interactive query calibration loop. Complete ✓ — preview search, refine/filter/add/regenerate actions, YAML state save/load.  
**`_preview_slr.py`** — ad-hoc Scopus query counter for quick result-count previews before calibration.

Key improvements over `test_scopus_pipeline.py`:
- Use `date` API param for year filtering (cleaner than inline `PUBYEAR`)
- Request `view=STANDARD` explicitly with `count=200`
- Parse `author` array for full author list (not just `dc:creator`)
- Parse `affiliation` array for org/city/country
- Parse `subtypeDescription` for human-readable doc type
- Parse `authkeywords` for keyword analysis
- Parse `openaccessFlag` for OA filtering/flagging
- `--no-abstract-enrich` flag to conserve weekly quota (10k limit)

## Subject Area Codes

| Code | Area |
|------|------|
| `COMP` | Computer Science |
| `ENGI` | Engineering |
| `ENER` | Energy |
| `ENVI` | Environmental Science |
| `SOCI` | Social Sciences |
| `ECON` | Economics, Econometrics and Finance |
| `BUSI` | Business, Management and Accounting |
| `DECI` | Decision Sciences |
| `MATH` | Mathematics |
| `MATE` | Materials Science |
| `MULT` | Multidisciplinary |
| `PHYS` | Physics and Astronomy |
| `CHEM` | Chemistry |
| `EART` | Earth and Planetary Sciences |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `SCOPUS_API_KEY` not found | `.env` not loaded | Check `dotenv.load_dotenv()` at top of script |
| < 10 results for narrow query | Query too specific | Broaden; use `TITLE-ABS-KEY` instead of `TITLE` |
| 403 error | Institutional IP not whitelisted | Check Elsevier entitlements; API key may need IP registration |
| Abstract column empty | `--no-abstract-enrich` set or quota hit | Check `X-RateLimit-Remaining` header; abstracts need separate API call |
| > 5000 results truncated | Scopus result cap | Split query by year range or add more filters |
| `429 Too Many Requests` | Rate limit hit (9 req/s) | Increase `query_delay`; current throttle is 9 req/s |
| Chart import error | matplotlib/seaborn missing | `uv pip install matplotlib seaborn` |

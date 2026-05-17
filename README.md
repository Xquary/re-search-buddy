# Re-Search Buddy

Find academically relevant papers based on your research question or writing. Search across arXiv, Semantic Scholar, Google Scholar, and CNKI, rank results by relevance, and export to structured xlsx with optional PDF downloads.

## Quick Start

```bash
git clone https://github.com/Xquary/re-search-buddy.git
cd re-search-buddy
python -m venv .venv && source .venv/bin/activate
uv sync  # or: pip install -e .
cp .env.example .env   # edit with your API keys
```

## API Keys

| Key | Required? | Purpose |
|-----|-----------|---------|
| `OPENAI_API_KEY` | **Required** | Embeddings + keyword extraction |
| `SEMANTIC_SCHOLAR_API_KEY` | Recommended | Semantic Scholar dedicated rate limit |
| `SCOPUS_API_KEY` | Optional | Scopus search + Elsevier PDF downloads |
| `ANNAS_SECRET_KEY` | Optional | Anna's Archive PDF fallback |
| `ZOTERO_API_KEY` | Optional | Zotero library integration |

Set them in `.env` (never commit this file).

---

## Three Workflows

This tool supports three main research workflows. Each starts from a piece of text you provide and ends with a ranked xlsx of relevant papers.

### 1. Topic Search — Find papers on a research topic

**What it does:** Takes your topic description or research paragraph, generates search queries, searches across databases, ranks papers by relevance to your text, and exports the top-N matches.

**What goes in:** A `.md`, `.txt`, `.docx`, or `.pdf` file describing your research topic. Drop it in `input/raw/`, then scan:

```bash
# Step 1 — prepare your input
cp ~/Downloads/my_research_question.md input/raw/
PYTHONPATH=src .venv/bin/python skills/test-input-scan/scan_input.py

# Step 2 — search (pick a backend)
# Semantic Scholar (fastest, recommended)
PYTHONPATH=src .venv/bin/python skills/test-semantic-scholar/test_semantic_scholar_pipeline.py \
  --input "my_research_question.md" --max-per-query 50 --top-n 10 --year-from 2020

# arXiv (for STEM topics)
PYTHONPATH=src .venv/bin/python skills/test-arxiv/test_arxiv_pipeline.py \
  --input "my_research_question.md" --max-per-query 10 --top-n 10

# Google Scholar (broadest coverage)
PYTHONPATH=src .venv/bin/python skills/test-scholar/test_pipeline.py \
  --input "my_research_question.md" --max-per-query 10 --top-n 10
```

**What comes out:**
```
output/my_research_question/
└── SemanticScholar_top50_select10/
    ├── SemanticScholar_top50_select10.xlsx   ← ranked paper list
    └── downloads/                            ← PDF papers (optional)
```

**xlsx columns:** rank, score (cosine similarity 0–1), title, authors, year, publication, document_type, doi, citations, abstract, url, pdf_url, retrieval_query.

---

### 2. Systematic Literature Review (SLR) — Comprehensive review with charts

**What it does:** Structured review following standard methodology — multiple queries, comprehensive retrieval (no result cap), embedding-based relevance ranking, full candidate export, and visualisation charts (yearly trend, top journals, thematic heatmap, score distribution).

**What goes in:** A `.md` file with your research scope, plus your search queries. Two database options:

```bash
# Scopus — Boolean queries with field codes, subject/doc-type filters
PYTHONPATH=src .venv/bin/python skills/slr/slr_scopus.py \
  --input "my_scope.md" \
  --queries 'TITLE-ABS-KEY("steel" AND decarbon*) AND china;TITLE-ABS-KEY("green steel" OR "low-carbon steel")' \
  --query-topics "DecarbPathways;GreenSteel" \
  --max-results 200 --year-from 2015 --subject-area ENER

# Semantic Scholar — short keyword queries (3-5 keywords, AND-ed automatically)
PYTHONPATH=src .venv/bin/python skills/slr/slr_semantic_scholar.py \
  --input "my_scope.md" \
  --queries "China steel decarbonization barriers;China steel SOE governance;steel supply chain emissions" \
  --query-topics "Barriers;SOE;SupplyChain" \
  --max-results 100 --year-from 2015
```

Common flags: `--year-from YYYY`, `--year-to YYYY`, `--threshold 0.0` (minimum score), `--no-download`, `--no-charts`.

**What comes out:**
```
output/my_scope/
└── SLR_SemanticScholar_q3_max100_y2015-x/
    ├── SLR_SemanticScholar_q3_max100_y2015-x.xlsx   ← all ranked papers
    ├── charts/
    │   ├── publications_per_year.png                ← yearly publication trend
    │   ├── top_journals.png                         ← top 15 journals
    │   ├── thematic_heatmap.png                     ← keyword themes over time
    │   └── score_distribution.png                   ← similarity score histogram
    └── downloads/                                   ← PDF papers (optional)
```

**xlsx columns** (SLR adds): topic_label, first_author, journal/venue, affiliations (Scopus), scopus_id, open_access, author_keywords.

---

### 3. Citation Gap Fill — Find papers for placeholder citations

**What it does:** You have a draft with placeholder citations (marked as XX, XXX, etc.). The tool extracts each citation context, generates targeted queries per gap, searches Google Scholar, ranks candidates, and maps the best paper to each citation slot.

**What goes in:** A `.md` file containing your draft text with `[XX]` or `[XXX]` markers where you need citations.

Example draft:
```markdown
Recent research shows that SOE governance structures significantly
influence decarbonization outcomes [XX]. However, empirical evidence
from the Chinese steel sector remains limited [XX].

Scholars have debated whether carbon border adjustment mechanisms
create effective incentives [XX].
```

**Run it:**
```bash
PYTHONPATH=src .venv/bin/python skills/citation-search/test_<stem>.py
```

**What comes out:**
```
output/my_draft/
└── Scholar_top10_select10_citation_map.xlsx    ← papers mapped to citation slots
```

---

## Input File Preparation

Supported formats: `.md`, `.txt`, `.docx`, `.pdf`.

1. Drop your file in `input/raw/`
2. Run the scanner:
   ```bash
   PYTHONPATH=src .venv/bin/python skills/test-input-scan/scan_input.py
   ```
3. This extracts text, creates a `.md` copy, generates an embedding vector, and caches it
4. All pipelines then reference it via `--input <filename>`
5. To list cached inputs: `PYTHONPATH=src .venv/bin/python skills/test-input-scan/scan_input.py --list`

## Output Format

All workflows produce an `.xlsx` spreadsheet with:
- **rank** — position by cosine similarity
- **score** — cosine similarity to your input text (0–1)
- **title, authors, year, publication** — paper metadata
- **doi, citations, document_type** — bibliographic details
- **abstract** — full abstract
- **url, pdf_url** — links
- **retrieval_query** — which search query found this paper
- **topic_label** — (SLR only) the topic label for the query

PDF downloads (optional) are saved alongside the xlsx in a `downloads/` subdirectory.

## Backend Comparison

| Backend | Setup | Speed | Coverage | Best for |
|---------|-------|-------|----------|----------|
| Semantic Scholar | API key (optional) | Fast | 200M+ papers | Default choice, topic search, SLR |
| arXiv | arxiv-mcp-server | Medium | STEM | Math, physics, CS topics |
| Google Scholar | google-scholar-mcp-server | Slow | Broadest | Citation gaps, comprehensive |
| CNKI | Chrome + remote debugging | Slow | Chinese-language | China-specific research |
| Scopus | SCOPUS_API_KEY required | Slow | Broad | SLR with Boolean queries |

## Project Structure

```
re-search-buddy/
├── README.md
├── pyproject.toml
├── config.yaml
├── .env.example
├── src/research_finder/       # Core library
├── skills/                    # Pipeline scripts
│   ├── test-scholar/          # Google Scholar topic search
│   ├── test-arxiv/            # arXiv topic search
│   ├── test-semantic-scholar/ # Semantic Scholar topic search
│   ├── test-cnki/             # CNKI (Chinese) topic search
│   ├── test-pipeline/         # Full multi-source CLI
│   ├── test-input-scan/       # Input file cache
│   ├── test-mcp/              # MCP server health check
│   ├── citation-search/       # Citation gap fill workflow
│   ├── slr/                   # Systematic review (Scopus + Sem. Scholar)
│   ├── test-slr-analysis/     # Post-SLR data analysis & charts
│   ├── re-search-buddy/       # AI agent router (see below)
│   └── setup/                 # Environment setup wizard
├── input/                     # Your files (gitignored)
└── output/                    # Results (gitignored)
```

## Requirements

- Python 3.11+
- `OPENAI_API_KEY` for embeddings
- Optional: `uv` for package management

---

## For AI Agents (Claude, opencode, etc.)

If you're an AI agent helping a user with this tool, follow these instructions.

### Entry Point: `skills/re-search-buddy/SKILL.md`

**Always start here.** This is the top-level router. It will:

1. **Run setup** (`skills/setup/SKILL.md`) — checks Python packages → API keys → MCP/CLI tools. Each stage is independent: show results, only actionable/missing items are clickable, already-OK items are display-only.
2. **Classify the user's task** into one of:
   - Topic search → Section B of re-search-buddy
   - Systematic review (SLR) → Section C (pick Scopus or Semantic Scholar)
   - Citation gap fill → Section A (citation-search skill)
   - Test/debug a backend → Section D
   - Custom workflow → Section E
3. **Execute the workflow** by reading the relevant skill's `SKILL.md` and following its SOP step-by-step.

### Key Rules for Agents

- **Never skip re-search-buddy** — always consult it first before any pipeline script.
- **Ask parameters before queries** — sequential questions for max-per-query, top-n, year range, threshold; then draft queries with topic labels; then present everything together for final confirmation.
- **Confirm queries before searching** — never burn API credits without explicit approval.
- **Use `AskUserQuestion`** for every prompt — 2–4 clickable options, `(Recommended)` default first. Never ask users to type or paste values (except raw text content).
- **Each setup stage runs independently**: check → table → options (only missing/actionable items selectable).
- **For SLR, default to comprehensive mode** — max-results=100, top-n=all, threshold=0.0.
- **Match query syntax to the source** — Semantic Scholar uses 3–5 keywords (AND-ed); Scopus uses Boolean; Scholar/arXiv use loose phrases.
- **Warm, brief, and explicit** — the user may not be a coder.

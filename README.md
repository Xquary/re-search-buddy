# Re-Search Buddy

Find academically relevant papers based on your research question or writing. Search across arXiv, Semantic Scholar, Google Scholar, and CNKI, rank results by relevance, and export to structured xlsx with optional PDF downloads.

## Quick Start

```bash
git clone https://github.com/Xquary/research_finder.git
cd research_finder
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

## Usage

### Topic Search — Find papers on a topic

```bash
# First, scan your input file (creates cached embedding)
PYTHONPATH=src .venv/bin/python skills/test-input-scan/scan_input.py

# Then search with any backend
# Semantic Scholar (fastest, recommended)
PYTHONPATH=src .venv/bin/python skills/test-semantic-scholar/test_semantic_scholar_pipeline.py \
  --input "my_topic.md" --max-per-query 50 --top-n 10

# arXiv
PYTHONPATH=src .venv/bin/python skills/test-arxiv/test_arxiv_pipeline.py \
  --input "my_topic.md" --max-per-query 10 --top-n 10

# Google Scholar
PYTHONPATH=src .venv/bin/python skills/test-scholar/test_pipeline.py \
  --input "my_topic.md" --max-per-query 10 --top-n 10
```

### Systematic Literature Review (SLR)

```bash
# Scopus — Boolean queries, subject filters
PYTHONPATH=src .venv/bin/python skills/slr/slr_scopus.py \
  --input "my_topic.md" \
  --queries 'TITLE-ABS-KEY("steel" AND decarbon*) AND china' \
  --max-results 200 --year-from 2015

# Semantic Scholar — keyword queries
PYTHONPATH=src .venv/bin/python skills/slr/slr_semantic_scholar.py \
  --input "my_topic.md" \
  --queries "China steel decarbonization barriers" \
  --max-results 100 --year-from 2015
```

### Full CLI Pipeline

```bash
PYTHONPATH=src .venv/bin/python -m research_finder find input/my_topic.md
PYTHONPATH=src .venv/bin/python -m research_finder search input/my_topic.md
```

## Input Files

Drop `.md`, `.txt`, `.docx`, or `.pdf` files into `input/raw/`, then run:

```bash
PYTHONPATH=src .venv/bin/python skills/test-input-scan/scan_input.py
```

This extracts text, creates cached embeddings, and makes them available to all pipelines via `--input <stem>`.

## Output

Results land in `output/<stem>/<Source>_top<N>_select<M>/` containing:
- `<Source>_top<N>_select<M>.xlsx` — ranked paper metadata
- `downloads/` — downloaded PDFs (optional)

SLR runs create `output/<stem>/SLR_<Source>_<tag>/` with charts in `charts/`.

## Backend Comparison

| Backend | Setup | Speed | Coverage | Notes |
|---------|-------|-------|----------|-------|
| Semantic Scholar | API key (optional) | Fast | 200M+ papers | Recommended default |
| arXiv | arxiv-mcp-server | Medium | STEM only | Auto PDF download |
| Google Scholar | google-scholar-mcp-server | Slow | Broadest | May hit rate limits |
| CNKI | Chrome + remote debugging | Slow | Chinese-language | Needs npx + Chrome |
| Scopus | API key required | Slow | Broad | Boolean queries, charts |

## Project Structure

```
research_finder/
├── README.md
├── pyproject.toml
├── config.yaml
├── .env.example
├── src/research_finder/    # Core library
├── skills/                 # Pipeline scripts
│   ├── test-scholar/       # Google Scholar
│   ├── test-arxiv/         # arXiv
│   ├── test-semantic-scholar/  # Semantic Scholar
│   ├── test-cnki/          # CNKI (Chinese)
│   ├── test-pipeline/      # Full CLI
│   ├── test-input-scan/    # Input cache
│   ├── test-mcp/           # MCP health check
│   ├── citation-search/    # Citation gap fill
│   ├── slr/                # Systematic review
│   └── test-slr-analysis/  # Post-SLR analysis
├── input/                  # Your files (gitignored)
└── output/                 # Results (gitignored)
```

## Requirements

- Python 3.11+
- `OPENAI_API_KEY` for embeddings
- Optional: `uv` for package management

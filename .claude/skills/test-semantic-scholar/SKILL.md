---
name: test-semantic-scholar
description: Test Semantic Scholar pipeline (REST API → embed → rank → xlsx → download). Use to verify Semantic Scholar REST API integration end-to-end.
argument-hint: "[--input name] [--year-from YYYY] [--year-to YYYY] [--max-per-query N] [--top-n N]"
---

# Semantic Scholar Pipeline Test

End-to-end test: Semantic Scholar REST API search → API embedding → cosine similarity ranking → xlsx export → PDF download. Runs ``test_semantic_scholar_pipeline.py``.

Unlike other pipelines, this one **generates queries dynamically** via `KeywordExtractor` (LLM-based, gpt-4o-mini) from the input text.

## Prerequisites

- `.env` configured with `OPENAI_API_KEY` (for LLM queries + embeddings)
- (Recommended) `SEMANTIC_SCHOLAR_API_KEY` in `.env` — bumps rate limit to 1 req/s
- Project venv: `uv venv && uv pip install -e ".[dev]"`
- (Optional) `scan_input.py` has been run if using `--input <name>`

## Quick Run

```bash
# Default: hardcoded short TEXT, LLM-generated queries, top 10 from 50 results/query
PYTHONPATH=src .venv/bin/python test_semantic_scholar_pipeline.py

# With cached input embedding (queries derived from cached file text)
PYTHONPATH=src .venv/bin/python test_semantic_scholar_pipeline.py --input "my_file"

# With year filter
PYTHONPATH=src .venv/bin/python test_semantic_scholar_pipeline.py --year-from 2023 --max-per-query 100 --top-n 20
```

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--input <name>` | (none) | Use cached embedding from `input/embeddings/`; queries derived from cached text |
| `--year-from YYYY` | (none) | Native year filter via API `year` param |
| `--year-to YYYY` | (none) | Native year filter via API `year` param |
| `--max-per-query N` | 50 | Candidates requested per query |
| `--top-n N` | 10 | Final ranked papers in xlsx |

## Steps Performed

1. **Generate queries** — `KeywordExtractor.extract(TEXT)` using LLM (gpt-4o-mini)
2. **Search** — Semantic Scholar REST API via `SemanticScholarSearcher.search()`
3. **Year filter** — applied at API level via `year` query param
4. **Embed** — `text-embedding-3-small` via LiteLLM API
5. **Rank** — `cosine_similarity` → select top-N
6. **Export** — xlsx with 14 columns (includes citations, doi, pdf_url)
7. **Download** — open-access PDFs from `openAccessPdf.url`

## Expected Output

```
STEP 0: Generating search queries from input text
Generated N queries:
  - ...
STEP 1: Searching Semantic Scholar
Found N unique papers from Semantic Scholar
STEP 2: Embedding text and paper metadata
...
STEP 3: Ranking by cosine similarity
  #1  [score: 0.xxxx]  Paper Title...
STEP 4: Downloading PDFs
XLSX written to: output/<stem>/SemanticScholar_top<M>_select<N>/SemanticScholar_top<M>_select<N>.xlsx
```

**Output path**: `output/<input_stem>/SemanticScholar_top<per_query>_select<top_n>/SemanticScholar_top<per_query>_select<top_n>.xlsx` + `downloads/`

**XLSX columns**: rank, score, title, retrieval_query, authors, year, publication, document_type, doi, citations, source, url, pdf_url, abstract

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| 429 Too Many Requests | Rate limit exceeded without API key | Set `SEMANTIC_SCHOLAR_API_KEY` in `.env` |
| LLM query generation error | `OPENAI_API_KEY` missing | Check `.env`; fallback: hardcode queries |
| No open-access PDFs | Most papers behind paywalls | Expected; only ~30% have open-access PDFs |
| "No papers found" | Queries too specific | LLM-generated queries may be narrow; re-run |

## Key Difference

This is the only test pipeline that uses **dynamic LLM-generated queries** instead of hardcoded ones. If `--input <name>` is provided, queries are derived from the cached file's text rather than the hardcoded TEXT fallback.

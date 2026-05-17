---
name: test-scholar
description: Test Google Scholar search pipeline (Scholar → embed → rank → xlsx → download). Use to verify Scholar MCP integration end-to-end.
argument-hint: "[--input name] [--year-from YYYY] [--year-to YYYY] [--max-per-query N] [--top-n N]"
---

# Scholar Pipeline Test

End-to-end test: Google Scholar search → API embedding → cosine similarity ranking → xlsx export → PDF download. Runs ``skills/test-scholar/test_pipeline.py``.

## Prerequisites

- `.env` configured with `OPENAI_API_KEY` (for LiteLLM API embeddings)
- Project venv set up: `uv venv && uv pip install -e ".[dev]"`
- (Optional) `skills/test-input-scan/scan_input.py` has been run if using `--input <name>`
- Google Scholar MCP server accessible (may be throttled by Google)

## Quick Run

```bash
# Default: hardcoded TEXT, top 10 from 5 queries × 10 papers each
PYTHONPATH=src .venv/bin/python skills/test-scholar/test_pipeline.py

# With cached input embedding
PYTHONPATH=src .venv/bin/python skills/test-scholar/test_pipeline.py --input "my_file"

# With year filter and custom counts
PYTHONPATH=src .venv/bin/python skills/test-scholar/test_pipeline.py --year-from 2020 --year-to 2025 --max-per-query 20 --top-n 15
```

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--input <name>` | (none) | Use cached embedding from `input/embeddings/`. Accepts stem, raw filename, or .md filename. |
| `--year-from YYYY` | (none) | Post-hoc filter: exclude papers before this year |
| `--year-to YYYY` | (none) | Post-hoc filter: exclude papers after this year |
| `--max-per-query N` | 10 | Candidates requested per query |
| `--top-n N` | 10 | Final ranked papers in xlsx |

**Note**: Scholar has no native year filter at the MCP level — year filtering is applied post-search, so many results may be dropped.

## Steps Performed

1. **Input text** — hardcoded TEXT (green steel transition passage) or loaded from `--input` cache
2. **Search** — 5 hardcoded English queries via `ScholarSearcher.search()`
3. **Year filter** — post-hoc `filter_by_year()` if `--year-from`/`--year-to` given
4. **Embed** — `text-embedding-3-small` via LiteLLM API (text + all paper metadata)
5. **Rank** — `cosine_similarity` → select top-N
6. **Export** — `openpyxl` xlsx with 14 columns + CSV copy
7. **Download** — PDFs via `download_papers()` into `downloads/`

## Expected Output

```
STEP 1: Searching Google Scholar
...
Found N unique papers from Scholar

STEP 2: Embedding text and paper metadata
Text embedding: shape=(1536,)
Paper embeddings: shape=(N, 1536)

STEP 3: Ranking by cosine similarity
Top N papers (threshold=0.0):
  #1  [score: 0.xxxx]  Paper Title...

STEP 4: Downloading PDFs
XLSX written to: output/<stem>/Scholar_top<M>_select<N>/Scholar_top<M>_select<N>.xlsx
```

**Output path**: `output/<input_stem>/Scholar_top<per_query>_select<top_n>/Scholar_top<per_query>_select<top_n>.xlsx`

**XLSX columns**: rank, score, title, retrieval_query, authors, year, publication, publisher, document_type, doi, source, url, abstract, metadata_line

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "No papers found" | Google Scholar throttled the requests | Increase `query_delay` in config (default 3.0s); retry later |
| Empty Scholar results | Query too specific | Broaden queries; Scholar returns fewer results than requested |
| PDF download 403 | Publisher paywall | Expected; Anna's Archive fallback runs but may also fail |
| `OPENAI_API_KEY` missing | `.env` not loaded | Run `dotenv.load_dotenv()` or export the var |

## Hardcoded Queries

The script uses 5 queries about agent-based modeling, green steel, supply chain. Before running, review the QUERIES list in `skills/test-scholar/test_pipeline.py` — if the TEXT has changed and queries no longer match, propose new queries.

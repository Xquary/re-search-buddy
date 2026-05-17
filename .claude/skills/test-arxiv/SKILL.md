---
name: test-arxiv
description: Test arXiv search pipeline (arXiv → embed → rank → xlsx → download). Use to verify arXiv MCP integration end-to-end.
argument-hint: "[--input name] [--year-from YYYY] [--year-to YYYY] [--max-per-query N] [--top-n N]"
---

# arXiv Pipeline Test

End-to-end test: arXiv MCP search → API embedding → cosine similarity ranking → xlsx export → PDF download. Runs ``test_arxiv_pipeline.py``.

## Prerequisites

- `uv` installed; `arxiv-mcp-server` available via `uv tool run`
- `.env` configured with `OPENAI_API_KEY` (for LiteLLM API embeddings)
- Project venv: `uv venv && uv pip install -e ".[dev]"`
- (Optional) `scan_input.py` has been run if using `--input <name>`

## Quick Run

```bash
PYTHONPATH=src .venv/bin/python test_arxiv_pipeline.py

# With cached input embedding
PYTHONPATH=src .venv/bin/python test_arxiv_pipeline.py --input "my_file"

# Year filter + custom counts
PYTHONPATH=src .venv/bin/python test_arxiv_pipeline.py --year-from 2020 --year-to 2025 --max-per-query 20 --top-n 15
```

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--input <name>` | (none) | Use cached embedding from `input/embeddings/` |
| `--year-from YYYY` | (none) | arXiv native filter: `date_from` at MCP layer |
| `--year-to YYYY` | (none) | Passed to config; applied at MCP level |
| `--max-per-query N` | 10 | Candidates requested per query |
| `--top-n N` | 10 | Final ranked papers in xlsx |

**Note**: Unlike Scholar, arXiv applies year filtering at the MCP `search_papers` level (efficient — no post-hoc drop).

## Steps Performed

1. **Input text** — hardcoded TEXT or loaded from cache
2. **Search** — 5 hardcoded English queries via `ArxivSearcher.search()` with `date_from` parameter
3. **Year filter** — applied at MCP level; post-hoc `filter_by_year()` as safety net
4. **Embed** — `text-embedding-3-small` via LiteLLM API
5. **Rank** — `cosine_similarity` → select top-N
6. **Export** — xlsx with 10 columns
7. **Download** — arXiv PDFs (always accessible, no paywalls)

## Expected Output

```
STEP 1: Searching arXiv
Found N unique papers from arXiv

STEP 2: Embedding text and paper metadata
...
STEP 3: Ranking by cosine similarity
  #1  [score: 0.xxxx]  Paper Title...

STEP 4: Downloading PDFs
XLSX written to: output/<stem>/arXiv_top<M>_select<N>/arXiv_top<M>_select<N>.xlsx
```

**Output path**: `output/<input_stem>/arXiv_top<per_query>_select<top_n>/arXiv_top<per_query>_select<top_n>.xlsx` + `downloads/`

**XLSX columns**: rank, score, title, retrieval_query, authors, year, publication, source, url, abstract

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `❌ arxiv: FAILED` in logs | `arxiv-mcp-server` not found | `uv tool install arxiv-mcp-server` |
| Few or no results | Queries too specific for arXiv corpus | Broaden queries; arXiv is physics/CS-heavy |
| Year filter returns 0 | arXiv has few pre-2020 papers for niche queries | Widen year range or remove filter |
| PDF download fails | Network issue or arXiv rate limit | Retry; arXiv PDFs are always publicly accessible |

## Hardcoded Queries

Same 5 queries as `test_pipeline.py` (agent-based modeling, green steel, supply chain). If the TEXT has changed, update QUERIES in the script.

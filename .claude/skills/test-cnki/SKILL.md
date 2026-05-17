---
name: test-cnki
description: Test CNKI search pipeline (English→Chinese translate → CNKI Chrome DevTools MCP → embed → rank → xlsx). Use to verify CNKI integration end-to-end.
argument-hint: "[--input name] [--year-from YYYY] [--year-to YYYY]"
---

# CNKI Pipeline Test

End-to-end test: translate English queries to Chinese → CNKI Chrome DevTools MCP search → API embedding → cosine similarity ranking → xlsx export. Runs ``test_cnki_pipeline.py``.

**No download step** — CNKI requires login for PDF downloads.

## Prerequisites

- **Chrome** running with `--remote-debugging-port=9222` (WSL2: launch via PowerShell from Windows host)
- **Node.js / npx** available (`chrome-devtools-mcp` auto-fetched via `npx -y`)
- `.env` configured with `OPENAI_API_KEY` (for Chinese translation + API embeddings)
- Project venv: `uv venv && uv pip install -e ".[dev]"`
- No captcha active on CNKI (check Chrome manually if search fails)
- `search.cnki.region` in `config.yaml`: `"oversea"` (outside China) or `"china"` (inside China)

## Quick Run

```bash
# Default: hardcoded TEXT, 5 English queries translated to Chinese, top 10 from 50/query
PYTHONPATH=src .venv/bin/python test_cnki_pipeline.py

# With cached input embedding
PYTHONPATH=src .venv/bin/python test_cnki_pipeline.py --input "my_file"

# With year filter
PYTHONPATH=src .venv/bin/python test_cnki_pipeline.py --year-from 2020 --year-to 2025
```

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--input <name>` | (none) | Use cached embedding from `input/embeddings/` |
| `--year-from YYYY` | (none) | Post-hoc year filter |
| `--year-to YYYY` | (none) | Post-hoc year filter |

**Fixed constants** (imported from `cnki_searcher.py`):
- `PAPERS_PER_QUERY = 50` — collected across multiple result pages
- `FINAL_TOP_N = 10` — selected after embedding + cosine ranking

## Steps Performed

1. **Translate** — 5 English queries → Chinese keywords via LLM (gpt-4o-mini, `"2-4 short keywords"` prompt)
2. **Search** — CNKI via `CnkiSearcher.search()` using Chrome DevTools MCP (`navigate_page` + `evaluate_script`)
3. **Pagination** — collects up to 50 results per query via JS-level wait polling `.countPageMark`
4. **Detail pages** — fetches full abstracts by clicking "More" button on each paper detail page
5. **Year filter** — post-hoc `filter_by_year()`
6. **Embed** — `text-embedding-3-small` via LiteLLM API
7. **Rank** — `cosine_similarity` → select FINAL_TOP_N
8. **Export** — xlsx with 11 columns

## Expected Output

```
STEP 1: Translating queries to Chinese
  EN: steel decarbonization policy transition governance
  ZH: 钢铁 脱碳 政策 治理

STEP 2: Searching CNKI (Chinese queries)
Found N unique papers from CNKI

STEP 3: Embedding text and paper metadata
...
STEP 4: Ranking by cosine similarity
Ranked N candidates → selected top 10

XLSX written to: output/<stem>/CNKI_top50_select10/CNKI_top50_select10.xlsx
```

**Output path** (fixed naming): `output/<input_stem>/CNKI_top50_select10/CNKI_top50_select10.xlsx`

**XLSX columns**: rank, score, title, document_type, retrieval_query, authors, year, publication, source, url, abstract

## Starting Chrome (WSL2)

```powershell
# Run from Windows PowerShell (not WSL terminal)
powershell.exe -Command "Start-Process 'C:\Program Files\Google\Chrome\Application\chrome.exe' -ArgumentList '--remote-debugging-port=9222','--user-data-dir=C:\tmp\chrome-debug'"
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `chrome-devtools-mcp` connection refused | Chrome not running with debug port | Start Chrome (see above) |
| Captcha detected | CNKI anti-scraping triggered | Solve captcha in Chrome manually, retry |
| Results < 20 on queries | Niche topic with low CNKI coverage | Use broader 2-3 keyword queries |
| Translation error | LLM API failing | Check `OPENAI_API_KEY`; falls back to English |
| `npx: command not found` | Node.js missing | Install Node.js |

## English Queries

The script uses 5 English queries about steel decarbonization policy, green steel transition, hydrogen-based steelmaking, Australia-China value chain. Before running, confirm these match the TEXT topic. If TEXT has changed, propose new queries and their Chinese translations.

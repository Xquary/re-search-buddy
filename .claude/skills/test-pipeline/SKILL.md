---
name: test-pipeline
description: Run the full multi-source research finder pipeline via CLI. Use to test the end-to-end flow: keyword extraction → multi-source search → Zotero check → embedding → ranking → download → export.
argument-hint: "[find|search|config] <input_file>"
---

# Full Pipeline Test

Runs the complete `research_finder` CLI pipeline: LLM-based keyword extraction → multi-source search (arXiv, Scholar, Semantic Scholar, CNKI) → Zotero duplicate check → embedding → cosine ranking → download → export. Uses ``src/research_finder/cli.py`` and ``src/research_finder/pipeline.py``.

This is the **production entry point** — unlike the individual test scripts, it orchestrates all enabled backends in one run.

## Prerequisites

- All MCP servers accessible (arXiv, Scholar, CNKI — depends on `search.backends` config)
- Chrome running with `--remote-debugging-port=9222` if CNKI is enabled
- `.env` configured with `OPENAI_API_KEY` (for LLM extraction + embeddings)
- (Optional) `ZOTERO_API_KEY` + `ZOTERO_LIBRARY_ID` if Zotero integration enabled
- `config.yaml` tuned for desired backends and parameters

## Quick Run

```bash
# Full pipeline with an input file
PYTHONPATH=src .venv/bin/python -m research_finder.cli find input/raw/my_paper.md

# Search only (no ranking/download)
PYTHONPATH=src .venv/bin/python -m research_finder.cli search input/raw/my_paper.md

# Show current configuration
PYTHONPATH=src .venv/bin/python -m research_finder.cli config
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `find <input_file>` | Full pipeline: extract keywords → search → embed → rank → download → export |
| `search <input_file>` | Search only: extract keywords → search across backends (no ranking/download) |
| `config` | Print current configuration from `config.yaml` |

## CLI Flags

| Flag | Description |
|------|-------------|
| `--no-zotero` | Skip Zotero library check & export entirely |
| `--no-zotero-export` | Check Zotero library but skip exporting results |

## Pipeline Stages (in order)

1. **Keyword Extraction** — LLM extracts keywords + forms search queries from input text
2. **Multi-Source Search** — queries dispatched to all enabled backends in `search.backends`
3. **Deduplication** — duplicates removed by title across all sources
4. **Zotero Check** — papers already in user's Zotero library flagged (if enabled)
5. **Embedding** — input text + paper metadata embedded via configured embedder
6. **Ranking** — cosine similarity → select top-N papers
7. **Results Export** — JSON saved to output directory
8. **Download** — PDFs fetched (arXiv direct, Semantic Scholar open-access, Anna's Archive fallback)
9. **Zotero Export** — top papers pushed to Zotero (if enabled)

## Config Backends

Enabled via `config.yaml`:
```yaml
search:
  backends:
    - arxiv
    - scholar
    - semantic_scholar
    - cnki
```

Disable backends by removing them from the list.

## Expected Output

Output goes to `output/<input_stem>/` (configured via `output.dir`):
- JSON results files per backend
- Downloaded PDFs in `downloads/`
- Console progress with per-stage summaries

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| CLI not found | `PYTHONPATH` not set | Use `PYTHONPATH=src` prefix |
| One backend fails, pipeline stops | Backend not accessible | Remove failing backend from `search.backends` |
| LLM extraction fails | `OPENAI_API_KEY` missing or model not accessible | Check `.env` and `llm.model` in config |
| Zotero errors | Zotero not running or API key missing | Use `--no-zotero` to skip; check env vars |
| All backends return 0 results | Input text too niche | Broaden the input text topic |

## Verify with Individual Test Scripts

If the full pipeline fails, narrow down the issue with individual backend tests:
- `test-mcp` — MCP connectivity
- `test-arxiv` — arXiv only
- `test-scholar` — Scholar only
- `test-semantic-scholar` — Semantic Scholar only
- `test-cnki` — CNKI only

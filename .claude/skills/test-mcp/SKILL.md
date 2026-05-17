---
name: test-mcp
description: Test MCP server connectivity for arXiv, Google Scholar, and CNKI backends. Use when debugging MCP connection issues or verifying server health.
argument-hint: "[arxiv|scholar|cnki]"
---

# MCP Connectivity Smoke Test

Verifies that each MCP server backend starts, lists tools, and handles a test call. Runs ``test_mcp.py`` in the project root.

## Prerequisites

| Backend | Requirement |
|---------|-------------|
| arXiv | `uv` installed; `arxiv-mcp-server` available via `uv tool run` |
| Google Scholar | Project venv (`.venv/bin/python`); `mcp-server-google-scholar` in dependencies |
| CNKI | Node.js / `npx` available; Chrome running with `--remote-debugging-port=9222` |

Env vars (via `.env`): none required for basic connectivity (CNKI needs Chrome, not env vars).

## Quick Run

```bash
# Test all backends (arXiv, Scholar, CNKI sequentially)
PYTHONPATH=src .venv/bin/python test_mcp.py

# Test a single backend
PYTHONPATH=src .venv/bin/python test_mcp.py arxiv
PYTHONPATH=src .venv/bin/python test_mcp.py scholar
PYTHONPATH=src .venv/bin/python test_mcp.py cnki
```

## What It Tests

1. Starts the MCP server subprocess via stdio
2. Initializes a `ClientSession` with `mcp` SDK
3. Lists all available tools on the server
4. Calls one test tool:
   - **arXiv**: `search_papers(query="transformer attention mechanism", max_results=3)`
   - **Scholar**: `search_google_scholar_key_words(query="attention is all you need", num_results=3)`
   - **CNKI**: `navigate_page(url="https://kns.cnki.net/kns8s/search")`

## Expected Output

```
============================================================
Testing: arxiv
Command: uv tool run arxiv-mcp-server
============================================================
Available tools (N): [search_papers, download_paper, read_paper, ...]
Calling: search_papers(...)
Result (truncated): ...paper data...
✅ arxiv: SUCCESS
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `❌ arxiv: FAILED` | `arxiv-mcp-server` not installed | `uv tool install arxiv-mcp-server` |
| `❌ scholar: FAILED` | Venv not set up | `uv venv && uv pip install -e ".[dev]"` |
| `❌ cnki: FAILED` | Chrome not running in debug mode | Launch Chrome: see `CLAUDE.md` CNKI setup |
| `✅ scholar but empty results` | Google Scholar anti-scraping throttling | Normal; connectivity is passing |
| `npx: command not found` | Node.js missing | `brew install node` (macOS) or apt install (Linux) |

## Script Reference

File: `test_mcp.py` — 90 lines, uses `asyncio.run(main())`, no argparse flags.

---
name: setup
description: Interactive environment setup for research_finder — Python packages, API keys, MCP/CLI tools. Use when the user runs /setup, or when re-search-buddy first detects a missing prerequisite.
argument-hint: "[optional: specific key name, e.g. SCOPUS_API_KEY]"
---

# Setup — Environment, API Keys & Tools

Three-stage interactive setup. Each stage offers clickable options — install/configure what's needed, skip what isn't, and recall any stage later when needs change.

---

## Stage 1 — Python venv & packages

**Always run first.** Nothing else works without the Python environment.

```bash
# Check venv
test -x .venv/bin/python && echo "[ok] .venv/bin/python" || echo "[missing] venv — run: uv venv && uv sync"

# Check critical packages
.venv/bin/python -c "import dotenv; print('[ok] dotenv')" 2>/dev/null || echo "[missing] dotenv"
.venv/bin/python -c "import httpx; print('[ok] httpx')" 2>/dev/null || echo "[missing] httpx"
.venv/bin/python -c "import openpyxl; print('[ok] openpyxl')" 2>/dev/null || echo "[missing] openpyxl"
.venv/bin/python -c "import yaml; print('[ok] yaml')" 2>/dev/null || echo "[missing] yaml"

# Check optional packages (needed for SLR charts)
.venv/bin/python -c "import matplotlib; print('[ok] matplotlib')" 2>/dev/null || echo "[missing] matplotlib"
.venv/bin/python -c "import seaborn; print('[ok] seaborn')" 2>/dev/null || echo "[missing] seaborn"
.venv/bin/python -c "import sklearn; print('[ok] scikit-learn')" 2>/dev/null || echo "[missing] scikit-learn"
.venv/bin/python -c "import fitz; print('[ok] PyMuPDF')" 2>/dev/null || echo "[missing] PyMuPDF"
.venv/bin/python -c "import litellm; print('[ok] litellm')" 2>/dev/null || echo "[missing] litellm"
.venv/bin/python -c "import mcp; print('[ok] mcp')" 2>/dev/null || echo "[missing] mcp"
```

Report status and offer via `AskUserQuestion`:
- **Install all missing** — runs `uv sync` (or `uv pip install missing1 missing2 ...`)
- **Install only critical** — venv, dotenv, httpx, openpyxl, yaml, litellm, mcp, scikit-learn
- **Install all including optional** — adds matplotlib, seaborn, PyMuPDF
- **Skip** — environment is fine, or fix it manually later

If venv is missing entirely, `uv venv && uv sync` first.

---

## Stage 2 — API keys

Parse `.env` and report each key as **✅ set** / **❌ missing** (never print values):

| Key | Required? | What it unlocks | Where to get it |
|---|---|---|---|
| `OPENAI_API_KEY` | **Required** | All embeddings + LLM keyword extraction | https://platform.openai.com/api-keys |
| `SEMANTIC_SCHOLAR_API_KEY` | Optional (recommended) | Dedicated rate-limit pool on Semantic Scholar | https://www.semanticscholar.org/product/api#api-key |
| `SCOPUS_API_KEY` | Optional | Scopus searcher + Elsevier full-text downloads | https://dev.elsevier.com |
| `WILEY_TDM_TOKEN` | Optional | Wiley TDM full-text downloads | https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining |
| `ANNAS_SECRET_KEY` | Optional | Anna's Archive fallback downloads | Donate at https://annas-archive.gl/donate |
| `ZOTERO_API_KEY` + `ZOTERO_LIBRARY_ID` | Optional | Check / export to user's Zotero library | https://www.zotero.org/settings/keys |

Use `AskUserQuestion` (multiSelect) offering each **missing** key, plus:
- **Configure all missing** — walks through each, one at a time
- **Skip all** — remind later when a workflow needs them

If `OPENAI_API_KEY` is missing, it MUST be configured before proceeding — block exit otherwise.

**Collecting a key (one at a time):**
1. Explain what it unlocks and the URL to get it
2. User pastes value (written to `.env`, not echoed)
3. If line exists, replace value; otherwise append
4. Confirm saved without printing value

---

## Stage 3 — MCP servers & CLI tools

Check and offer to install:

| Tool | Needed for | Check |
|------|-----------|-------|
| `arxiv-mcp-server` | arXiv search | `which arxiv-mcp-server` or `uvx arxiv-mcp-server --help` |
| `google-scholar-mcp-server` | Google Scholar search | `.venv/bin/python -m google_scholar_server --help` (try/except) |
| `chrome-devtools-mcp` | CNKI search, browser downloads | `npx --version` (Node.js) + `curl -s http://127.0.0.1:9222/json/version` (Chrome debug) |
| `annas-mcp` | Anna's Archive PDF fallback | `which annas-mcp` or `ls .venv/bin/annas-mcp` |
| `zotero-mcp-server` | Zotero integration | `which zotero-mcp-server` |

**Install commands:**

| Tool | Install |
|------|---------|
| arxiv-mcp-server | `uv tool install arxiv-mcp-server` |
| google-scholar-mcp-server | already in project deps (`mcp-server-google-scholar`) |
| chrome-devtools-mcp + Chrome | Chrome: WSL2 → `powershell.exe -Command "Start-Process 'C:\Program Files\Google\Chrome\Application\chrome.exe' -ArgumentList '--remote-debugging-port=9222','--user-data-dir=C:\tmp\chrome-debug'"`; macOS: `/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug &`. Node.js: macOS `brew install node`; Linux `sudo apt install nodejs npm` |
| annas-mcp | Download binary from https://github.com/iosifache/annas-mcp/releases → place in `.venv/bin/` → `chmod +x .venv/bin/annas-mcp` |
| zotero-mcp-server | `uv tool install zotero-mcp-server` |

Use `AskUserQuestion` (multiSelect) listing each missing tool, plus:
- **Install all missing**
- **Skip all** — remind later when a workflow needs them

---

## Stage 4 — Verify

```bash
.venv/bin/python -c "import dotenv, os; dotenv.load_dotenv(); print('OPENAI_API_KEY:', 'set' if os.getenv('OPENAI_API_KEY') else 'MISSING')"
```

Report final status. If `OPENAI_API_KEY` is set, offer:
> Setup done. Want to run a task? Try `/re-search-buddy` to pick what to do.

---

## Style rules

- One key at a time. Never echo pasted values.
- Every prompt uses `AskUserQuestion` with clickable options.
- If the user is hesitant about pasting keys, suggest they edit `.env` manually.
- Setup can be re-run at any time to reconfigure specific items.
- **Each stage is independent:** run the check, print the results table, then present a selection where only actionable/missing items are selectable. Already-OK items are displayed in the table but must NOT appear as clickable options — only "Next → (next stage)" and "Configure <missing item>" options are offered. If nothing is missing, only the "Next →" option appears.

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

**CRITICAL — card-in-preview rule:** The "Configure X" picker MUST be a **single-select** `AskUserQuestion` where each option's `preview` field contains that item's full Config Card (purpose, URL, step-by-step, env line / install command). Single-select is required because `preview` only renders in single-select mode — multiSelect hides it. Each option's `description` stays one short line; the card goes in `preview`.

Flow:
- One question: "Which missing item do you want to configure first?"
- Options: one per ❌ item (each with `preview` = its Config Card) + a final "Skip — proceed to workflow" option.
- After the user picks one, configure it, re-run the stage check, then re-prompt with the remaining ❌ items until they choose Skip.

**Collecting a key (one at a time):**
1. Show the **Config Card** for that key (see below) — purpose, URL, step-by-step, env line — inline in chat BEFORE any AskUserQuestion.
2. Offer follow-up options via `AskUserQuestion`:
   - **Paste the key now** — user pastes value (written to `.env`, not echoed)
   - **Open the URL only** — user will configure later
   - **Skip**
3. If line exists in `.env`, replace value; otherwise append. Never echo the value back.
4. Confirm saved and re-run the Stage 2 check for that key.

---

### API Config Cards (canonical — show verbatim when user picks an API)

**Always render the card for the selected API before asking for the value.** Do not invent URLs or steps.

#### `OPENAI_API_KEY` — REQUIRED
- **Unlocks:** all embeddings + LLM keyword extraction. Nothing works without this.
- **Get it:** https://platform.openai.com/api-keys
- **Steps:**
  1. Log in (or create an account) at https://platform.openai.com
  2. Add a payment method under Billing (pay-as-you-go is fine)
  3. Go to API keys → **Create new secret key** → name it `re-search-buddy`
  4. Copy the `sk-...` value (shown only once)
- **`.env` line:** `OPENAI_API_KEY=sk-...`

#### `SEMANTIC_SCHOLAR_API_KEY` — optional (recommended)
- **Unlocks:** dedicated rate-limit pool on Semantic Scholar (avoids 429s on bulk SLR).
- **Get it:** https://www.semanticscholar.org/product/api#api-key-form
- **Steps:**
  1. Fill the request form (name, email, intended use — describe academic research)
  2. Wait 1–3 business days for the email with your key
- **`.env` line:** `SEMANTIC_SCHOLAR_API_KEY=<key>`

#### `SCOPUS_API_KEY` — optional
- **Unlocks:** Scopus searcher + Elsevier full-text downloads. Required for SLR via Scopus.
- **Get it:** https://dev.elsevier.com/apikey/manage
- **Steps:**
  1. Register / log in at https://dev.elsevier.com
  2. Accept the API Service Agreement
  3. **Create API Key** — set a label and the website URL of your institution
  4. **IMPORTANT:** Scopus only authorizes requests from your institution's IP range. Use the key on campus / via VPN.
- **`.env` line:** `SCOPUS_API_KEY=<key>`

#### `WILEY_TDM_TOKEN` — optional
- **Unlocks:** Wiley TDM full-text PDF downloads.
- **Get it:** https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining
- **Steps:**
  1. Your institution must have a Wiley subscription
  2. Email Wiley TDM (`tdm@wiley.com`) from your institutional address requesting a TDM client token
  3. Wait for the emailed token (usually a few days)
- **`.env` line:** `WILEY_TDM_TOKEN=<token>`

#### `SPRINGER_META_API_KEY` — optional
- **Unlocks:** Springer Nature metadata enrichment + open-access full text.
- **Get it:** https://dev.springernature.com/signup
- **Steps:**
  1. Sign up (free)
  2. Go to **Applications** → **Create application**
  3. Subscribe to the **Meta API** (free tier: 5000 calls/day)
  4. Copy the application's key
- **`.env` line:** `SPRINGER_META_API_KEY=<key>`

#### `ANNAS_SECRET_KEY` — optional
- **Unlocks:** Anna's Archive PDF fallback when no other source has the file.
- **Get it:** Donate at https://annas-archive.gl/donate (membership required for API)
- **Steps:**
  1. Make a donation at the donate page
  2. Log in to your account → **Account → API key** → copy the secret key
- **`.env` line:** `ANNAS_SECRET_KEY=<key>`

#### `ZOTERO_API_KEY` (+ `ZOTERO_LIBRARY_ID`) — optional
- **Unlocks:** dedup against your Zotero library + export results into a Zotero collection.
- **Get it:** https://www.zotero.org/settings/keys/new
- **Steps:**
  1. Log in at https://www.zotero.org
  2. Settings → **Feeds/API** → **Create new private key**
  3. Allow library access (read/write if you want export); name it `re-search-buddy`
  4. Copy the key
  5. Find your `ZOTERO_LIBRARY_ID`:
     - Personal library: https://www.zotero.org/settings/keys → "Your userID for use in API calls"
     - Group library: visit the group page, ID is in the URL
- **`.env` lines:**
  ```
  ZOTERO_API_KEY=<key>
  ZOTERO_LIBRARY_ID=<numeric id>
  ZOTERO_LIBRARY_TYPE=user   # or "group"
  ```

---

### MCP / CLI Tool Config Cards

When a Stage 3 tool is missing, show the matching card, then offer:
- **Auto-install for me** — you run the install command
- **Show command only** — user copy/pastes themselves
- **Skip**

#### `arxiv-mcp-server` (arXiv search)
- Install: `uv tool install arxiv-mcp-server`
- Verify: `which arxiv-mcp-server`

#### `google-scholar-mcp-server` (Google Scholar search)
- Already in project deps. If missing: `uv sync`
- Verify: `.venv/bin/python -c "import google_scholar_server"`

#### Chrome debug + Node.js (CNKI search)
- **Node.js:**
  - Linux/WSL: `sudo apt install -y nodejs npm`
  - macOS: `brew install node`
- **Launch Chrome with remote debugging** (needed every session):
  - WSL2: `powershell.exe -Command "Start-Process 'C:\Program Files\Google\Chrome\Application\chrome.exe' -ArgumentList '--remote-debugging-port=9222','--user-data-dir=C:\tmp\chrome-debug'"`
  - macOS: `/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug &`
  - Linux: `google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug &`
- Verify: `curl -s http://127.0.0.1:9222/json/version`

#### `annas-mcp` (Anna's Archive PDF fallback)
- Install: download binary from https://github.com/iosifache/annas-mcp/releases → place in `.venv/bin/annas-mcp` → `chmod +x .venv/bin/annas-mcp`
- Verify: `ls .venv/bin/annas-mcp`

#### `zotero-mcp-server` (Zotero MCP integration)
- Install: `uv tool install zotero-mcp-server`
- Verify: `which zotero-mcp-server`

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
- **MANDATORY missing-items gate before task selection:** After all check stages, if ANY item is ❌ (even optional), present a single-select `AskUserQuestion` with one option per missing item (full instruction card in `preview`) plus a "Skip / Done — proceed to task" option as the first/recommended choice. This MUST fire BEFORE the caller's task-selection prompt — never merge the two. Loop until the user picks "Skip / Done".

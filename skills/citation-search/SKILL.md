---
name: citation-search
description: Find literature to fill citation gaps in a user's writing. Use when the user provides a piece of text with placeholder citations (XX, XXX) and needs relevant papers.
argument-hint: "[optional: text or path]"
---

# Citation Gap Literature Search — Interactive SOP

This skill is a **conversational SOP**. You (Claude) walk a possibly non-technical user through a literature search end-to-end. Treat each step below as a checkpoint: do not skip, do not run anything that burns API credits before the user explicitly approves it.

The user works alongside you in Claude Code (desktop or CLI). Assume they may not know Python, paths, or env vars. Be friendly, brief, and explicit about what you are doing.

---

## Step 0 — Greeting & input mode

Greet the user in one line, then ask via `AskUserQuestion` how they want to provide the text:

- **Paste inline** — they will paste the passage in the next message.
- **File path** — they will give a path to a `.md` / `.txt` / `.docx` / `.pdf` already on disk.

If they pasted text inline in the initial invocation, skip the question.

---

## Step 1 — Ingest the text

**If pasted:**
1. Ask for a short stem name (kebab-case, e.g. `china-energy-gov`). If they don't care, derive one from the first salient noun phrase.
2. Write the passage to `input/raw/<stem>.md` using the Write tool. Create the dir with `mkdir -p input/raw` first.

**If file path:**
1. Verify the file exists. If it is not already under `input/raw/`, copy it there with a clean stem name.

Then run the input scan to extract markdown + cache an embedding:

```bash
PYTHONPATH=src .venv/bin/python skills/test-input-scan/scan_input.py
```

Confirm output shows `[new] embedding <stem>.md` (or `unchanged` if already cached). Record the `<stem>` — every later step uses it.

---

## Step 2 — Analyze gaps & gather search parameters

Read the saved text. Identify each distinct citation placeholder (`XX`, `XXX`, `[?]`, etc.) and the scholarly strand it represents. In your reply, briefly list each gap with one-line intent (e.g. "XX → structure: institutional landscape, central-local relations").

Then ask the user **four parameter questions** before drafting queries. Use `AskUserQuestion` (one call, multiple questions). For each, propose a default based on the text and the number of gaps you identified — do not ask cold.

| # | Question | Header | Default to suggest | Why it matters |
|---|---|---|---|---|
| 1 | How many queries to run? | `Query count` | `2 × number of gaps`, capped at 5 | More queries = better coverage but more API spend; Scholar throttles hard above ~6. |
| 2 | What field / discipline should results come from? | `Field` | Inferred from text (e.g. "political science / China studies", "ML / NLP", "environmental economics") | Used to bias query wording and to pick sources (arXiv only for STEM, CNKI for China topics). Also lets you filter out off-topic hits in Step 6. |
| 3 | How many candidates per query (first-pass)? | `Per-query N` | `10` for Scholar / arXiv / Semantic Scholar, `20` for Scopus, `50` for CNKI | Raises recall ceiling but multiplies embedding cost. Hard caps: Scholar ~20 (anti-scraping), CNKI 50, Scopus 25 per page. |
| 4 | How to select final papers? | `Selection` | `Top 10 by score, with similarity ≥ 0.35 cutoff` | Offer three modes: **fixed top-N** (e.g. 10), **threshold-only** (keep all ≥ X), or **both** (top-N AND ≥ threshold). Typical thresholds: 0.30 loose, 0.40 strict, 0.50 very strict. |

Show the chosen values back in one line, e.g.:
> Plan: 5 queries · field = "China energy governance" · per-query = 10 · select top 10 with score ≥ 0.35.

**Then** draft the queries — exactly the count chosen in Q1, biased toward the chosen field, each tagged with the gap it serves. **Per-source query syntax matters:**

- **Scholar / arXiv / CNKI** — keyword-rich English phrases (loose matching). 6–10 keywords work well.
- **Semantic Scholar** — the `/paper/search/bulk` endpoint AND's every token across title/abstract/keywords. Long Scholar-style strings return 0 hits. Keep queries **short (3–5 keywords), no boolean operators, all terms must plausibly co-occur in a title or abstract.** Example: `China cadre promotion tournament local government` (works) vs `China local cadre promotion tournament GDP performance evaluation industrial policy` (0 hits).
- **Scopus** — strict boolean `TITLE-ABS-KEY(...)` matching where bare keywords are AND'd. A long keyword string returns 0 hits. Use **quoted phrases + OR groups + explicit AND**, e.g. `("cadre evaluation" OR "promotion tournament") AND "local government" AND china`. Field codes (`TITLE(...)`, `ABS(...)`, `SUBJAREA(...)`, `PUBYEAR > 2015`, etc.) pass through untouched.
- If the user selected **multiple sources with different syntaxes**, draft **separate query sets** — loose (Scholar/arXiv/CNKI), short-AND (Semantic Scholar), boolean (Scopus) — and show each set for approval. Store as `QUERIES_BY_SOURCE` in the runner script. Present them via a second `AskUserQuestion`:

- **Approve** — proceed.
- **Edit queries** — user types corrections; regenerate and re-ask.
- **Change parameters** — go back to the parameter questions.
- **Cancel** — abort.

**Never run a search before this approval.** Queries burn API credits.

Store the chosen `per_query`, `top_n`, and `threshold` — pass them to every runner invocation in Step 5 (`--max-per-query`, `--top-n`, and apply the threshold filter on `p.score` before writing the xlsx).

---

## Step 3 — Pick sources (ask once)

Ask via `AskUserQuestion` (multiSelect) which databases to search. Default-recommend Scholar.

| Source | When to recommend | Requires |
|---|---|---|
| Google Scholar | Always — best general coverage | nothing extra |
| Semantic Scholar | Better recall, OA PDFs, citation counts | `SEMANTIC_SCHOLAR_API_KEY` (optional, recommended) |
| arXiv | Topic is physics / CS / ML / quant econ | nothing extra |
| Scopus | User has Elsevier institutional access; needs DOI + journal metadata | `SCOPUS_API_KEY` + institutional IP |
| CNKI | Topic concerns China / Chinese-language sources | Chrome running on `--remote-debugging-port=9222` |

Run each selected source **sequentially** (not in parallel — they share rate-limit budgets and Chrome).

---

## Step 4 — Preflight check (gated by source choice)

Before running any source, verify its prerequisites. Use Bash and the table below. If anything is missing, **stop and walk the user through fixing it** — do not silently skip.

| Source | Check | Fix if missing |
|---|---|---|
| All | `.env` exists with `OPENAI_API_KEY` | Tell user to copy `.env.example` → `.env` and fill in their key. |
| Semantic Scholar | `SEMANTIC_SCHOLAR_API_KEY` env var | Optional; warn that without it requests share a public rate-limit pool. |
| Scopus | `SCOPUS_API_KEY` env var | Direct user to register at https://dev.elsevier.com/ — cannot proceed without. |
| CNKI | `curl -s http://127.0.0.1:9222/json/version` returns JSON | Instruct user to launch Chrome with remote debugging. WSL2: `powershell.exe -Command "Start-Process 'C:\Program Files\Google\Chrome\Application\chrome.exe' -ArgumentList '--remote-debugging-port=9222','--user-data-dir=C:\tmp\chrome-debug'"`. macOS/Linux: see CLAUDE.md. |
| CNKI | `npx --version` available | `brew install node` (macOS) or `sudo apt install nodejs npm` (Linux). |

State each check result in one line (e.g. `[ok] OPENAI_API_KEY set`, `[missing] SCOPUS_API_KEY`).

---

## Step 5 — Run each source

For each source in turn, invoke the existing pipeline with the cached input embedding. **Always pass `--input <stem>`** so it reuses the embedding from Step 1.

```bash
# Scholar
PYTHONPATH=src .venv/bin/python skills/test-scholar/test_pipeline.py --input <stem>

# Semantic Scholar
PYTHONPATH=src .venv/bin/python skills/test-semantic-scholar/test_semantic_scholar_pipeline.py --input <stem>

# arXiv
PYTHONPATH=src .venv/bin/python skills/test-arxiv/test_arxiv_pipeline.py --input <stem>

# Scopus (SLR pipeline; runs query-by-query)
PYTHONPATH=src .venv/bin/python skills/slr/slr_scopus.py --input <stem> --no-download

# CNKI
PYTHONPATH=src .venv/bin/python skills/test-cnki/test_cnki_pipeline.py --input <stem>
```

**Important:** the upstream `test_*_pipeline.py` scripts use hardcoded `QUERIES` lists. Before running, you must inject the user-approved queries. Two options:

1. **Preferred** — write a temporary citation-search runner at `skills/citation-search/run_<stem>.py` that imports the relevant searcher class (`ScholarSearcher`, `SemanticScholarSearcher`, `ArxivSearcher`, `ScopusSearcher`, `CnkiSearcher`), takes a `--source` flag, and uses the approved `QUERIES` constant. Use the template at the bottom of this file. This avoids editing shared test scripts.
2. **Fallback** — only if (1) is too heavy, edit the `QUERIES` list inside the relevant `test_*_pipeline.py`, run it, then revert the edit. Note the project rule: scripts live in their skill subdir, so prefer (1).

After each source completes, print the xlsx path and the top-3 titles+scores so the user can sanity-check.

---

## Step 6 — Report results

After all selected sources have run, present results in markdown mapped back to the citation gaps:

```markdown
## Top results mapped to citation gaps

### XX (<gap intent>)
| # | Source | Score | Paper | Why it fits |
|---|--------|-------|-------|-------------|
| 1 | Scholar | 0.612 | Author (Year) — "Title", *Journal* | one-line justification |

### XXX (<gap intent>)
| # | Source | Score | Paper | Why it fits |
|---|--------|-------|-------|-------------|
...
```

End with a short recommendation: which specific papers to cite for each gap, and any classics that recurred across sources.

---

## Step 7 — Downloads (no, unless asked)

Do **not** auto-download. After reporting, ask via `AskUserQuestion` whether to download PDFs. If yes, run the downloader phase on the merged result xlsx (Direct → Elsevier → Wiley → Anna's). If no, exit cleanly.

---

## Output layout

```
output/<stem>/
├── Scholar_top<M>_select<N>/Scholar_top<M>_select<N>.xlsx
├── SemanticScholar_top<M>_select<N>/...
├── arXiv_top<M>_select<N>/...
├── Scopus_top<M>_select<N>/...
└── CNKI_top<M>_select<N>/...
```

---

## Runner template (preferred over editing test scripts)

Save at `skills/citation-search/run_<stem>.py`. Reuses the cached input embedding and the user-approved queries; dispatches to any searcher.

**Critical API facts — do not get these wrong:**
- `rank_papers(text_emb, paper_embs, papers, top_n=N, threshold=0.0)` — `paper_embs` comes **before** `papers`.
- `rank_papers` returns `list[Paper]`, score is on `p.score` (no tuple unpacking).
- Call `dotenv.load_dotenv()` at module top level inside a script file; not inside `python -c "..."`.

```python
"""Citation-search runner for <stem>. Dispatches to a chosen searcher."""
import argparse, yaml
from pathlib import Path
import dotenv; dotenv.load_dotenv()
from openpyxl import Workbook
from research_finder.embedder import get_embedder
from research_finder.ranker import rank_papers
from research_finder.input_store import InputStore

INPUT_NAME = "<stem>"
QUERIES = [
    # approved queries, e.g. "China energy governance institutional landscape ...",
]

SEARCHERS = {
    "scholar":  ("research_finder.searcher.scholar_searcher", "ScholarSearcher", "Scholar"),
    "semantic": ("research_finder.searcher.semantic_scholar_searcher", "SemanticScholarSearcher", "SemanticScholar"),
    "arxiv":    ("research_finder.searcher.arxiv_searcher", "ArxivSearcher", "arXiv"),
    "scopus":   ("research_finder.searcher.scopus_searcher", "ScopusSearcher", "Scopus"),
    "cnki":     ("research_finder.searcher.cnki_searcher", "CnkiSearcher", "CNKI"),
}

ap = argparse.ArgumentParser()
ap.add_argument("--source", required=True, choices=list(SEARCHERS))
ap.add_argument("--max-per-query", type=int, default=10)
ap.add_argument("--top-n", type=int, default=10)
ap.add_argument("--threshold", type=float, default=0.0, help="drop papers with score < threshold")
args = ap.parse_args()

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

mod_path, cls_name, label = SEARCHERS[args.source]
import importlib
Searcher = getattr(importlib.import_module(mod_path), cls_name)

store = InputStore(cfg)
text_emb, text = store.load(INPUT_NAME)
print(f"[input] {INPUT_NAME}: {len(text)} chars, dim={text_emb.shape}")

papers = Searcher(cfg).search(QUERIES)
print(f"[{label}] {len(papers)} unique papers")

embedder = get_embedder(cfg)
embs = embedder.embed_batch([f"{p.title}. {p.abstract or ''}" for p in papers])
ranked = rank_papers(text_emb, embs, papers, top_n=args.top_n, threshold=args.threshold)

out_dir = Path("output") / INPUT_NAME / f"{label}_top{args.max_per_query}_select{args.top_n}"
out_dir.mkdir(parents=True, exist_ok=True)
xlsx = out_dir / f"{label}_top{args.max_per_query}_select{args.top_n}.xlsx"
wb = Workbook(); ws = wb.active; ws.title = "Results"
ws.append(["rank","score","title","authors","year","publication","publisher",
           "document_type","abstract","url","doi","pdf_url","retrieval_query"])
for i, p in enumerate(ranked, 1):
    ws.append([i, round(p.score,4), p.title, ", ".join(p.authors or []), p.year,
               getattr(p,"publication",""), getattr(p,"publisher",""),
               getattr(p,"document_type",""), p.abstract or "", p.url or "",
               getattr(p,"doi","") or "", p.pdf_url or "",
               getattr(p,"retrieval_query","") or ""])
wb.save(xlsx)
print(f"[xlsx] {xlsx}")
for i, p in enumerate(ranked[:3], 1):
    print(f"  #{i} [{p.score:.3f}] {p.title[:80]}")
```

Invoke once per selected source:

```bash
PYTHONPATH=src .venv/bin/python skills/citation-search/run_<stem>.py --source scholar
PYTHONPATH=src .venv/bin/python skills/citation-search/run_<stem>.py --source semantic
# ...etc
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `TypeError: float() argument must be a string or a real number, not 'Paper'` | Wrong `rank_papers` arg order | `rank_papers(text_emb, paper_embs, papers, ...)` |
| `TypeError: cannot unpack non-iterable Paper object` | Treating result as `(score, paper)` | Use `p.score` |
| Scholar returns 0 papers | Google Scholar throttle | Raise `search.scholar.query_delay` in `config.yaml`; wait 10 min |
| eHTML downloads instead of PDFs | Anna's Archive fast-download broken | Known issue; eHTML is readable |
| CNKI: navigate fails | Chrome not on port 9222 | Re-launch Chrome with `--remote-debugging-port=9222` |
| Scopus: 401 | Missing/invalid `SCOPUS_API_KEY` | Set env var; some endpoints need institutional IP |
| Embedding fails | `OPENAI_API_KEY` missing | Fill `.env` |

## Reference implementations
- `skills/citation-search/test_principal_multiplicity.py` — earlier working single-source example
- `skills/test-scholar/test_pipeline.py` — base Scholar template
- `skills/slr/slr_scopus.py` — Scopus SLR pipeline
- `skills/slr/slr_semantic_scholar.py` — Semantic Scholar SLR pipeline

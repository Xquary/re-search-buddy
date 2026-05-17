---
name: citation-search
description: Find literature to fill citation gaps in a user's writing. Use when the user provides a piece of text with placeholder citations (XX, XXX) and needs relevant papers.
argument-hint: "[text with citation gaps]"
---

# Citation Gap Literature Search

When a user provides a piece of writing with placeholder citation markers (e.g. `XX`, `XXX`), find academically relevant papers to fill those gaps using the research_finder pipeline (Scholar first, optionally extend to arXiv/Semantic Scholar/CNKI).

## Workflow

### 1. Analyze the text

Identify the distinct scholarly strands or claims marked by gaps. Extract key concepts, frameworks, and relationships. Map each gap to its intellectual domain.

Example from the green energy governance case:
- `XX` → structure-focused strand: institutional landscape, policy design, central-local relations
- `XXX` → agency-focused strand: fragmented authoritarianism, subnational actors, implementation

### 2. Draft queries (5 queries, get approval first)

Craft 5 Google Scholar queries that cover each strand and their intersections. Use keyword-rich English phrases (Scholar works best with specific multi-word queries, not natural language questions).

**CRITICAL**: Show the exact 5 queries to the user and ask for approval before running. Queries burn API credits and determine the entire downstream ranking.

Example:
```
1. China energy governance institutional landscape policy design regulatory framework central-local relations  [→ XX]
2. fragmented authoritarianism China energy policy implementation subnational  [→ XXX]
3. China central local relations policy implementation energy sector bureaucracy  [→ bridging]
4. subnational actors firms implementation space China environmental energy governance  [→ XXX]
5. China energy transition institutional constraints political economy  [→ broader framing]
```

### 3. Save input text

Write the user's text to `input/raw/<stem>.md`. Use a short, descriptive stem (e.g. `china_energy_governance`).

```bash
mkdir -p input/raw
# Write the text to input/raw/<stem>.md
```

### 4. Scan and embed

```bash
PYTHONPATH=src .venv/bin/python skills/test-input-scan/scan_input.py
```

Expected output:
```
  [new] extracted <stem>.md → <stem>.md (N chars)
  [new] embedding <stem>.md (N chars)
  added: 1 ['<stem>.md']
```

### 5. Create pipeline script

Place the script at `skills/citation-search/test_<stem>.py`. Use the verified template below
(see also `skills/citation-search/test_principal_multiplicity.py` as a working reference).

**Critical API facts — do not get these wrong:**
- `rank_papers(text_emb, paper_embs, papers, top_n=N, threshold=0.0)` — `paper_embs` comes **before** `papers`
- `rank_papers` returns `list[Paper]`, **not** a list of `(score, paper)` tuples
- The similarity score is on `paper.score` — access it as `p.score`, not by unpacking
- `dotenv.load_dotenv()` must **not** be called with `()` at module level in a heredoc/`-c` context — call it inside a `if __name__ == "__main__"` guard or just run the file directly

```python
"""Literature search: <topic>."""
import argparse
from pathlib import Path
import dotenv
dotenv.load_dotenv()
from openpyxl import Workbook
from research_finder.searcher.scholar_searcher import ScholarSearcher
from research_finder.embedder import get_embedder
from research_finder.ranker import rank_papers
from research_finder.input_store import InputStore
import yaml

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--year-from", dest="year_from", type=int, default=None)
parser.add_argument("--year-to", dest="year_to", type=int, default=None)
parser.add_argument("--max-per-query", dest="max_per_query", type=int, default=10)
parser.add_argument("--top-n", dest="top_n", type=int, default=10)
_args, _ = parser.parse_known_args()

INPUT_NAME = "<stem>"

QUERIES = [
    # approved queries go here
]

SOURCE_NAME = "Scholar"
per_query = _args.max_per_query
top_n = _args.top_n

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)
cfg.setdefault("search", {}).setdefault("scholar", {})["max_results"] = per_query
cfg.setdefault("embedding", {})["provider"] = "api"

store = InputStore(cfg)
cached_text_emb, TEXT = store.load(INPUT_NAME)
print(f"[input_store] loaded '{INPUT_NAME}': {len(TEXT)} chars, embedding shape={cached_text_emb.shape}\n")

print("STEP 1: Searching Google Scholar")
searcher = ScholarSearcher(cfg)
papers = searcher.search(QUERIES)
print(f"Found {len(papers)} unique papers from Scholar\n")

if _args.year_from or _args.year_to:
    before = len(papers)
    papers = [p for p in papers if p.year and
              (_args.year_from is None or p.year >= _args.year_from) and
              (_args.year_to is None or p.year <= _args.year_to)]
    print(f"Year filter: {before} -> {len(papers)} papers\n")

print("STEP 2: Embedding paper metadata")
embedder = get_embedder(cfg)
paper_texts = [f"{p.title}. {p.abstract or ''}" for p in papers]
paper_embs = embedder.embed_batch(paper_texts)

print("STEP 3: Ranking by cosine similarity")
# NOTE: argument order is (text_emb, paper_embs, papers) — paper_embs before papers
# rank_papers returns list[Paper]; score is on p.score, NOT a (score, paper) tuple
ranked = rank_papers(cached_text_emb, paper_embs, papers, top_n=top_n, threshold=0.0)
print(f"\nTop {len(ranked)} papers:")
for i, p in enumerate(ranked, 1):
    print(f"  #{i:2d}  [score: {p.score:.4f}]  {p.title[:80]}")

out_label = f"{SOURCE_NAME}_top{per_query}_select{top_n}"
out_dir = Path("output") / INPUT_NAME / out_label
out_dir.mkdir(parents=True, exist_ok=True)
xlsx_path = out_dir / f"{out_label}.xlsx"

wb = Workbook()
ws = wb.active
ws.title = "Results"
headers = ["rank", "score", "title", "authors", "year", "publication",
           "publisher", "document_type", "abstract", "url", "doi",
           "pdf_url", "retrieval_query", "metadata_line"]
ws.append(headers)
for i, p in enumerate(ranked, 1):
    ws.append([
        i, round(p.score, 4), p.title,
        ", ".join(p.authors) if p.authors else "",
        p.year, getattr(p, "publication", ""),
        getattr(p, "publisher", ""),
        getattr(p, "document_type", ""),
        p.abstract or "", p.url or "",
        getattr(p, "doi", "") or "",
        p.pdf_url or "",
        getattr(p, "retrieval_query", "") or "",
        getattr(p, "metadata_line", "") or "",
    ])
wb.save(xlsx_path)
print(f"\nXLSX written to: {xlsx_path}")
print("Done.")
```

**Key differences from `skills/test-scholar/test_pipeline.py`:**
- Uses `InputStore.load()` to pull cached text + embedding (no hardcoded TEXT, no `--input` flag)
- `INPUT_NAME` set to the stem
- `QUERIES` are the approved ones
- No download step by default (user will ask if needed)

### 6. Run the pipeline

```bash
PYTHONPATH=src .venv/bin/python test_<stem>.py
```

Expected output:
```
[input_store] loaded '<stem>': N chars, embedding shape=(1536,)
STEP 1: Searching Google Scholar
Found N unique papers from Scholar
STEP 2: Embedding text and paper metadata
STEP 3: Ranking by cosine similarity
Top 10 papers (threshold=0.0):
  #1  [score: 0.xxxx]  Paper Title...
...
XLSX written to: output/<stem>/Scholar_top10_select10/Scholar_top10_select10.xlsx
STEP 4: Downloading PDFs
```

### 7. Report results

Present a table mapping the top-N papers to the original citation gaps. For each paper, include:
- Score (cosine similarity)
- Author(s), year, title
- Why it fits that specific gap
- Journal name

Format:
```markdown
## Top 10 Results Mapped to Citation Gaps

### XX (structure strand)
| # | Score | Paper | Why it fits |
|---|-------|-------|-------------|
| N | 0.xxx | Author (Year) — "Title" | Reason... |

### XXX (agency strand)
| # | Score | Paper | Why it fits |
|---|-------|-------|-------------|
| N | 0.xxx | Author (Year) — "Title" | Reason... |

### Bridging both
| # | Score | Paper | Why it fits |
|---|-------|-------|-------------|
| N | 0.xxx | Author (Year) — "Title" | Reason... |
```

End with a recommendation: which specific papers to cite for each gap, plus any foundational/classic texts that appeared.

## Output Files

```
output/<stem>/Scholar_top<M>_select<N>/
├── Scholar_top<M>_select<N>.xlsx    # Full ranked metadata
└── downloads/                        # PDFs (eHTML from Anna's Archive fallback)
```

## Extending to Other Sources

After Scholar results, optionally extend:

```bash
# Semantic Scholar (LLM-generated queries, better recall)
PYTHONPATH=src .venv/bin/python skills/test-semantic-scholar/test_semantic_scholar_pipeline.py --input <stem>

# arXiv (same queries, physics/CS-heavy corpus)
PYTHONPATH=src .venv/bin/python skills/test-arxiv/test_arxiv_pipeline.py --input <stem>

# CNKI (Chinese queries; requires Chrome + remote debugging)
PYTHONPATH=src .venv/bin/python skills/test-cnki/test_cnki_pipeline.py --input <stem>
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `TypeError: float() argument must be a string or a real number, not 'Paper'` | Wrong `rank_papers` arg order | Put `paper_embs` **before** `papers`: `rank_papers(text_emb, paper_embs, papers, ...)` |
| `TypeError: cannot unpack non-iterable Paper object` | Treating `rank_papers` result as `(score, paper)` tuples | It returns `list[Paper]`; use `p.score` not unpacking |
| `AssertionError` in dotenv | Running `dotenv.load_dotenv()` inside `-c` one-liner | Run as a script file, not `python -c "..."` |
| "No papers found" | Google Scholar throttled | Increase `query_delay` in config.yaml (default 3.0s) |
| pdf_url is always None for Scholar | Scholar doesn't provide PDF links | Expected; download step is optional |
| eHTML downloads instead of PDFs | Anna's Archive fast download broken | Known issue; eHTML is readable, or use DOI to access directly |
| Embedding fails | `OPENAI_API_KEY` missing | Check `.env` |

## Verified script pattern

Reference: `skills/citation-search/test_principal_multiplicity.py` — confirmed working example. See also `skills/test-scholar/test_pipeline.py` for the base template.

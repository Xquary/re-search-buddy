"""End-to-end test: CNKI search → embed → rank → output top 10.

Translates queries to Chinese before searching CNKI.

Optional: pass ``--input <name>`` to load a pre-computed input embedding from
``input/embeddings/`` instead of re-embedding the hardcoded ``TEXT`` below.
Run ``scan_input.py`` first to populate the store.
"""
import argparse
from pathlib import Path

import dotenv
dotenv.load_dotenv()
from openpyxl import Workbook

from research_finder.searcher.cnki_searcher import CnkiSearcher, PAPERS_PER_QUERY
from research_finder.embedder import get_embedder
from research_finder.ranker import rank_papers
from research_finder.models import Paper
from research_finder.input_store import InputStore
from research_finder.filters import filter_by_year
import litellm
import yaml

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--input", dest="input_name", default=None)
parser.add_argument("--year-from", dest="year_from", type=int, default=None)
parser.add_argument("--year-to", dest="year_to", type=int, default=None)
_args, _ = parser.parse_known_args()

# ── Selection constants ────────────────────────────────────────────────────────
# PAPERS_PER_QUERY = 50   (imported from cnki_searcher — metadata collected per query)
FINAL_TOP_N = 10           # papers selected after embedding + cosine ranking
# ──────────────────────────────────────────────────────────────────────────────

# ── 1. Input text ──────────────────────────────────────────────────────────
TEXT = (
    "Recent study argues that steel decarbonization should be understood as a broader "
    "industrial transformation rather than a narrow emissions problem, with the role of "
    "the state, policy design, and political contestation over risk and reward distribution "
    "identified as critical yet underexplored frontiers (Algers et al., 2025). However, while "
    "the literature increasingly call for the policy scope extension beyond innovation support "
    "to encompass system-wide transition governance (Nykvist et al., 2025), it offers limited "
    "insight into the actual mechanisms through which policy is formulated, how it triggers "
    "and accelerates technological deployment, and crucially, how it interacts with "
    "market-driven forces of demand pull and supply push in shaping green steel transition "
    "trajectories. Especially pronounced in cross-border settings such as the Australia–China "
    "green steel relationship, where two economies embedded in the same value chain operate "
    "under fundamentally different policy rationales, raising unresolved questions about "
    "whether policy or market dynamics play the more determinant role, and how their interplay "
    "conditions the pace and direction of the future green steel transition."
)

# ── 2. English queries ─────────────────────────────────────────────────────
ENGLISH_QUERIES = [
    "steel decarbonization policy transition governance",
    "green steel industrial transformation demand pull supply push",
    "hydrogen-based steelmaking policy mechanisms deployment",
    "Australia China green steel value chain cross-border",
    "policy market dynamics green steel transition pathways",
]


# ── 3. Translate queries to Chinese ───────────────────────────────────────
def translate_to_chinese(queries: list[str]) -> list[tuple[str, str]]:
    """Translate English queries to Chinese, return list of (en, zh) tuples."""
    translated = []
    for q in queries:
        try:
            response = litellm.completion(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional academic translator. Translate the following English research query into short Chinese KEYWORDS separated by spaces (e.g. '钢铁 脱碳 政策'). CNKI works best with 2-4 short keywords, not long phrases. Return ONLY the space-separated Chinese keywords, no explanations or quotes.",
                    },
                    {"role": "user", "content": q},
                ],
                max_tokens=100,
            )
            zh = response.choices[0].message.content.strip()
            translated.append((q, zh))
            print(f"  EN: {q}")
            print(f"  ZH: {zh}\n")
        except Exception as e:
            print(f"  Translation failed for '{q}': {e}")
            translated.append((q, q))  # fallback to English
    return translated


# ── 4. Search ──────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 1: Translating queries to Chinese")
print("=" * 80)
translations = translate_to_chinese(ENGLISH_QUERIES)

print("=" * 80)
print("STEP 2: Searching CNKI (Chinese queries)")
print("=" * 80)

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

cfg.setdefault("search", {}).setdefault("cnki", {})["max_results"] = PAPERS_PER_QUERY * len(ENGLISH_QUERIES)
cfg.setdefault("embedding", {})["provider"] = "api"

# ── Optional: load input text + embedding from the input_store cache ──────
cached_text_emb = None
if _args.input_name:
    store = InputStore(cfg)
    cached_text_emb, TEXT = store.load(_args.input_name)
    print(f"[input_store] loaded '{_args.input_name}': {len(TEXT)} chars, "
          f"embedding shape={cached_text_emb.shape}\n")

searcher = CnkiSearcher(cfg)
cnki_queries = [zh for _, zh in translations]
papers = searcher.search(cnki_queries)
print(f"Found {len(papers)} unique papers from CNKI")
if _args.year_from is not None or _args.year_to is not None:
    print(f"Year filter: [{_args.year_from or '-'}, {_args.year_to or '-'}]")
    before = len(papers)
    papers = filter_by_year(papers, _args.year_from, _args.year_to)
    print(f"  year filter kept {len(papers)} / {before}")
print()

if not papers:
    print("No papers found. Exiting.")
    raise SystemExit(0)

for i, p in enumerate(papers[:5], 1):
    print(f"  {i}. {p.title}")
    if p.abstract:
        print(f"     {p.abstract[:120]}...")
print(f"  ... and {len(papers) - 5} more\n" if len(papers) > 5 else "\n")

# ── 5. Embed ───────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 3: Embedding text and paper metadata")
print("=" * 80)

embedder = get_embedder(cfg)
if cached_text_emb is not None:
    text_emb = cached_text_emb
    print(f"Text embedding: shape={text_emb.shape} (from input_store cache)")
else:
    text_emb = embedder.embed_single(TEXT)
    print(f"Text embedding: shape={text_emb.shape}")

paper_texts = [f"{p.title} {p.abstract or ''}" for p in papers]
paper_embs = embedder.embed_batch(paper_texts)
print(f"Paper embeddings: shape={paper_embs.shape}\n")

# ── 6. Rank ────────────────────────────────────────────────────────────────
print("=" * 80)
print("STEP 4: Ranking by cosine similarity")
print("=" * 80)

ranked = rank_papers(text_emb, paper_embs, papers, top_n=FINAL_TOP_N, threshold=0.0)
print(f"Ranked {len(papers)} candidates → selected top {FINAL_TOP_N} (threshold=0.0):\n")

for i, p in enumerate(ranked, 1):
    print(f"{'─' * 78}")
    print(f"  #{i}  [score: {p.score:.4f}]  {p.title}")
    if p.authors:
        print(f"  Authors: {', '.join(p.authors[:5])}")
    if p.year:
        print(f"  Year: {p.year}")
    if p.url:
        print(f"  URL: {p.url}")
    if p.abstract:
        abstract_preview = p.abstract[:300] + ("..." if len(p.abstract) > 300 else "")
        print(f"  Abstract: {abstract_preview}")
    print()

# ── 7. Export ──────────────────────────────────────────────────────────────
SOURCE_NAME = "CNKI"
per_query = PAPERS_PER_QUERY
top_n = FINAL_TOP_N

if _args.input_name:
    input_stem = Path(_args.input_name).stem
    base_dir = Path("output") / input_stem
else:
    base_dir = Path("output") / "default"

search_dir_name = f"{SOURCE_NAME}_top{per_query}_select{top_n}"
search_dir = base_dir / search_dir_name
search_dir.mkdir(parents=True, exist_ok=True)

xlsx_path = search_dir / f"{search_dir_name}.xlsx"

wb = Workbook()
ws = wb.active
ws.title = "Top10"
headers = [
    "rank",
    "score",
    "title",
    "document_type",
    "retrieval_query",
    "authors",
    "year",
    "publication",
    "source",
    "url",
    "abstract",
]
ws.append(headers)
for i, paper in enumerate(ranked, 1):
    ws.append(
        [
            i,
            round(paper.score, 6),
            paper.title,
            paper.document_type or "",
            paper.retrieval_query or "",
            "; ".join(paper.authors),
            paper.year or "",
            paper.publication or "",
            paper.source,
            paper.url or "",
            paper.abstract or "",
        ]
    )
wb.save(xlsx_path)

print("=" * 80)
print(f"XLSX written to: {xlsx_path}")
print("Done.")

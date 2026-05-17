---
name: test-slr-analysis
description: SLR data profiling and advanced analysis. Takes the SLR output xlsx and produces data profiling stats, content analysis, and advanced visualisation charts across keyword-matched and non-matched paper sets. Use after SLR search + local keyword verification.
argument-hint: "[--input-path <xlsx>]"
---

# SLR Data Analysis — Profiling, Content, Advanced Charts

## Citation-vs-relevance highlights rule

The 1.2d scatter plot (score vs. citations) MUST highlight **top-N most cited ∪ top-M most relevant** papers (default N=M=15), labeled with Author (Year) via `adjustText`. Non-highlighted points are drawn small/translucent in the background; highlighted points are large with black edge.

Always offer N and M via `AskUserQuestion` before running (recommended default: 15+15). The driver passes them via `--top-cited` and `--top-relevant` to `analysis_citations.py`.

Also write a helper sheet to the xlsx (`<short>_highlighted`, e.g. `kw_clean_highlighted`) containing the union list with a `selected_reason` column ("high cited" / "high relevant" / "high cited, high relevant"). Disable with `--no-write-highlight-sheet`.

## Workflow rule

The post-SLR analysis pipeline has **3 mandatory stages**, in order. Do not skip stages.

**1. Keyword-verification pre-pass** — `enrich_keyword_clean.py`
   - Define keyword buckets per topic (one bucket per query label).
   - Confirm buckets with the user via `AskUserQuestion`.
   - Adds two sheets to the xlsx:
     - `keyword_verified_clean` — papers where title/abstract/keywords match ≥1 bucket; gains a `keyword_hit` column.
     - `missing_topic_only_clean` — papers retrieved but matching no bucket (likely tangential hits).
   - `python enrich_keyword_clean.py --xlsx <path> --buckets-yaml <path>`

**2. Journal-exclusion filter** — offer multi-select to drop noisy journals (see "Journal filter rule" below).

**3. Run all 10 analyses on both sheets** — `run_all_analyses.py`
   - Driver iterates `keyword_verified_clean` + `missing_topic_only_clean`, calls every `analysis_*.py` with shared CLI flags via `_common.parse_and_load()`.
   - Output goes under `charts/analysis/{keyword_clean,missing_clean}/{1_profiling,2_content,3_visuals}/`.
   - Never invoke a single `analysis_*.py` directly without going through the driver (unless debugging one chart).

## Common loader

All scripts share `_common.py` which provides `parse_and_load()`. Standard CLI flags:
`--xlsx --sheet --topic-col --exclude-journals --phase-dir --subdir`. The loader applies the journal filter, builds the subset palette from unique `topic_label` values, and aliases `topic_label` → `keyword_hit` so legacy logic keeps working.

## Output structure rule

**All analysis chart output MUST be organized into 3 phase subdirs with numbered filenames**, mirroring the methodology phases:

```
charts/analysis/
├── 1_profiling/       1.1_yearly_trend.png, 1.2_top_journals.png, 1.3_topic_distribution.png, ...
├── 2_content/         2.1_keyword_network_topics.png, 2.2_topic_tsne.png, 2.3_geographic.png, ...
└── 3_visuals/         3.1_wordcloud_overall.png, 3.2.N_wordcloud_<topic>.png, ...
```

Every chart filename starts with its phase.subphase number (1.1, 1.2, 2.1, 2.2b, 3.2.1, etc.). When adding a new analysis, place it in the right phase and assign the next subnumber. The universal entry-point script is `analysis_universal.py` — extend it rather than creating loose scripts.

## Journal filter rule

**Before running analysis, always offer a multi-select option to exclude journals.** Print the top-20 journals from the xlsx first (with paper counts), then ask via `AskUserQuestion` (multiSelect=true) which to drop. Standard groups to offer:
- MDPI high-volume mega-journals (Sustainability Switzerland, Energies, Processes, Applied Sciences, …)
- Trade / non-English engineering journals (Kang T Ieh Iron and Steel, Chernye Metally, Chinese-language metallurgy, …)
- "Keep all" option

Pass the exclusions to `analysis_universal.py` via `--exclude-journals "Title1|Title2|Title3"` (pipe-separated, case-insensitive). Report the papers-removed count.

## Interaction rule

All user prompts in this skill MUST be selection-based via `AskUserQuestion` with 2–4 concrete options and a `(Recommended)` default. No free-form paste prompts.


Post-search analysis pipeline for the SLR Scopus output. Operates on two clean sheets (Energies and Sustainability Switzerland journals removed):
- `keyword_verified_clean` — papers that matched keyword topics (≈260 papers, has `keyword_hit` column)
- `missing_topic_only_clean` — papers that did NOT match any keyword (≈1400 papers, no `keyword_hit`)

## Analysis Pipeline

```
SLR xlsx
    │
    ├── keyword_verified_clean ─────────────────────
    │   ├── Phase 1: Data Profiling
    │   │   ├── 1.1 Yearly trend — absolute + 100% stacked bars (1×2)
    │   │   ├── 1.2 Citation analysis — distribution, boxplot, top-cited, score vs cites
    │   │   ├── 1.3 Journal analysis — coverage + year trend combined (2×2)
    │   │   └── 1.4 Subset overlap — bar chart + chord diagram
    │   ├── Phase 2: Content Analysis
    │   │   ├── 2.1 Keyword network — NMF topic-term table + network graph (1×2)
    │   │   ├── 2.2 Topic analysis — NMF t-SNE + topic-year trend
    │   │   └── 2.3 Geographic distribution — per subset
    │   └── Phase 3: Visuals
    │       ├── 3.1 Word clouds — combined 2×2 grid
    │       └── 3.2 Subset-specific TF-IDF keywords
    │
    └── missing_topic_only_clean ──────────────────
        ├── Phase 1: Data Profiling
        │   ├── 1.1 Yearly trend
        │   ├── 1.2 Citation distribution + top-cited
        │   └── 1.3 Journal analysis (2×2)
        ├── Phase 2: Content Analysis
        │   ├── 2.2 Topic analysis
        │   └── 2.3 Geographic distribution (overall)
        └── Phase 3: Visuals
            └── 3.1 Overall word cloud
```

## Prerequisites

| Requirement | How to check |
|-------------|-------------|
| SLR xlsx with `keyword_verified` and `missing_topic_only` sheets | `output/<stem>/SLR_Scopus_<tag>/SLR_Scopus_<tag>.xlsx` |
| matplotlib + seaborn | `uv pip install matplotlib seaborn` |
| openpyxl | Already in project deps |
| scikit-learn | Already in project deps (TF-IDF, NMF, t-SNE) |
| networkx | `uv pip install networkx` for keyword network |
| wordcloud | `uv pip install wordcloud` for word clouds |

## Quick Run

```bash
cd /path/to/research_finder

# Run all analyses (both keyword_clean and missing_clean)
PYTHONPATH=src .venv/bin/python skills/test-slr-analysis/analysis_yearly_trend.py
PYTHONPATH=src .venv/bin/python skills/test-slr-analysis/analysis_citations.py
PYTHONPATH=src .venv/bin/python skills/test-slr-analysis/analysis_journals.py
PYTHONPATH=src .venv/bin/python skills/test-slr-analysis/analysis_subset_overlap.py
PYTHONPATH=src .venv/bin/python skills/test-slr-analysis/analysis_keyword_network.py
PYTHONPATH=src .venv/bin/python skills/test-slr-analysis/analysis_topic_modeling.py
PYTHONPATH=src .venv/bin/python skills/test-slr-analysis/analysis_geographic.py
PYTHONPATH=src .venv/bin/python skills/test-slr-analysis/analysis_wordcloud.py
PYTHONPATH=src .venv/bin/python skills/test-slr-analysis/analysis_subset_tfidf.py
```

## Script Inventory

| Script | Sheet(s) | Phase | Output |
|--------|----------|-------|--------|
| `analysis_yearly_trend.py` | both | Profiling | `1.1_yearly_trend_by_subset.png` (1×2: absolute + % stacked) |
| `analysis_citations.py` | both | Profiling | `1.2_citations_distribution.png` (adaptive panels) |
| `analysis_journals.py` | both | Profiling | `1.3_journal_coverage.png` (2×2: coverage + year trend) |
| `analysis_subset_overlap.py` | keyword_clean | Profiling | `1.4_subset_overlap.png` (bar + chord) |
| `analysis_keyword_network.py` | keyword_clean | Content | `2.1_keyword_network.png` (1×2: topic-term bars + graph) |
| `analysis_topic_modeling.py` | both | Content | `2.2_topic_analysis.png` (t-SNE + stacked bars) |
| `analysis_geographic.py` | both | Content | `2.3_geographic_distribution.png` (per-subset or overall) |
| `analysis_wordcloud.py` | both | Visuals | `3.1_wordclouds.png` (2×2) or `3.1_wordcloud_overall.png` |
| `analysis_subset_tfidf.py` | keyword_clean | Visuals | `3.2_subset_tfidf.png` (per-subset TF-IDF) |

## Figure Numbering Convention

All charts follow a `{phase}.{number}_{name}.png` scheme, ordered from most general (broad dataset overview) to most specific (deep content analysis):

| # | Figure | Layout | Phase | Logic |
|---|--------|--------|-------|-------|
| 1.1 | `yearly_trend_by_subset` | 1×2 | Profiling | *When* — absolute + 100% stacked bars |
| 1.2 | `citations_distribution` | 2×2 | Profiling | *Impact* — distribution, boxplot, top-cited, score vs cites |
| 1.3 | `journal_coverage` | 2×2 | Profiling | *Where* — subset coverage + year trend combined |
| 1.4 | `subset_overlap` | 1×2 | Profiling | *Theme overlap* — exclusive/overlap bars + chord diagram |
| 2.1 | `keyword_network` | 1×2 | Content | *Term relationships* — topic-term coefficient bars + network graph |
| 2.2 | `topic_analysis` | 2×2 | Content | *Latent themes* — NMF t-SNE + topic-year stacked bars |
| 2.3 | `geographic_distribution` | 2×2 | Content | *Where (authors)* — per-subset country distribution |
| 3.1 | `wordclouds` | 2×2 | Visuals | *Synthesis* — combined word clouds per subset |
| 3.2 | `subset_tfidf` | 2×2 | Visuals | *Distinctive terms* — per-subset TF-IDF keywords |

Directories mirror phases: `1_profiling/`, `2_content/`, `3_visuals/`

## Output Structure

```
output/<input_stem>/SLR_Scopus_<tag>/charts/analysis/
├── keyword_clean/              # keyword-matched papers
│   ├── 1_profiling/
│   │   ├── 1.1_yearly_trend_by_subset.png
│   │   ├── 1.2_citations_distribution.png
│   │   ├── 1.3_journal_coverage.png
│   │   └── 1.4_subset_overlap.png
│   ├── 2_content/
│   │   ├── 2.1_keyword_network.png
│   │   ├── 2.2_topic_analysis.png
│   │   └── 2.3_geographic_distribution.png
│   └── 3_visuals/
│       ├── 3.1_wordclouds.png
│       └── 3.2_subset_tfidf.png
└── missing_clean/              # non-matching papers
    ├── 1_profiling/
    │   ├── 1.1_yearly_trend_by_subset.png
    │   ├── 1.2_citations_distribution.png
    │   └── 1.3_journal_coverage.png
    ├── 2_content/
    │   ├── 2.2_topic_analysis.png
    │   └── 2.3_geographic_distribution.png
    └── 3_visuals/
        └── 3.1_wordcloud_overall.png
```

## Subset Naming Convention

All charts use full subset names (not single letters):

| Short | Display name | Description |
|-------|-------------|-------------|
| energy | Energy | Energy transitions, markets, systems |
| industrial | Industrial | Industrial decarbonization, ecology |
| green | Green | Green/sustainable/low-carbon transition |
| firm | Firm & Decision | Firm-level decisions, adoption, innovation |

## Data Source Columns

| Column | Used for |
|--------|----------|
| `keyword_hit` | Subset tags, term matches (keyword_clean only) |
| `score` | Cosine similarity — scatter plots |
| `citations` | Citation count — impact metric |
| `year` | Temporal analysis |
| `journal` | Journal coverage, heatmap |
| `title` | TF-IDF, word cloud, topic modeling |
| `abstract` | TF-IDF, topic modeling, word cloud |
| `affiliations` | Geographic distribution |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `keyword_hit` column missing | Running keyword analysis on missing_clean | Expected — analysis adapts automatically |
| Empty abstract column | `--no-abstract-enrich` was set | Re-run search without that flag or work with titles only |
| matplotlib import error | matplotlib not installed | `uv pip install matplotlib seaborn` |
| networkx missing | Optional dep not installed | `uv pip install networkx` |
| wordcloud missing | Optional dep not installed | `uv pip install wordcloud` |
| NMF/t-SNE slow on missing_clean | 1400+ papers | Expected — use smaller random subset if too slow |

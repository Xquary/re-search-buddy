# Skills

Claude/opencode skill definitions for the research_finder project. Each subdirectory contains a `SKILL.md` that documents how to run and debug a specific test or workflow.

These skills are **canonical** — they are also symlinked (or copied) into `.claude/skills/` so the AI can load them. If you create a new skill, add it here first, then copy it to `.claude/skills/` to make it loadable.

## Skill List

### Test Skills

These 7 skills cover every test script in the project — use them as operational runbooks:

| # | Skill | Script | Description |
|---|-------|--------|-------------|
| 1 | `test-mcp` | `test_mcp.py` | MCP server connectivity smoke test (arXiv, Scholar, CNKI) |
| 2 | `test-scholar` | `test_pipeline.py` | Google Scholar → embed → rank → xlsx → download |
| 3 | `test-arxiv` | `test_arxiv_pipeline.py` | arXiv → embed → rank → xlsx → download |
| 4 | `test-semantic-scholar` | `test_semantic_scholar_pipeline.py` | Semantic Scholar REST API → embed → rank → xlsx → download |
| 5 | `test-cnki` | `test_cnki_pipeline.py` | English→Chinese translate → CNKI → embed → rank → xlsx |
| 6 | `test-pipeline` | `pipeline.py` (CLI) | Full multi-source pipeline via `research_finder find` |
| 7 | `test-input-scan` | `scan_input.py` | Input file scanning & embedding cache |

### Workflow Skills

| # | Skill | Script Pattern | Description |
|---|-------|----------------|-------------|
| 8 | `citation-search` | `test_<stem>.py` | Analyze text → draft queries → Scholar search → embed → rank → map results to citation gaps |
| 9 | `slr` | `slr_scopus.py` / `slr_semantic_scholar.py` | Systematic literature review (Scopus + Semantic Scholar): scoped search → embed → rank → XLSX + charts |

## Skill Template

When creating a new skill, follow this structure in `SKILL.md`:

```markdown
---
name: my-skill
description: What this skill does. Use when <condition>.
argument-hint: "[optional arguments]"
---

# <Title>

Brief overview of what the test/workflow does.

## Prerequisites

| Requirement | How to check/setup |
|-------------|-------------------|
| ... | ... |

## Quick Run

```bash
PYTHONPATH=src .venv/bin/python <script>.py
```

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--flag` | value | What it does |

## Steps Performed

1. Step one
2. Step two
...

## Expected Output

```
stdout markers and output paths
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| ... | ... | ... |

## Script Reference

File: `<script>.py` — additional notes.
```

## Directory Layout

```
skills/
├── README.md              # This file
├── test-mcp/
│   └── SKILL.md          # MCP connectivity smoke test
├── test-scholar/
│   └── SKILL.md          # Google Scholar pipeline
├── test-arxiv/
│   └── SKILL.md          # arXiv pipeline
├── test-semantic-scholar/
│   └── SKILL.md          # Semantic Scholar pipeline
├── test-cnki/
│   └── SKILL.md          # CNKI pipeline
├── test-pipeline/
│   └── SKILL.md          # Full CLI pipeline
├── test-input-scan/
│   └── SKILL.md          # Input scanning & cache
└── citation-search/
    └── SKILL.md          # Citation gap literature search
```

## Making Skills Loadable

Skills in this directory are the **source of truth**. To make them loadable by Claude/opencode, copy them into `.claude/skills/`:

```bash
# Copy all skills
cp -r skills/* .claude/skills/

# Or copy a single skill
cp -r skills/citation-search .claude/skills/
```

The `.claude/skills/` directory also contains CNKI-specific skills from `cookjohn/cnki-skills` (those are not managed here — they are installed from the upstream repo).

## Using Skills

Load a skill in Claude/opencode and it will inject the full instructions into the conversation:

```
/load test-arxiv
/load citation-search
```

Or invoke the skill via `/skill-name` if configured as a slash command.

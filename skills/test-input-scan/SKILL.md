---
name: test-input-scan
description: Test input file scanning and embedding cache. Use to verify the input store (raw → markdown → embedding → cache) pipeline works correctly.
argument-hint: "[--list | --no-prune]"
---

# Input Scan Test

Tests the input store pipeline: scan `input/raw/` for new or changed files → extract plain text (PDF/DOCX/MD/TXT) → embed via configured provider → cache `.npy` vectors. Runs ``skills/test-input-scan/scan_input.py``.

Also verifies cache invalidation logic: raw changes trigger re-extract + re-embed; markdown edits trigger re-embed; config changes (model/provider) trigger re-embed; unchanged files skip.

## Prerequisites

- Project venv: `uv venv && uv pip install -e ".[dev]"`
- `.env` configured with `OPENAI_API_KEY` (for API embeddings)
- `config.yaml` has `embedding.provider` and `embedding.api.model` set
- At least one file in `input/raw/` (`.md`, `.txt`, `.docx`, or `.pdf`)

## Quick Run

```bash
# Scan input/raw/ for new/changed files and embed them
PYTHONPATH=src .venv/bin/python skills/test-input-scan/scan_input.py

# List currently cached inputs (no processing)
PYTHONPATH=src .venv/bin/python skills/test-input-scan/scan_input.py --list

# Scan but keep manifest entries for deleted raw files
PYTHONPATH=src .venv/bin/python skills/test-input-scan/scan_input.py --no-prune
```

## CLI Flags

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to config.yaml (default: `config.yaml`) |
| `--input-dir DIR` | Input directory root (default: `input`) |
| `--list` | List cached inputs and exit (no scanning) |
| `--no-prune` | Keep manifest entries for deleted raw files instead of cleaning up |

## Steps Performed

1. **Walk `input/raw/`** — enumerate files, hash each with SHA256
2. **Compare hashes** — check against `input/embeddings/manifest.json`
3. **For new or changed raw files**:
   - Extract text (PyMuPDF for PDF, python-docx for DOCX, UTF-8 for md/txt)
   - Write canonical `input/markdown/<stem>.md`
   - Embed via configured embedder
   - Save `input/embeddings/<stem>.npy`
   - Update manifest
4. **For markdown-only edits** (raw unchanged, md different):
   - Re-embed from edited markdown
   - Update manifest (keep raw hash)
5. **For provider/model changes**:
   - Re-embed all files
6. **For unchanged files**: skip
7. **Prune** (default): remove manifest entries + `.npy` + `.md` for deleted raw files

## Expected Output

```
Scanning input/raw
  [new]     foo.pdf  → input/markdown/foo.md  → input/embeddings/foo.npy
  [updated] bar.md   → re-embedded, md hash updated
  [skip]    baz.txt  (unchanged)

  added:     1  ['foo.pdf']
  updated:   1  ['bar.md']
  md_edited: 0  []
  unchanged: 1  ['baz.txt']
  removed:   0  []
```

## Output Layout

```
input/
├── raw/             # user drops files here
│   ├── paper1.pdf
│   └── notes.txt
├── markdown/        # auto-extracted plain-text copies
│   ├── paper1.md
│   └── notes.md
└── embeddings/      # per-file .npy vectors + manifest.json
    ├── paper1.npy
    ├── notes.npy
    └── manifest.json
```

## Manifest Entry Format

```json
{
  "raw_sha256": "abc123...",
  "md_sha256": "def456...",
  "char_count": 13921,
  "provider": "api",
  "model": "text-embedding-3-small",
  "dimensions": 1536,
  "embedded_at": "2026-04-17T12:00:00",
  "markdown_path": "paper1.md",
  "embedding_path": "paper1.npy"
}
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "(no cached inputs)" | `input/raw/` is empty | Drop files into `input/raw/` first |
| PDF extraction produces garbage | PDF is scanned/image-based | Use OCR'd PDF; PyMuPDF needs text layer |
| DOCX fails | `python-docx` not installed | `uv pip install python-docx` |
| Embedding fails | `OPENAI_API_KEY` missing | Check `.env` |
| File skipped with "unsupported format" | File is not .md/.txt/.docx/.pdf | Convert to supported format |
| `load()` refuses vector | Model mismatch (`manifest.json` model ≠ current config) | Re-run `skills/test-input-scan/scan_input.py` (auto re-embeds) |

## Using Cached Embeddings in Test Pipelines

All 4 test pipelines accept `--input <name>` to load pre-computed embeddings:

```bash
PYTHONPATH=src .venv/bin/python skills/test-input-scan/scan_input.py              # embed first
PYTHONPATH=src .venv/bin/python skills/test-scholar/test_pipeline.py --input paper1  # then use
```

`name` can be the raw filename, markdown filename, or stem (without extension).

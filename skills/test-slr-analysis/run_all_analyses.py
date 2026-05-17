"""Driver: run every analysis_*.py on each sheet of an SLR xlsx.

Usage:
  PYTHONPATH=src .venv/bin/python skills/test-slr-analysis/run_all_analyses.py \\
    --xlsx <path> [--exclude-journals "A|B|C"] [--sheets sheetA,sheetB]
"""
import argparse, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent
SCRIPTS = [
    "analysis_yearly_trend.py",
    "analysis_citations.py",
    "analysis_journals.py",
    "analysis_journal_year_trend.py",
    "analysis_subset_overlap.py",
    "analysis_keyword_network.py",
    "analysis_topic_modeling.py",
    "analysis_geographic.py",
    "analysis_subset_tfidf.py",
    "analysis_wordcloud.py",
]

ap = argparse.ArgumentParser()
ap.add_argument("--xlsx", required=True)
ap.add_argument("--sheets", default="keyword_verified_clean,missing_topic_only_clean")
ap.add_argument("--exclude-journals", default="")
ap.add_argument("--top-cited", type=int, default=15, help="for analysis_citations.py highlights")
ap.add_argument("--top-relevant", type=int, default=15, help="for analysis_citations.py highlights")
args = ap.parse_args()

import openpyxl
wb = openpyxl.load_workbook(args.xlsx, read_only=True)
available = set(wb.sheetnames)
wb.close()

requested = [s.strip() for s in args.sheets.split(",") if s.strip()]
sheets = [s for s in requested if s in available]
missing = [s for s in requested if s not in available]
if missing:
    print(f"[warn] sheets not in xlsx, skipping: {missing}")
if not sheets:
    print(f"[error] no requested sheet exists. available: {sorted(available)}")
    sys.exit(1)

subdir_map = {
    "keyword_verified_clean": "keyword_clean",
    "missing_topic_only_clean": "missing_clean",
}

for sheet in sheets:
    sub = subdir_map.get(sheet, sheet)
    print(f"\n{'='*70}\n  SHEET: {sheet}  →  charts/analysis/{sub}/\n{'='*70}")
    for script in SCRIPTS:
        cmd = [sys.executable, str(ROOT / script),
               "--xlsx", args.xlsx, "--sheet", sheet, "--subdir", sub]
        if args.exclude_journals:
            cmd += ["--exclude-journals", args.exclude_journals]
        if script == "analysis_citations.py":
            cmd += ["--top-cited", str(args.top_cited), "--top-relevant", str(args.top_relevant)]
        print(f"\n--- {script} ---")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.stdout: print(r.stdout.rstrip())
        if r.returncode != 0:
            print(f"[FAIL] {script}\n{r.stderr.rstrip()}")

print(f"\n[done] all analyses dispatched.")

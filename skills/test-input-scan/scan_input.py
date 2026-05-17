"""Scan input/raw/ and embed new or changed files into input/embeddings/.

Usage:
    PYTHONPATH=src .venv/bin/python scan_input.py           # scan + report
    PYTHONPATH=src .venv/bin/python scan_input.py --list    # list cached inputs
    PYTHONPATH=src .venv/bin/python scan_input.py --no-prune  # keep stale manifest entries
"""
from __future__ import annotations

import argparse
import sys

import dotenv
import yaml

dotenv.load_dotenv()

from research_finder.input_store import InputStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--input-dir", default="input", help="Input directory root")
    parser.add_argument("--list", action="store_true", help="List cached inputs and exit")
    parser.add_argument("--no-prune", action="store_true", help="Keep manifest entries for deleted files")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    store = InputStore(cfg, input_dir=args.input_dir)

    if args.list:
        rows = store.list()
        if not rows:
            print("(no cached inputs yet — drop files into input/raw/ and run scan_input.py)")
            return 0
        print(f"Cached inputs ({len(rows)}):")
        for r in rows:
            print(f"  {r['name']:30s}  dim={r['dimensions']:<5d}  model={r['model']:28s}  chars={r['char_count']}")
        return 0

    print(f"Scanning {store.raw_dir}")
    result = store.scan(prune_missing=not args.no_prune, verbose=True)

    print()
    print(f"  added:     {len(result.added)}  {result.added}")
    print(f"  updated:   {len(result.updated)}  {result.updated}")
    print(f"  md_edited: {len(result.md_edited)}  {result.md_edited}")
    print(f"  unchanged: {len(result.unchanged)}  {result.unchanged}")
    print(f"  removed:   {len(result.removed)}  {result.removed}")
    if result.skipped:
        print(f"  skipped:   {len(result.skipped)}")
        for name, reason in result.skipped:
            print(f"    - {name}: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

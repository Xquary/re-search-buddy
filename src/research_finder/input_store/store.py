"""On-disk store that caches embeddings for user input files.

Flow
----
1. User drops files into ``input/raw/`` (``.md`` / ``.txt`` / ``.docx`` / ``.pdf``).
2. :meth:`InputStore.scan` walks that directory, extracts plain text, and
   writes a canonical ``.md`` copy to ``input/markdown/`` (you can inspect or
   hand-edit it before embedding). It then embeds that markdown text and
   writes a ``.npy`` into ``input/embeddings/``, with a ``manifest.json``
   tracking raw-file and markdown-file hashes.
3. Scan semantics:
     - raw file new or changed → regenerate markdown, re-embed
     - only the markdown was edited → re-embed from the edited markdown
     - provider/model changed → re-embed
     - else → skip
4. Downstream pipelines call :meth:`InputStore.load` to get back the cached
   embedding + markdown text without re-invoking the embedder.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..embedder import get_embedder
from .reader import SUPPORTED_EXTENSIONS, read_text

MANIFEST_FILENAME = "manifest.json"


@dataclass
class ScanResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)       # raw changed
    md_edited: list[str] = field(default_factory=list)     # only markdown changed
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (name, reason)


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class InputStore:
    """Cache + lookup for embeddings of files in ``input/raw/``."""

    def __init__(self, config: dict[str, Any], input_dir: Path | str = "input"):
        self.config = config
        self.input_dir = Path(input_dir)
        self.raw_dir = self.input_dir / "raw"
        self.markdown_dir = self.input_dir / "markdown"
        self.embeddings_dir = self.input_dir / "embeddings"
        self.manifest_path = self.embeddings_dir / MANIFEST_FILENAME
        for d in (self.raw_dir, self.markdown_dir, self.embeddings_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._embedder = None  # lazy

    # ── manifest helpers ──────────────────────────────────────────────────
    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        if not self.manifest_path.exists():
            return {}
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return data.get("files", {})

    def _save_manifest(self, files: dict[str, dict[str, Any]]) -> None:
        payload = {"version": 2, "files": files}
        self.manifest_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── config helpers ────────────────────────────────────────────────────
    def _model_signature(self) -> tuple[str, str]:
        emb_cfg = self.config.get("embedding", {}) or {}
        provider = emb_cfg.get("provider", "api")
        if provider == "api":
            model = (emb_cfg.get("api") or {}).get("model", "text-embedding-3-small")
        else:
            model = (emb_cfg.get("local") or {}).get("model_name", "all-MiniLM-L6-v2")
        return provider, model

    def _get_embedder(self):
        if self._embedder is None:
            self._embedder = get_embedder(self.config)
        return self._embedder

    # ── path helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _markdown_name(raw_name: str) -> str:
        return Path(raw_name).stem + ".md"

    @staticmethod
    def _embedding_name(raw_name: str) -> str:
        return Path(raw_name).stem + ".npy"

    @staticmethod
    def _is_supported_raw(p: Path) -> bool:
        if not p.is_file():
            return False
        # Filter WSL/Windows junk like "foo.pdf:Zone.Identifier" or "*.Zone.Identifier"
        if "Zone.Identifier" in p.name or p.name.startswith("."):
            return False
        return p.suffix.lower() in SUPPORTED_EXTENSIONS

    # ── public API ────────────────────────────────────────────────────────
    def scan(self, *, prune_missing: bool = True, verbose: bool = True) -> ScanResult:
        """Walk ``raw/``, convert → markdown → embed, update manifest."""
        manifest = self._load_manifest()
        provider, model = self._model_signature()
        result = ScanResult()

        all_in_raw = sorted(self.raw_dir.iterdir())
        present: dict[str, Path] = {}
        for p in all_in_raw:
            if not p.is_file():
                continue
            if "Zone.Identifier" in p.name or p.name.startswith("."):
                continue  # silently ignore WSL/dotfile junk
            if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                result.skipped.append((p.name, f"unsupported extension {p.suffix}"))
                continue
            present[p.name] = p

        for name, raw_path in present.items():
            raw_bytes = raw_path.read_bytes()
            raw_sha = _sha256_bytes(raw_bytes)
            entry = manifest.get(name) or {}

            md_path = self.markdown_dir / self._markdown_name(name)
            raw_changed = entry.get("raw_sha256") != raw_sha
            need_regen_md = raw_changed or not md_path.exists()

            # 1. Raw → markdown (regenerate if raw changed or md missing)
            if need_regen_md:
                try:
                    md_text = read_text(raw_path)
                except Exception as e:
                    result.skipped.append((name, f"read error: {e}"))
                    continue
                md_path.write_text(md_text, encoding="utf-8")
                if verbose:
                    reason = "raw changed" if entry else "new"
                    print(f"  [{reason}] extracted {raw_path.name} → {md_path.name} ({len(md_text)} chars)")
            else:
                md_text = md_path.read_text(encoding="utf-8")

            md_sha = _sha256_text(md_text)

            # 2. Decide whether to (re-)embed
            embed_reason: str | None = None
            if not entry:
                embed_reason = "new"
            elif raw_changed:
                embed_reason = "raw_changed"
            elif entry.get("md_sha256") != md_sha:
                embed_reason = "md_edited"
            elif entry.get("model") != model or entry.get("provider") != provider:
                embed_reason = "model_changed"
            elif not (self.embeddings_dir / entry.get("embedding_path", "")).exists():
                embed_reason = "npy_missing"

            if embed_reason is None:
                result.unchanged.append(name)
                continue

            embedder = self._get_embedder()
            if verbose:
                print(f"  [{embed_reason}] embedding {md_path.name} ({len(md_text)} chars)")
            vec = embedder.embed_single(md_text)
            npy_name = self._embedding_name(name)
            np.save(self.embeddings_dir / npy_name, vec)
            manifest[name] = {
                "raw_sha256": raw_sha,
                "md_sha256": md_sha,
                "char_count": len(md_text),
                "provider": provider,
                "model": model,
                "dimensions": int(vec.shape[0]),
                "embedded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "markdown_path": md_path.name,
                "embedding_path": npy_name,
            }
            if embed_reason == "new":
                result.added.append(name)
            elif embed_reason == "md_edited":
                result.md_edited.append(name)
            else:
                result.updated.append(name)

        if prune_missing:
            for stale in [n for n in manifest if n not in present]:
                npy = self.embeddings_dir / manifest[stale].get("embedding_path", "")
                md = self.markdown_dir / manifest[stale].get("markdown_path", "")
                if npy.exists():
                    npy.unlink()
                if md.exists():
                    md.unlink()
                manifest.pop(stale)
                result.removed.append(stale)

        self._save_manifest(manifest)
        return result

    def list(self) -> list[dict[str, Any]]:
        manifest = self._load_manifest()
        return [{"name": n, **meta} for n, meta in sorted(manifest.items())]

    def load(self, name: str) -> tuple[np.ndarray, str]:
        """Load the cached embedding + markdown text for ``name``.

        ``name`` may be the raw filename (``foo.pdf``), the markdown filename
        (``foo.md``), or just the stem (``foo``).
        """
        manifest = self._load_manifest()
        resolved = self._resolve(name, manifest)
        entry = manifest[resolved]

        provider, model = self._model_signature()
        if entry.get("provider") != provider or entry.get("model") != model:
            raise RuntimeError(
                f"Cached embedding for '{resolved}' was made with "
                f"{entry.get('provider')}/{entry.get('model')}, but config now says "
                f"{provider}/{model}. Re-run scan to refresh."
            )
        npy_path = self.embeddings_dir / entry["embedding_path"]
        if not npy_path.exists():
            raise FileNotFoundError(
                f"Embedding file missing for '{resolved}': {npy_path}. Run scan first."
            )
        md_path = self.markdown_dir / entry["markdown_path"]
        if not md_path.exists():
            raise FileNotFoundError(
                f"Markdown file missing for '{resolved}': {md_path}. Run scan first."
            )
        vec = np.load(npy_path)
        text = md_path.read_text(encoding="utf-8")
        return vec, text

    def _resolve(self, name: str, manifest: dict[str, dict[str, Any]]) -> str:
        if name in manifest:
            return name
        stem = Path(name).stem
        matches = [n for n in manifest if Path(n).stem == stem]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous input name '{name}': matches {matches}")
        raise FileNotFoundError(
            f"No input named '{name}' in manifest. Run scan or use one of: {list(manifest)}"
        )

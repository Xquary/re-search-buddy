from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import Paper
from .searcher.registry import get_enabled_searchers


class Pipeline:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def run(self, text: str) -> list[Paper]:
        """Run the full research finding pipeline."""
        zotero_cfg = self.config.get("zotero", {})
        zotero_enabled = zotero_cfg.get("enabled", False)

        manager = None
        if zotero_enabled:
            from .zotero import ZoteroClientManager
            manager = ZoteroClientManager(self.config)
            manager.connect()

        try:
            return self._run_inner(text, manager)
        finally:
            if manager:
                manager.disconnect()

    def _run_inner(self, text: str, manager: Any) -> list[Paper]:
        """Inner pipeline logic; manager is a connected ZoteroClientManager or None."""
        zotero_cfg = self.config.get("zotero", {})

        # Step 1: Extract keywords and form search queries
        from .extractor.keyword_extractor import KeywordExtractor
        extractor = KeywordExtractor(self.config)
        queries = extractor.extract(text)

        # Step 2: Search across databases
        searchers = get_enabled_searchers(self.config)

        # Inject ZoteroSearcher when library search is enabled
        if manager and zotero_cfg.get("search_library", True):
            from .zotero import ZoteroSearcher
            searchers.append(ZoteroSearcher(self.config, manager))

        papers: list[Paper] = []
        for searcher in searchers:
            results = searcher.search(queries)
            papers.extend(results)

        # Deduplicate by title
        seen: set[str] = set()
        unique_papers: list[Paper] = []
        for p in papers:
            key = p.title.lower().strip()
            if key not in seen:
                seen.add(key)
                unique_papers.append(p)
        papers = unique_papers

        if not papers:
            return []

        # Step 2.5: Flag papers already in Zotero library
        if manager and zotero_cfg.get("check_duplicates", True):
            from .zotero import ZoteroChecker
            ZoteroChecker(self.config, manager).check_and_flag(papers)

        # Step 3: Embed and rank
        from .embedder.registry import get_embedder
        from .ranker.similarity import rank_papers
        embedder = get_embedder(self.config)
        text_embedding = embedder.embed_single(text)
        paper_texts = [f"{p.title} {p.abstract or ''} {' '.join(p.keywords)}" for p in papers]
        paper_embeddings = embedder.embed_batch(paper_texts)

        top_n = self.config.get("ranking", {}).get("top_n", 10)
        threshold = self.config.get("ranking", {}).get("similarity_threshold", 0.3)
        ranked = rank_papers(text_embedding, paper_embeddings, papers, top_n=top_n, threshold=threshold)

        # Step 4: Save results
        self._save_results(ranked)

        # Step 5: Download full texts
        output_dir: Path | None = None
        if self.config.get("output", {}).get("download_fulltext", True):
            from .downloader.fulltext import download_papers
            output_dir = Path(self.config.get("output", {}).get("dir", "./output"))
            downloads_dir = output_dir / "downloads"
            browser_download = self.config.get("output", {}).get("browser_download", False)
            download_papers(ranked, downloads_dir, browser_download=browser_download)

        # Step 6: Export top papers to Zotero
        if manager and zotero_cfg.get("export_results", False):
            from .zotero import ZoteroExporter
            ZoteroExporter(self.config, manager).export(ranked, downloads_dir)

        return ranked

    def _save_results(self, papers: list[Paper]) -> None:
        output_dir = Path(self.config.get("output", {}).get("dir", "./output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        output_format = self.config.get("output", {}).get("format", "json")

        if output_format == "json":
            data = [asdict(p) for p in papers]
            with open(output_dir / "results.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

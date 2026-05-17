from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from .config import load_config

console = Console()


@click.group()
@click.version_option()
def cli():
    """Research Finder - Find relevant academic papers based on your writing."""


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None, help="Path to config.yaml")
@click.option("--top-n", type=int, default=None, help="Number of top papers to return")
@click.option("--no-download", is_flag=True, help="Skip full-text PDF download")
@click.option("--no-zotero", is_flag=True, help="Disable all Zotero integration for this run")
@click.option("--no-zotero-export", is_flag=True, help="Skip exporting results to Zotero (search/check still run)")
def find(
    input_file: Path,
    config_path: Path | None,
    top_n: int | None,
    no_download: bool,
    no_zotero: bool,
    no_zotero_export: bool,
):
    """Run the full pipeline: extract keywords -> search -> rank -> download."""
    config = load_config(config_path)
    if top_n is not None:
        config["ranking"]["top_n"] = top_n
    if no_download:
        config["output"]["download_fulltext"] = False
    if no_zotero:
        config.setdefault("zotero", {})["enabled"] = False
    if no_zotero_export:
        config.setdefault("zotero", {})["export_results"] = False

    from .pipeline import Pipeline

    text = input_file.read_text(encoding="utf-8")
    console.print(f"[bold blue]Input:[/bold blue] {input_file.name} ({len(text)} chars)")

    pipe = Pipeline(config)
    results = pipe.run(text)

    console.print(f"\n[bold green]Found {len(results)} relevant papers:[/bold green]")
    for i, paper in enumerate(results, 1):
        library_tag = " [dim](in library)[/dim]" if paper.in_library else ""
        console.print(f"\n[bold]{i}. {paper.title}[/bold]{library_tag}")
        console.print(f"   Score: {paper.score:.3f} | Source: {paper.source}")
        console.print(f"   {paper.abstract[:200]}..." if paper.abstract and len(paper.abstract) > 200 else f"   {paper.abstract or 'No abstract'}")


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
def search(input_file: Path, config_path: Path | None):
    """Search databases only (no ranking or download)."""
    config = load_config(config_path)

    from .extractor.keyword_extractor import KeywordExtractor
    from .searcher.registry import get_enabled_searchers

    text = input_file.read_text(encoding="utf-8")
    extractor = KeywordExtractor(config)
    queries = extractor.extract(text)

    console.print("[bold blue]Extracted queries:[/bold blue]")
    for q in queries:
        console.print(f"  - {q}")

    searchers = get_enabled_searchers(config)
    all_papers = []
    for searcher in searchers:
        console.print(f"\n[bold]Searching {searcher.name}...[/bold]")
        papers = searcher.search(queries)
        console.print(f"  Found {len(papers)} results")
        all_papers.extend(papers)

    console.print(f"\n[bold green]Total: {len(all_papers)} papers found[/bold green]")


@cli.command()
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
def config(config_path: Path | None):
    """Show current configuration."""
    import yaml

    cfg = load_config(config_path)
    # Mask API keys
    if "llm" in cfg and "api_key" in cfg["llm"] and cfg["llm"]["api_key"]:
        cfg["llm"]["api_key"] = cfg["llm"]["api_key"][:8] + "..."
    console.print(yaml.dump(cfg, default_flow_style=False))


if __name__ == "__main__":
    cli()

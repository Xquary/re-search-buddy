from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Paper:
    title: str
    abstract: str | None = None
    retrieval_query: str | None = None
    keywords: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    publication: str | None = None
    publisher: str | None = None
    metadata_line: str | None = None
    document_type: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    source: str = ""
    year: int | None = None
    doi: str | None = None
    tldr: str | None = None
    score: float = 0.0
    zotero_key: str | None = None  # Zotero item key; set by ZoteroSearcher or ZoteroExporter
    in_library: bool = False        # True if paper already exists in user's Zotero library
    # SLR-enriched fields (populated by ScopusSearcher STANDARD view)
    issn: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    scopus_id: str | None = None
    open_access: bool = False
    author_keywords: str | None = None
    affiliations: str | None = None  # semicolon-separated "Org; City; Country" strings

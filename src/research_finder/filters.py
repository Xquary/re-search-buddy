"""Post-search filters applied to ``Paper`` lists."""
from __future__ import annotations

from typing import Iterable

from .models import Paper


def filter_by_year(
    papers: Iterable[Paper],
    year_from: int | None = None,
    year_to: int | None = None,
    *,
    drop_missing_year: bool = True,
) -> list[Paper]:
    """Return papers whose ``year`` lies within ``[year_from, year_to]``.

    ``None`` for either bound means that side is unbounded. Papers with
    ``year is None`` are dropped by default when any bound is active; pass
    ``drop_missing_year=False`` to keep them.
    """
    if year_from is None and year_to is None:
        return list(papers)
    out: list[Paper] = []
    for p in papers:
        if p.year is None:
            if drop_missing_year:
                continue
            out.append(p)
            continue
        if year_from is not None and p.year < year_from:
            continue
        if year_to is not None and p.year > year_to:
            continue
        out.append(p)
    return out

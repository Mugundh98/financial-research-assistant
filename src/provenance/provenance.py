"""Provenance reporting.

Summarizes the distinct sources behind an answer — their type, filing, URL, and
as-of date — plus the freshness window. This is what lets a reader trust (and
independently verify) every figure and claim.
"""
from __future__ import annotations

from ..contracts.models import AnalysisResult


def build_provenance(result: AnalysisResult) -> dict:
    sources: dict[str, dict] = {}
    for c in result.citations:
        sources[c.source_id] = {
            "type": c.source_type.value,
            "source": c.source,
            "url": c.source_url,
            "as_of": c.as_of.isoformat() if c.as_of else None,
            "form": c.form,
            "accession": c.accession,
        }
    by_type: dict[str, int] = {}
    for s in sources.values():
        by_type[s["type"]] = by_type.get(s["type"], 0) + 1

    fr = result.freshness
    return {
        "source_count": len(sources),
        "by_type": by_type,
        "as_of_oldest": fr.oldest_as_of.isoformat() if fr.oldest_as_of else None,
        "as_of_newest": fr.newest_as_of.isoformat() if fr.newest_as_of else None,
        "freshest_age_days": fr.max_age_days,
        "is_stale": fr.is_stale,
        "sources": sorted(sources.values(), key=lambda s: (s["type"], s["as_of"] or "")),
    }

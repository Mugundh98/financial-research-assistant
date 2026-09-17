"""Normalize raw SEC EDGAR JSON into validated data contracts.

This is the enforcement point for the "data contracts" rubric item: raw upstream
JSON only becomes a first-class object once it passes through these functions and
validates against the Pydantic models. Provenance (source_url, accession) and
temporal stamps (``as_of``) are attached here so nothing downstream has to guess.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from ..config import settings
from ..contracts.models import Company, FinancialFact

# A pragmatic core set of GAAP concepts most useful for decision-intelligence.
# (Different filers tag revenue differently, hence the two revenue concepts.)
CORE_CONCEPTS: list[str] = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "CostOfRevenue",
    "GrossProfit",
    "OperatingIncomeLoss",
    "NetIncomeLoss",
    "ResearchAndDevelopmentExpense",
    "Assets",
    "Liabilities",
    "StockholdersEquity",
    "CashAndCashEquivalentsAtCarryingValue",
    "EarningsPerShareDiluted",
]


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _classify_period(start: Optional[date], end: Optional[date]) -> str:
    """Classify a fact's period by duration (robust to SEC's `fp`/`fy` quirks)."""
    if end and not start:
        return "instant"          # balance-sheet point-in-time
    if start and end:
        days = (end - start).days
        if 330 <= days <= 400:
            return "annual"
        if 80 <= days <= 100:
            return "quarter"
        if 150 <= days <= 200:
            return "half"
        if 250 <= days <= 290:
            return "ytd9"
        return "other"
    return "unknown"


def company_from_submissions(sub: dict) -> Company:
    tickers = sub.get("tickers") or []
    return Company(
        cik=str(sub.get("cik", "")),
        ticker=tickers[0] if tickers else None,
        name=sub.get("name", ""),
        sic=str(sub["sic"]) if sub.get("sic") else None,
        sic_description=sub.get("sicDescription"),
        fiscal_year_end=sub.get("fiscalYearEnd"),
    )


def facts_from_company_concept(
    cik: str, concept_json: dict, company: Optional[str] = None
) -> list[FinancialFact]:
    cik10 = "".join(ch for ch in str(cik) if ch.isdigit()).zfill(10)
    tag = concept_json.get("tag", "")
    taxonomy = concept_json.get("taxonomy", "us-gaap")
    label = concept_json.get("label")
    source_url = (
        f"{settings.sec_base_data}/api/xbrl/companyconcept/"
        f"CIK{cik10}/{taxonomy}/{tag}.json"
    )
    facts: list[FinancialFact] = []
    for unit, entries in (concept_json.get("units") or {}).items():
        for e in entries:
            try:
                value = float(e["val"])
            except (KeyError, TypeError, ValueError):
                continue
            start = _parse_date(e.get("start"))
            end = _parse_date(e.get("end"))
            filed = _parse_date(e.get("filed"))
            period_type = _classify_period(start, end)
            # Derive the fiscal-year label from the period end, NOT SEC's filing
            # `fy` (which tags prior-year comparatives with the filing's year).
            fiscal_year = end.year if end else e.get("fy")
            fact_id = (
                f"{cik10}:{tag}:{e.get('fy')}:{e.get('fp')}:"
                f"{e.get('start') or ''}:{e.get('end')}:{e.get('accn')}"
            )
            facts.append(
                FinancialFact(
                    id=fact_id,
                    cik=cik10,
                    company=company,
                    taxonomy=taxonomy,
                    concept=tag,
                    label=label,
                    value=value,
                    unit=unit,
                    fiscal_year=fiscal_year,
                    fiscal_period=e.get("fp"),
                    period_type=period_type,
                    period_start=start,
                    period_end=end,
                    filed=filed,
                    form=e.get("form"),
                    accession=e.get("accn"),
                    frame=e.get("frame"),
                    source_url=source_url,
                    approved=True,
                    as_of=end or filed,
                )
            )
    return facts


def facts_from_company_facts(
    cik: str, facts_json: dict, concepts: Optional[list[str]] = None
) -> list[FinancialFact]:
    company = facts_json.get("entityName")
    us_gaap = ((facts_json.get("facts") or {}).get("us-gaap")) or {}
    wanted = concepts if concepts is not None else list(us_gaap.keys())
    out: list[FinancialFact] = []
    for tag in wanted:
        node = us_gaap.get(tag)
        if not node:
            continue
        concept_json = {
            "tag": tag,
            "taxonomy": "us-gaap",
            "label": node.get("label"),
            "units": node.get("units", {}),
        }
        out.extend(facts_from_company_concept(cik, concept_json, company))
    return out

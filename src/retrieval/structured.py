"""Structured retrieval over financial facts (the 'structured data' half of RAG).

Typed queries over validated :class:`FinancialFact` objects: filter by
company/concept/period, resolve human metric names to GAAP concepts, and build
clean per-year series for the deterministic calculation tools to consume.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from ..contracts.models import Citation, FinancialFact, SourceType

# Human metric name -> candidate GAAP concept tags (filers tag revenue two ways).
CONCEPT_SYNONYMS: dict[str, list[str]] = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
    "net income": ["NetIncomeLoss"],
    "gross profit": ["GrossProfit"],
    "operating income": ["OperatingIncomeLoss"],
    "cost of revenue": ["CostOfRevenue"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "equity": ["StockholdersEquity"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "r&d": ["ResearchAndDevelopmentExpense"],
    "eps": ["EarningsPerShareDiluted"],
}


def _pad_cik(cik: str) -> str:
    digits = "".join(ch for ch in str(cik) if ch.isdigit())
    return digits.zfill(10) if digits else ""


class FactStore:
    def __init__(self, facts: list[FinancialFact], companies=None):
        self.facts = list(facts)
        self._ticker_to_cik = {
            c.ticker.upper(): c.cik for c in (companies or []) if c.ticker
        }

    def resolve_cik(self, cik: Optional[str] = None, ticker: Optional[str] = None) -> Optional[str]:
        if cik:
            return _pad_cik(cik)
        if ticker:
            return self._ticker_to_cik.get(ticker.upper())
        return None

    def query(
        self,
        cik: Optional[str] = None,
        ticker: Optional[str] = None,
        concept: Optional[str] = None,
        concepts: Optional[list[str]] = None,
        fiscal_period: Optional[str] = None,
        fiscal_year: Optional[int] = None,
        form: Optional[str] = None,
        unit: Optional[str] = None,
    ) -> list[FinancialFact]:
        target = self.resolve_cik(cik, ticker)
        wanted = set(concepts or ([concept] if concept else []))
        out = []
        for f in self.facts:
            if target and f.cik != target:
                continue
            if wanted and f.concept not in wanted:
                continue
            if fiscal_period and f.fiscal_period != fiscal_period:
                continue
            if fiscal_year and f.fiscal_year != fiscal_year:
                continue
            if form and f.form != form:
                continue
            if unit and f.unit != unit:
                continue
            out.append(f)
        return out

    def metric(self, name: str, cik=None, ticker=None, period: str = "FY") -> list[FinancialFact]:
        concepts = CONCEPT_SYNONYMS.get(name.lower(), [name])
        return self.query(cik=cik, ticker=ticker, concepts=concepts, fiscal_period=period)

    def _facts_for(self, name: str, cik=None, ticker=None, unit: Optional[str] = "USD") -> list[FinancialFact]:
        concepts = CONCEPT_SYNONYMS.get(name.lower(), [name])
        facts = self.query(cik=cik, ticker=ticker, concepts=concepts)
        return [f for f in facts if (unit is None or f.unit == unit)]

    def series(self, name: str, cik=None, ticker=None, period: str = "FY", unit: Optional[str] = "USD") -> list[FinancialFact]:
        """Annual time series: one fact per fiscal year.

        Flow metrics (revenue, income) use annual-duration facts; stock metrics
        (assets, cash) use the fiscal-year-end balance from 10-Ks. Ties broken by
        the most recent (period_end, filed), i.e. the latest restatement.
        """
        facts = self._facts_for(name, cik=cik, ticker=ticker, unit=unit)
        pool = [f for f in facts if f.period_type == "annual"]
        if not pool:  # stock/instant metric -> year-end balances
            instants = [f for f in facts if f.period_type == "instant"]
            pool = [f for f in instants if (f.form or "").startswith("10-K")] or instants

        def rank(f: FinancialFact):
            return (f.period_end or date.min, f.filed or date.min)

        by_year: dict[int, FinancialFact] = {}
        for f in pool:
            if f.fiscal_year is None:
                continue
            if f.fiscal_year not in by_year or rank(f) > rank(by_year[f.fiscal_year]):
                by_year[f.fiscal_year] = f
        return [by_year[y] for y in sorted(by_year)]

    def latest(self, name: str, cik=None, ticker=None, period: str = "FY", unit: Optional[str] = "USD") -> Optional[FinancialFact]:
        s = self.series(name, cik=cik, ticker=ticker, period=period, unit=unit)
        return s[-1] if s else None


def fact_to_citation(fact: FinancialFact) -> Citation:
    return Citation(
        source_id=fact.id,
        source_type=SourceType.FINANCIAL_FACT,
        source=fact.source,
        source_url=fact.source_url,
        as_of=fact.as_of,
        form=fact.form,
        accession=fact.accession,
        snippet=f"{fact.concept} {fact.fiscal_period or ''}{fact.fiscal_year or ''} = {fact.value:,.0f} {fact.unit}",
    )

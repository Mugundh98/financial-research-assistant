from datetime import date

from src.agent.guardrails import compute_freshness, verify
from src.agent.planning import Plan
from src.config import settings
from src.contracts.models import (
    AnalysisResult,
    ApprovalStatus,
    Citation,
    Claim,
    SourceType,
)


def _cited(stmt, as_of=None):
    return Claim(statement=stmt, citations=[
        Citation(source_id=stmt, source_type=SourceType.FINANCIAL_FACT, as_of=as_of)
    ])


def test_uncited_claims_dropped():
    r = AnalysisResult(query_id="x", query="q", findings=[
        _cited("supported claim"),
        Claim(statement="unsupported claim"),
    ])
    verify(r, Plan(raw_query="q"), settings)
    assert len(r.findings) == 1
    assert r.findings[0].statement == "supported claim"
    assert r.findings[0].supported is True


def test_advice_triggers_approval_and_disclaimer():
    r = AnalysisResult(query_id="x", query="q", findings=[_cited("fact")])
    verify(r, Plan(raw_query="q", is_advice=True), settings)
    assert r.requires_human_approval is True
    assert r.approval.status == ApprovalStatus.PENDING
    assert any("recommend" in d.lower() for d in r.disclaimers)


def test_research_disclaimer_always_added():
    r = AnalysisResult(query_id="x", query="q", findings=[_cited("fact")])
    verify(r, Plan(raw_query="q"), settings)
    assert any("research assistance" in d.lower() for d in r.disclaimers)


def test_freshness_flags_old_data():
    old = [Citation(source_id="s", source_type=SourceType.FINANCIAL_FACT, as_of=date(2000, 1, 1))]
    fr = compute_freshness(old, settings, today=date(2026, 1, 1))
    assert fr.is_stale is True


def test_refusal_when_no_evidence():
    r = AnalysisResult(query_id="x", query="q")
    verify(r, Plan(raw_query="q"), settings)
    assert r.refused is True

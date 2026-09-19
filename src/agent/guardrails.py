"""Guardrails: enforce citations, freshness, safe communication, and approval.

Runs AFTER composition, over the assembled AnalysisResult. It is the layer that
"prevents unsupported financial conclusions": any claim without a citation is
dropped, freshness is computed and surfaced, advice is refused, and low-confidence
or high-impact answers are routed to a human-approval gate.
"""
from __future__ import annotations

from datetime import date

from ..config import Settings
from ..contracts.models import (
    AnalysisResult,
    ApprovalDecision,
    ApprovalStatus,
    Citation,
    FreshnessInfo,
)
from .planning import Plan

RESEARCH_DISCLAIMER = "This is research assistance, not personalized investment advice."
NO_RECS_DISCLAIMER = "The assistant does not make buy/sell/hold recommendations."


def _dedupe_citations(citations: list[Citation]) -> list[Citation]:
    seen: set[str] = set()
    out: list[Citation] = []
    for c in citations:
        if c.source_id not in seen:
            seen.add(c.source_id)
            out.append(c)
    return out


def compute_freshness(citations: list[Citation], cfg: Settings, today: date | None = None) -> FreshnessInfo:
    today = today or date.today()
    dates = [c.as_of for c in citations if c.as_of]
    if not dates:
        return FreshnessInfo()
    oldest, newest = min(dates), max(dates)
    age_of_newest = (today - newest).days
    is_stale = age_of_newest > cfg.staleness_days
    stale_sources = [c.source_id for c in citations if c.as_of and (today - c.as_of).days > cfg.staleness_days]
    return FreshnessInfo(
        oldest_as_of=oldest,
        newest_as_of=newest,
        max_age_days=age_of_newest,          # age of the freshest evidence
        is_stale=is_stale,
        stale_sources=stale_sources if is_stale else [],
    )


def _confidence(result: AnalysisResult, dropped: int) -> float:
    score = 0.4
    score += min(0.3, 0.1 * len([c for c in result.calculations if not c.error]))
    if len(result.citations) >= 3:
        score += 0.15
    if dropped:
        score -= 0.25
    if result.freshness.is_stale:
        score -= 0.15
    return max(0.0, min(1.0, round(score, 2)))


def _needs_approval(result: AnalysisResult, plan: Plan, dropped: int) -> tuple[bool, str]:
    if plan.is_advice:
        return True, "User requested a recommendation/decision; human sign-off required."
    if plan.intent == "scenario":
        return True, "Answer contains forward-looking projections; human review required."
    if dropped:
        return True, "Unsupported claims were removed; human review recommended."
    if result.confidence < 0.4:
        return True, "Low confidence in available evidence."
    return False, ""


def verify(result: AnalysisResult, plan: Plan, cfg: Settings, today: date | None = None) -> AnalysisResult:
    # 1. Drop unsupported claims (no citation => not allowed to stand).
    supported, dropped = [], 0
    for claim in result.findings:
        if claim.citations:
            claim.supported = True
            supported.append(claim)
        else:
            dropped += 1
    result.findings = supported

    # 2. Aggregate + de-duplicate citations from findings and calculations.
    all_cites = [c for f in result.findings for c in f.citations]
    all_cites += [c for tc in result.calculations for c in tc.citations]
    result.citations = _dedupe_citations(all_cites)

    # 3. Freshness.
    result.freshness = compute_freshness(result.citations, cfg, today)
    if result.freshness.is_stale:
        result.caveats.append(
            f"Most recent source is ~{result.freshness.max_age_days} days old (> {cfg.staleness_days}d threshold)."
        )

    # 4. Safe communication.
    result.disclaimers.append(RESEARCH_DISCLAIMER)
    if plan.is_advice:
        result.disclaimers.append(NO_RECS_DISCLAIMER)
        result.caveats.append("You asked for a recommendation; only sourced facts and comparisons are provided.")

    # 5. Confidence.
    result.confidence = _confidence(result, dropped)

    # 6. Refuse if nothing is supported.
    if not result.findings and not [c for c in result.calculations if not c.error]:
        result.refused = True
        result.refusal_reason = "No approved SEC-sourced evidence supports an answer."
        result.answer = "I couldn't find approved, SEC-sourced evidence to answer that, so I won't speculate."

    # 7. Human-approval gate.
    needs, reason = _needs_approval(result, plan, dropped)
    result.requires_human_approval = needs
    if needs:
        result.approval = ApprovalDecision(status=ApprovalStatus.PENDING, reason=reason)

    return result

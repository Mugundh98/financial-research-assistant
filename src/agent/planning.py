"""Lightweight, deterministic query planning.

Parses the natural-language question into a structured :class:`Plan`: which
companies, what intent, which metrics, and whether the user is (improperly)
asking for advice. Kept rule-based so the plan is reproducible and testable;
the LLM is reserved for prose, not control flow.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..retrieval.structured import CONCEPT_SYNONYMS

INTENTS = ("risks", "scenario", "compare", "margin", "growth", "metric", "overview")

_ADVICE_PATTERNS = [
    "should i", "should we", "buy", "sell", "invest in", "worth buying",
    "good stock", "good investment", "recommend", "is it a good", "price target",
]


@dataclass
class Plan:
    raw_query: str
    tickers: list[str] = field(default_factory=list)
    intent: str = "overview"
    metrics: list[str] = field(default_factory=lambda: ["revenue"])
    is_advice: bool = False

    def __str__(self) -> str:
        return f"intent={self.intent} tickers={self.tickers} metrics={self.metrics} advice={self.is_advice}"


def _detect_tickers(query: str, companies) -> list[str]:
    q = query.lower()
    found: list[tuple[int, str]] = []
    for co in companies:
        if not co.ticker:
            continue
        first_word = co.name.split()[0].lower().strip(".,")
        pos = None
        m = re.search(rf"\b{re.escape(co.ticker.lower())}\b", q)
        if m:
            pos = m.start()
        elif first_word and len(first_word) > 2 and first_word in q:
            pos = q.index(first_word)
        if pos is not None:
            found.append((pos, co.ticker))
    found.sort(key=lambda t: t[0])
    # de-dupe preserving first-appearance order
    seen: set[str] = set()
    return [tk for _, tk in found if not (tk in seen or seen.add(tk))]


def _detect_metrics(query: str) -> list[str]:
    q = query.lower()
    metrics = [name for name in CONCEPT_SYNONYMS if name in q]
    if "profit" in q and "gross profit" not in metrics:
        metrics.append("net income")
    return metrics or ["revenue"]


def _detect_intent(query: str, n_tickers: int) -> str:
    q = query.lower()
    if any(w in q for w in ("risk", "threat", "headwind", "concern")):
        return "risks"
    if any(w in q for w in ("scenario", "project", "forecast", "what if", "assume", "grow at")):
        return "scenario"
    if "compare" in q or " vs " in q or "versus" in q or "compared to" in q or n_tickers > 1:
        return "compare"
    if "margin" in q or "profitab" in q:
        return "margin"
    if any(w in q for w in ("grow", "growth", "cagr", "increase", "declin")):
        return "growth"
    if any(name in q for name in CONCEPT_SYNONYMS):
        return "metric"
    return "overview"


def plan_query(query: str, companies) -> Plan:
    tickers = _detect_tickers(query, companies)
    return Plan(
        raw_query=query,
        tickers=tickers,
        intent=_detect_intent(query, len(tickers)),
        metrics=_detect_metrics(query),
        is_advice=any(p in query.lower() for p in _ADVICE_PATTERNS),
    )


def tool_requests(plan: Plan) -> list[tuple[str, dict]]:
    """Deterministic tool selection for the plan (ticker added later, per company)."""
    reqs: list[tuple[str, dict]] = []
    metrics = plan.metrics or ["revenue"]

    if plan.intent in ("growth", "compare", "metric", "overview"):
        for m in metrics:
            reqs.append(("get_metric", {"metric": m}))
            reqs.append(("growth_rate", {"metric": m}))
            reqs.append(("cagr", {"metric": m, "years": 4}))
    elif plan.intent == "margin":
        q = plan.raw_query.lower()
        numer = "gross profit" if "gross" in q else "operating income" if "operating" in q else "net income"
        reqs.append(("margin", {"metric": numer}))
    elif plan.intent == "scenario":
        for m in metrics:
            reqs.append((
                "compare_scenarios",
                {"metric": m, "years": 3, "scenarios": [
                    {"name": "conservative", "growth_rate": 0.05},
                    {"name": "base", "growth_rate": 0.10},
                    {"name": "bull", "growth_rate": 0.15},
                ]},
            ))
    elif plan.intent == "risks":
        for m in metrics:
            reqs.append(("get_metric", {"metric": m}))

    return reqs

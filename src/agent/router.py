"""Model & capability selection (lighter-fidelity rubric item).

Routes to a cheaper/faster model for simple lookups and a stronger model for
work that needs synthesis (comparisons, scenarios, qualitative risk reading or
multi-company questions). Returns the model id and a tier label for logging.
"""
from __future__ import annotations

from ..config import Settings
from .planning import Plan

_COMPLEX_INTENTS = {"compare", "scenario", "risks"}


def select_model(plan: Plan, cfg: Settings) -> tuple[str, str]:
    complex_task = (
        plan.intent in _COMPLEX_INTENTS
        or len(plan.tickers) > 1
        or len(plan.metrics) > 1
        or len(plan.raw_query) > 160
    )
    if complex_task:
        return cfg.llm_model_strong, "strong"
    return cfg.llm_model_fast, "fast"

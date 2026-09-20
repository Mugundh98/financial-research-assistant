"""Model & capability selection (lighter-fidelity rubric item).

Routes to a cheaper/faster model for simple lookups and a stronger model for
work that needs synthesis (comparisons, scenarios, qualitative risk reading or
multi-company questions). Returns the model id and a tier label for logging.
"""
from __future__ import annotations

from ..config import Settings
from .planning import Plan

_COMPLEX_INTENTS = {"compare", "scenario", "risks"}


def select_model(plan: Plan, cfg: Settings) -> str:
    """Return the capability tier ('strong' or 'fast'). The concrete model id is
    resolved per active backend via ``llm.model_for_tier(tier)``."""
    complex_task = (
        plan.intent in _COMPLEX_INTENTS
        or len(plan.tickers) > 1
        or len(plan.metrics) > 1
        or len(plan.raw_query) > 160
    )
    return "strong" if complex_task else "fast"

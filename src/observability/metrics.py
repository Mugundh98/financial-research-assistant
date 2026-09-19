"""Token economics and per-stage latency.

`CostMeter` accumulates token usage and (approximate) dollar cost across a
session — the "token economics" and "latency/cost trade-off" story. `Stopwatch`
records per-stage timings so a single answer's cost in time is attributable.
"""
from __future__ import annotations

import time

from ..contracts.models import TokenUsage


class CostMeter:
    def __init__(self) -> None:
        self.queries = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0

    def record(self, usage: TokenUsage) -> None:
        self.queries += 1
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cost_usd += usage.cost_usd

    def summary(self) -> dict:
        return {
            "queries": self.queries,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }


class Stopwatch:
    """Records elapsed time between ``lap`` calls, in milliseconds."""

    def __init__(self) -> None:
        self.stages: dict[str, float] = {}
        self._t = time.perf_counter()

    def lap(self, name: str) -> None:
        now = time.perf_counter()
        self.stages[name] = round((now - self._t) * 1000, 1)
        self._t = now

    def total(self) -> float:
        return round(sum(self.stages.values()), 1)

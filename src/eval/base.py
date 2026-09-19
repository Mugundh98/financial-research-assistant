"""Tiny evaluation harness types."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Case:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class SuiteResult:
    name: str
    cases: list[Case] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def add(self, name: str, passed: bool, detail: str = "") -> bool:
        self.cases.append(Case(name, bool(passed), detail))
        return bool(passed)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 1.0

    def to_dict(self) -> dict:
        return {
            "suite": self.name,
            "passed": self.passed,
            "total": self.total,
            "rate": round(self.rate, 3),
            "metrics": self.metrics,
            "cases": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in self.cases],
        }

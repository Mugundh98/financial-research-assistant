"""Numeric-accuracy evaluation.

Three layers: (1) independent math identities, (2) reported values vs public
ground truth, (3) tool-vs-manual consistency. This is the check that would have
caught the fiscal-year mislabel bug.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..config import settings
from ..retrieval import FactStore
from ..tools import calculations as calc, default_registry
from .base import SuiteResult


def _value_for_year(fs: FactStore, metric: str, ticker: str, year: Optional[int]):
    if year is None:
        f = fs.latest(metric, ticker=ticker)
    else:
        f = next((x for x in fs.series(metric, ticker=ticker) if x.fiscal_year == year), None)
    return f


def run_numeric(corpus, truth_path: Optional[Path] = None) -> SuiteResult:
    s = SuiteResult("numeric_accuracy")
    fs = FactStore(corpus.facts, corpus.companies)
    reg = default_registry()

    # 1) independent math identities
    s.add("cagr(100->400 over 2y) == 100%", abs(calc.cagr(100, 400, 2) - 1.0) < 1e-9)
    s.add("yoy_growth(100->150) == 50%", abs(calc.yoy_growth(100, 150) - 0.5) < 1e-9)
    s.add("npv(10%, [-100,50,50,50]) ~ 24.3426", abs(calc.npv(0.1, [-100, 50, 50, 50]) - 24.3426) < 1e-3)
    s.add("irr([-100,50,50,50]) ~ 23.32%", abs(calc.irr([-100, 50, 50, 50]) - 0.2332) < 2e-3)

    # 2) reported values vs public ground truth
    path = truth_path or (settings.base_dir / "evals" / "numeric_truth.json")
    for t in json.loads(Path(path).read_text(encoding="utf-8")):
        f = _value_for_year(fs, t["metric"], t["ticker"], t.get("year"))
        got = f.value if f else None
        ok = got is not None and abs(got - t["expected"]) <= t.get("tol", 0)
        detail = f"expected {t['expected']:,} got {int(got):,}" if got is not None else "missing"
        s.add(f"{t['ticker']} {t['metric']} FY{t.get('year')}", ok, detail)

    # 3) tool output must equal manual computation from reported values
    series = {x.fiscal_year: x.value for x in fs.series("revenue", ticker="AAPL")}
    if 2024 in series and 2025 in series:
        manual = (series[2025] - series[2024]) / series[2024]
        tc = reg.dispatch("growth_rate", {"ticker": "AAPL", "metric": "revenue", "from_year": 2024, "to_year": 2025}, fs)
        s.add("growth_rate tool == manual (AAPL rev 24->25)",
              not tc.error and abs(tc.output - manual) < 1e-9,
              f"tool={tc.output:.6f} manual={manual:.6f}")
    return s

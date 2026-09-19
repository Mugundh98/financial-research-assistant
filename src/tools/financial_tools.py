"""Fact-aware tools: pull inputs from the FactStore and return cited ToolCalls.

These are what the agent (and, via the registry, the LLM) call. Each tool:
  * resolves its numeric inputs from validated SEC facts,
  * runs a pure function from :mod:`calculations`,
  * returns a :class:`ToolCall` carrying the formula and **citations** to every
    fact used — so no computed number is ever unsourced.

Every handler takes the FactStore as its first positional arg (``fs``) and only
keyword args after it, so the registry can dispatch LLM tool calls uniformly.
Errors are captured into ``ToolCall.error`` rather than raised.
"""
from __future__ import annotations

from typing import Optional

from ..contracts.models import FinancialFact, ToolCall
from ..retrieval.structured import FactStore, fact_to_citation
from . import calculations as calc


def _pick(series: list[FinancialFact], year: Optional[int], default_index: int) -> Optional[FinancialFact]:
    if year is not None:
        return next((f for f in series if f.fiscal_year == year), None)
    if len(series) >= abs(default_index):
        return series[default_index]
    return None


def _fact_for_year(fs, metric, ticker=None, cik=None, year=None) -> Optional[FinancialFact]:
    series = fs.series(metric, ticker=ticker, cik=cik)
    return _pick(series, year, default_index=-1)


def get_metric(fs: FactStore, *, ticker=None, metric="revenue", year=None, cik=None) -> ToolCall:
    inputs = {"ticker": ticker, "metric": metric, "year": year}
    try:
        f = _fact_for_year(fs, metric, ticker=ticker, cik=cik, year=year)
        if not f:
            raise ValueError(f"no reported '{metric}' found")
        return ToolCall(
            tool="get_metric", inputs=inputs, output=f.value, unit=f.unit,
            formula=f"reported {f.concept} for FY{f.fiscal_year}",
            citations=[fact_to_citation(f)],
        )
    except Exception as e:  # noqa: BLE001 - surface as tool error
        return ToolCall(tool="get_metric", inputs=inputs, error=str(e))


def growth_rate(fs: FactStore, *, ticker=None, metric="revenue", from_year=None, to_year=None, cik=None) -> ToolCall:
    inputs = {"ticker": ticker, "metric": metric, "from_year": from_year, "to_year": to_year}
    try:
        series = fs.series(metric, ticker=ticker, cik=cik)
        if len(series) < 2 and not (from_year and to_year):
            raise ValueError("need at least two annual data points")
        begin = _pick(series, from_year, default_index=-2)
        end = _pick(series, to_year, default_index=-1)
        if not begin or not end:
            raise ValueError("could not locate the requested fiscal years")
        value = calc.yoy_growth(begin.value, end.value)
        return ToolCall(
            tool="growth_rate", inputs=inputs, output=value, unit="ratio",
            formula=f"(FY{end.fiscal_year} {end.value:,.0f} - FY{begin.fiscal_year} {begin.value:,.0f}) / {begin.value:,.0f}",
            citations=[fact_to_citation(begin), fact_to_citation(end)],
        )
    except Exception as e:  # noqa: BLE001
        return ToolCall(tool="growth_rate", inputs=inputs, error=str(e))


def cagr(fs: FactStore, *, ticker=None, metric="revenue", years=None, from_year=None, to_year=None, cik=None) -> ToolCall:
    inputs = {"ticker": ticker, "metric": metric, "years": years, "from_year": from_year, "to_year": to_year}
    try:
        series = fs.series(metric, ticker=ticker, cik=cik)
        if not series:
            raise ValueError("no data")
        if from_year is not None and to_year is not None:
            begin = _pick(series, from_year, -1)
            end = _pick(series, to_year, -1)
        else:
            n = years if years is not None else len(series) - 1
            end = series[-1]
            begin = series[-1 - n] if len(series) > n else series[0]
        if not begin or not end:
            raise ValueError("could not locate the requested fiscal years")
        span = (end.fiscal_year or 0) - (begin.fiscal_year or 0)
        value = calc.cagr(begin.value, end.value, span)
        return ToolCall(
            tool="cagr", inputs=inputs, output=value, unit="ratio",
            formula=f"({end.value:,.0f}/{begin.value:,.0f})^(1/{span}) - 1",
            citations=[fact_to_citation(begin), fact_to_citation(end)],
        )
    except Exception as e:  # noqa: BLE001
        return ToolCall(tool="cagr", inputs=inputs, error=str(e))


def margin(fs: FactStore, *, ticker=None, metric="net income", year=None, cik=None) -> ToolCall:
    inputs = {"ticker": ticker, "metric": metric, "year": year}
    try:
        part = _fact_for_year(fs, metric, ticker=ticker, cik=cik, year=year)
        if not part:
            raise ValueError(f"no reported '{metric}'")
        revenue = _fact_for_year(fs, "revenue", ticker=ticker, cik=cik, year=part.fiscal_year)
        if not revenue:
            raise ValueError("no revenue to form a margin")
        value = calc.margin(part.value, revenue.value)
        return ToolCall(
            tool="margin", inputs=inputs, output=value, unit="ratio",
            formula=f"{metric} {part.value:,.0f} / revenue {revenue.value:,.0f} (FY{part.fiscal_year})",
            citations=[fact_to_citation(part), fact_to_citation(revenue)],
        )
    except Exception as e:  # noqa: BLE001
        return ToolCall(tool="margin", inputs=inputs, error=str(e))


def ratio(fs: FactStore, *, ticker=None, numerator="net income", denominator="assets", year=None, cik=None) -> ToolCall:
    inputs = {"ticker": ticker, "numerator": numerator, "denominator": denominator, "year": year}
    try:
        num = _fact_for_year(fs, numerator, ticker=ticker, cik=cik, year=year)
        den = _fact_for_year(fs, denominator, ticker=ticker, cik=cik, year=(year or (num.fiscal_year if num else None)))
        if not num or not den:
            raise ValueError("missing numerator or denominator")
        value = calc.ratio(num.value, den.value)
        return ToolCall(
            tool="ratio", inputs=inputs, output=value, unit="ratio",
            formula=f"{numerator} {num.value:,.0f} / {denominator} {den.value:,.0f}",
            citations=[fact_to_citation(num), fact_to_citation(den)],
        )
    except Exception as e:  # noqa: BLE001
        return ToolCall(tool="ratio", inputs=inputs, error=str(e))


def project_metric(fs: FactStore, *, ticker=None, metric="revenue", growth_rate=0.0, years=3, base_year=None, cik=None) -> ToolCall:
    inputs = {"ticker": ticker, "metric": metric, "growth_rate": growth_rate, "years": years, "base_year": base_year}
    try:
        base = _fact_for_year(fs, metric, ticker=ticker, cik=cik, year=base_year)
        if not base:
            raise ValueError("no base value to project from")
        projected = calc.project(base.value, growth_rate, years)
        output = {
            "base_year": base.fiscal_year,
            "base_value": base.value,
            "growth_rate": growth_rate,
            "projection": [
                {"year": (base.fiscal_year or 0) + i + 1, "value": v} for i, v in enumerate(projected)
            ],
        }
        return ToolCall(
            tool="project_metric", inputs=inputs, output=output, unit=base.unit,
            formula=f"{base.value:,.0f} * (1+{growth_rate})^t for t=1..{years}",
            citations=[fact_to_citation(base)],
        )
    except Exception as e:  # noqa: BLE001
        return ToolCall(tool="project_metric", inputs=inputs, error=str(e))


def compare_scenarios(fs: FactStore, *, ticker=None, metric="revenue", scenarios=None, years=3, base_year=None, cik=None) -> ToolCall:
    inputs = {"ticker": ticker, "metric": metric, "scenarios": scenarios, "years": years, "base_year": base_year}
    try:
        base = _fact_for_year(fs, metric, ticker=ticker, cik=cik, year=base_year)
        if not base:
            raise ValueError("no base value to project from")
        scenarios = scenarios or [{"name": "base", "growth_rate": 0.05}]
        results = []
        for sc in scenarios:
            g = float(sc["growth_rate"])
            projected = calc.project(base.value, g, years)
            results.append({
                "name": sc.get("name", f"g={g:.0%}"),
                "growth_rate": g,
                "final_value": projected[-1],
                "projection": projected,
            })
        deltas = {}
        if len(results) >= 2:
            ref = results[0]
            for r in results[1:]:
                deltas[f"{r['name']} vs {ref['name']}"] = r["final_value"] - ref["final_value"]
        output = {
            "base_year": base.fiscal_year,
            "base_value": base.value,
            "horizon_year": (base.fiscal_year or 0) + years,
            "scenarios": results,
            "deltas": deltas,
        }
        return ToolCall(
            tool="compare_scenarios", inputs=inputs, output=output, unit=base.unit,
            formula="project each scenario base*(1+g)^t; compare final values at horizon",
            citations=[fact_to_citation(base)],
        )
    except Exception as e:  # noqa: BLE001
        return ToolCall(tool="compare_scenarios", inputs=inputs, error=str(e))


def npv_tool(fs: FactStore = None, *, rate=0.1, cashflows=None) -> ToolCall:
    inputs = {"rate": rate, "cashflows": cashflows}
    try:
        value = calc.npv(rate, cashflows or [])
        return ToolCall(
            tool="npv", inputs=inputs, output=value, unit="currency",
            formula="sum(cashflow_t / (1+rate)^t), t=0..n",
        )
    except Exception as e:  # noqa: BLE001
        return ToolCall(tool="npv", inputs=inputs, error=str(e))


def irr_tool(fs: FactStore = None, *, cashflows=None) -> ToolCall:
    inputs = {"cashflows": cashflows}
    try:
        value = calc.irr(cashflows or [])
        return ToolCall(
            tool="irr", inputs=inputs, output=value, unit="ratio",
            formula="rate r such that NPV(r) = 0",
        )
    except Exception as e:  # noqa: BLE001
        return ToolCall(tool="irr", inputs=inputs, error=str(e))

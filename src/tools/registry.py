"""Tool registry: names, JSON schemas (Anthropic function-calling format), dispatch.

`schemas()` returns the exact shape the Claude Messages API expects for `tools`,
so the same registry both documents the deterministic tools and drives the LLM's
function calling in the agent phase. `dispatch()` runs a tool by name with the
model's arguments and always returns a validated :class:`ToolCall`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..contracts.models import ToolCall
from . import financial_tools as ft


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict          # JSON schema for the tool's arguments
    handler: Callable[..., ToolCall]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict]:
        """Anthropic tool-use format: {name, description, input_schema}."""
        return [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in self._tools.values()
        ]

    def dispatch(self, name: str, args: Optional[dict] = None, fs=None) -> ToolCall:
        tool = self._tools.get(name)
        if tool is None:
            return ToolCall(tool=name, inputs=args or {}, error=f"unknown tool '{name}'")
        try:
            return tool.handler(fs, **(args or {}))
        except TypeError as e:
            return ToolCall(tool=name, inputs=args or {}, error=f"bad arguments: {e}")


# ---- schema fragments ----------------------------------------------------- #
def _str(desc: str) -> dict:
    return {"type": "string", "description": desc}


def _int(desc: str) -> dict:
    return {"type": "integer", "description": desc}


def _num(desc: str) -> dict:
    return {"type": "number", "description": desc}


_METRIC_DESC = "Metric name: revenue, net income, gross profit, operating income, cost of revenue, assets, liabilities, equity, cash, r&d, eps"


def default_registry() -> ToolRegistry:
    r = ToolRegistry()

    r.register(Tool(
        "get_metric",
        "Look up a single reported financial metric for a company and fiscal year (latest if year omitted). Returns the exact value with a citation to the SEC filing.",
        {"type": "object", "properties": {
            "ticker": _str("Company ticker, e.g. AAPL"),
            "metric": _str(_METRIC_DESC),
            "year": _int("Fiscal year (optional; latest if omitted)"),
        }, "required": ["ticker", "metric"]},
        ft.get_metric,
    ))

    r.register(Tool(
        "growth_rate",
        "Growth of a metric between two fiscal years (defaults to the two most recent). Returns a ratio (0.06 = 6%).",
        {"type": "object", "properties": {
            "ticker": _str("Company ticker"),
            "metric": _str(_METRIC_DESC),
            "from_year": _int("Start fiscal year (optional)"),
            "to_year": _int("End fiscal year (optional)"),
        }, "required": ["ticker", "metric"]},
        ft.growth_rate,
    ))

    r.register(Tool(
        "cagr",
        "Compound annual growth rate of a metric over the last N years, or between two fiscal years. Returns a ratio.",
        {"type": "object", "properties": {
            "ticker": _str("Company ticker"),
            "metric": _str(_METRIC_DESC),
            "years": _int("Number of years to look back (optional)"),
            "from_year": _int("Start fiscal year (optional)"),
            "to_year": _int("End fiscal year (optional)"),
        }, "required": ["ticker", "metric"]},
        ft.cagr,
    ))

    r.register(Tool(
        "margin",
        "A metric as a share of revenue for a fiscal year (e.g. net margin). Returns a ratio.",
        {"type": "object", "properties": {
            "ticker": _str("Company ticker"),
            "metric": _str("Numerator metric, e.g. 'net income', 'gross profit', 'operating income'"),
            "year": _int("Fiscal year (optional; latest if omitted)"),
        }, "required": ["ticker", "metric"]},
        ft.margin,
    ))

    r.register(Tool(
        "ratio",
        "Ratio of one metric to another for a fiscal year (e.g. net income / assets). Returns a ratio.",
        {"type": "object", "properties": {
            "ticker": _str("Company ticker"),
            "numerator": _str(_METRIC_DESC),
            "denominator": _str(_METRIC_DESC),
            "year": _int("Fiscal year (optional)"),
        }, "required": ["ticker", "numerator", "denominator"]},
        ft.ratio,
    ))

    r.register(Tool(
        "project_metric",
        "Project a metric forward N years at a constant annual growth rate from a base fiscal year (latest if omitted).",
        {"type": "object", "properties": {
            "ticker": _str("Company ticker"),
            "metric": _str(_METRIC_DESC),
            "growth_rate": _num("Annual growth rate as a decimal, e.g. 0.08 for 8%"),
            "years": _int("Number of years to project"),
            "base_year": _int("Base fiscal year (optional; latest if omitted)"),
        }, "required": ["ticker", "metric", "growth_rate", "years"]},
        ft.project_metric,
    ))

    r.register(Tool(
        "compare_scenarios",
        "Project a metric under several named growth scenarios and compare final values at the horizon.",
        {"type": "object", "properties": {
            "ticker": _str("Company ticker"),
            "metric": _str(_METRIC_DESC),
            "scenarios": {
                "type": "array",
                "description": "List of scenarios",
                "items": {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "growth_rate": {"type": "number", "description": "Annual growth as a decimal"},
                }, "required": ["growth_rate"]},
            },
            "years": _int("Years to project"),
            "base_year": _int("Base fiscal year (optional)"),
        }, "required": ["ticker", "metric", "scenarios", "years"]},
        ft.compare_scenarios,
    ))

    r.register(Tool(
        "npv",
        "Net present value of a cashflow series at a discount rate. cashflows[0] is at t=0.",
        {"type": "object", "properties": {
            "rate": _num("Discount rate as a decimal, e.g. 0.1"),
            "cashflows": {"type": "array", "items": {"type": "number"}, "description": "Cashflows, earliest first"},
        }, "required": ["rate", "cashflows"]},
        ft.npv_tool,
    ))

    r.register(Tool(
        "irr",
        "Internal rate of return of a cashflow series (rate where NPV = 0).",
        {"type": "object", "properties": {
            "cashflows": {"type": "array", "items": {"type": "number"}, "description": "Cashflows, earliest first; must include a sign change"},
        }, "required": ["cashflows"]},
        ft.irr_tool,
    ))

    return r

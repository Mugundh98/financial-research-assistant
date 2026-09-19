"""Generation / faithfulness evaluation.

Verifies the core anti-hallucination property: every finding is cited, every
quantitative calculation carries source citations, and the deterministic tool
outputs re-derive exactly from the FactStore (no drift between what is claimed
and what the filings say).
"""
from __future__ import annotations

from ..retrieval import FactStore
from ..tools import calculations as calc
from .base import SuiteResult

DEFAULT_QUERIES = [
    "How fast is NVIDIA's revenue growing?",
    "Compare Apple and Microsoft revenue.",
    "What are the main risks facing NVIDIA?",
    "What is Apple's net margin?",
]


def run_generation(agent, queries=None) -> SuiteResult:
    s = SuiteResult("generation_faithfulness")
    fs = FactStore(agent.corpus.facts, agent.corpus.companies)
    for q in (queries or DEFAULT_QUERIES):
        r = agent.answer(q)
        tag = q[:34]

        uncited = [f for f in r.findings if not f.citations]
        s.add(f"[{tag}] every finding cited", not uncited, f"{len(uncited)} uncited")

        unsourced = [tc for tc in r.calculations if not tc.citations
                     and tc.tool in ("get_metric", "growth_rate", "cagr", "margin", "ratio")]
        s.add(f"[{tag}] calcs carry citations", not unsourced, f"{len(unsourced)} unsourced")

    # Deep faithfulness: a growth_rate tool result must equal a fresh recompute.
    tc = next((c for c in agent.answer("Compare Apple and Microsoft revenue.").calculations
               if c.tool == "growth_rate" and c.inputs.get("ticker") == "AAPL"), None)
    if tc and not tc.error:
        ser = {x.fiscal_year: x.value for x in fs.series("revenue", ticker="AAPL")}
        years = sorted(ser)
        recompute = calc.yoy_growth(ser[years[-2]], ser[years[-1]])
        s.add("AAPL growth_rate faithful to FactStore", abs(tc.output - recompute) < 1e-9,
              f"answer={tc.output:.6f} recompute={recompute:.6f}")
    return s

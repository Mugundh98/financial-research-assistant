"""The agent: plan -> retrieve -> compute -> compose -> verify -> approve.

Deterministic evidence-gathering (retrieval + cited tools) is the backbone, so
every figure is sourced and reproducible. The LLM only writes the narrative
(with a mock fallback that yields a templated answer). Guardrails then verify
the result. The single return type is always :class:`AnalysisResult`.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..config import Settings, settings as default_settings
from ..contracts.models import (
    AccessContext,
    AnalysisResult,
    ApprovalDecision,
    ApprovalStatus,
    Assumption,
    Claim,
    RetrievalHit,
    ToolCall,
)
from ..ingestion.corpus import Corpus
from ..retrieval import DocumentRetriever, FactStore, hit_to_citation
from ..tools import default_registry
from . import guardrails, prompts
from .llm import BaseLLM, get_llm
from .planning import Plan, plan_query, tool_requests
from .router import select_model


@dataclass
class Evidence:
    hits: list[RetrievalHit] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)


def _fmt(value, unit) -> str:
    return prompts._fmt_value(value, unit)


class Agent:
    def __init__(self, corpus: Corpus, cfg: Optional[Settings] = None, llm: Optional[BaseLLM] = None):
        self.cfg = cfg or default_settings
        self.corpus = corpus
        self.factstore = FactStore(corpus.facts, corpus.companies)
        self.retriever = DocumentRetriever.from_corpus(corpus)
        self.registry = default_registry()
        self.llm = llm or get_llm(self.cfg)

    # ---- pipeline stages -------------------------------------------------- #
    def _gather(self, plan: Plan) -> Evidence:
        ev = Evidence()
        reqs = tool_requests(plan)
        for ticker in plan.tickers or [None]:
            cik = self.factstore.resolve_cik(ticker=ticker) if ticker else None
            section = "Risk Factors" if plan.intent == "risks" else None
            k = 5 if plan.intent == "risks" else 3
            ev.hits += self.retriever.search(plan.raw_query, k=k, method="hybrid", cik=cik, section=section)
            if ticker:
                for tool_name, args in reqs:
                    ev.tool_calls.append(self.registry.dispatch(tool_name, {"ticker": ticker, **args}, self.factstore))
        return ev

    def _findings(self, plan: Plan, ev: Evidence) -> list[Claim]:
        findings: list[Claim] = []
        for tc in ev.tool_calls:
            if tc.error or not tc.citations:
                continue
            findings.append(Claim(
                statement=self._describe(tc),
                citations=tc.citations,
                supported=True,
                kind="calculation",
            ))
        # one qualitative claim per top document hit
        for h in ev.hits[:4]:
            sentence = " ".join(h.chunk.text.split())
            sentence = sentence[:220].rsplit(" ", 1)[0] + "..."
            findings.append(Claim(
                statement=f"{h.chunk.company} ({h.chunk.section}): {sentence}",
                citations=[hit_to_citation(h)],
                supported=True,
                kind="qualitative",
            ))
        return findings

    def _describe(self, tc: ToolCall) -> str:
        tk = tc.inputs.get("ticker", "")
        m = tc.inputs.get("metric", "")
        if tc.tool == "get_metric":
            return f"{tk} {m} was {_fmt(tc.output, tc.unit)} (latest reported)."
        if tc.tool == "growth_rate":
            return f"{tk} {m} changed {tc.output:+.1%} year over year."
        if tc.tool == "cagr":
            yrs = tc.inputs.get("years", "several")
            return f"{tk} {m} compounded at {tc.output:.1%}/yr over ~{yrs} years."
        if tc.tool == "margin":
            return f"{tk} {m} margin was {tc.output:.1%}."
        if tc.tool == "ratio":
            return f"{tk} {tc.inputs.get('numerator')}/{tc.inputs.get('denominator')} was {tc.output:.2f}."
        if tc.tool == "compare_scenarios":
            out = tc.output or {}
            hy = out.get("horizon_year")
            parts = ", ".join(f"{s['name']} {_fmt(s['final_value'], tc.unit)}" for s in out.get("scenarios", []))
            return f"{tk} {m} scenarios to FY{hy}: {parts}."
        return f"{tk} {tc.tool} = {tc.output}"

    def _assumptions(self, plan: Plan, ev: Evidence) -> list[Assumption]:
        assumptions: list[Assumption] = []
        for tc in ev.tool_calls:
            if tc.tool == "compare_scenarios" and not tc.error:
                for s in (tc.output or {}).get("scenarios", []):
                    assumptions.append(Assumption(
                        text=f"{tc.inputs.get('ticker')} '{s['name']}' scenario assumes {s['growth_rate']:.0%} annual growth.",
                        basis="analyst-provided scenario input (not a forecast)",
                        citations=tc.citations,
                    ))
        return assumptions

    def _template_answer(self, plan: Plan, ev: Evidence, findings: list[Claim]) -> str:
        good = [tc for tc in ev.tool_calls if not tc.error]
        calc_stmts = [f.statement for f in findings if f.kind == "calculation"]
        qual_stmts = [f.statement for f in findings if f.kind == "qualitative"]

        if plan.intent == "compare" and plan.tickers:
            metric = plan.metrics[0]
            lines, cagrs = [], {}
            for tk in plan.tickers:
                gm = self._first(good, tk, "get_metric", metric)
                gr = self._first(good, tk, "growth_rate", metric)
                cg = self._first(good, tk, "cagr", metric)
                bits = []
                if gm:
                    bits.append(_fmt(gm.output, gm.unit))
                if gr:
                    bits.append(f"{gr.output:+.1%} YoY")
                if cg:
                    bits.append(f"{cg.output:.1%} 4y CAGR")
                    cagrs[tk] = cg.output
                lines.append(f"{tk} {metric}: " + ", ".join(bits))
            answer = "Based on SEC filings:\n- " + "\n- ".join(lines)
            if len(cagrs) >= 2:
                fastest = max(cagrs, key=cagrs.get)
                answer += f"\n\n{fastest} shows the faster {metric} growth ({cagrs[fastest]:.1%} CAGR)."
            return answer

        if plan.intent == "risks":
            lines = qual_stmts[:4] or calc_stmts[:3]
            if not lines:
                return "No risk disclosures were retrieved from approved filings."
            return "Key risk disclosures from the latest 10-K (Risk Factors):\n- " + "\n- ".join(lines)

        if plan.intent == "scenario":
            if calc_stmts:
                return ("Scenario projections (illustrative, not forecasts):\n- "
                        + "\n- ".join(calc_stmts[:4]))
            return "No base figure was available to project from."

        # growth / metric / overview
        lines = calc_stmts[:6] or qual_stmts[:4]
        if not lines:
            return "No SEC-sourced evidence was found for this question."
        return "Based on SEC filings:\n- " + "\n- ".join(lines)

    @staticmethod
    def _first(tool_calls, ticker, tool, metric):
        for tc in tool_calls:
            if tc.tool == tool and tc.inputs.get("ticker") == ticker and tc.inputs.get("metric") == metric:
                return tc
        return None

    # ---- public API ------------------------------------------------------- #
    def answer(self, query: str, access: Optional[AccessContext] = None) -> AnalysisResult:
        t0 = time.perf_counter()
        trace: list[str] = []

        plan = plan_query(query, self.corpus.companies)
        trace.append(f"plan: {plan}")

        model, tier = select_model(plan, self.cfg)
        trace.append(f"router: {model} ({tier})")

        ev = self._gather(plan)
        trace.append(f"evidence: {len(ev.hits)} doc hits, "
                     f"{len([t for t in ev.tool_calls if not t.error])}/{len(ev.tool_calls)} tools ok")

        findings = self._findings(plan, ev)
        assumptions = self._assumptions(plan, ev)
        answer_text = self._template_answer(plan, ev, findings)

        result = AnalysisResult(
            query_id=uuid.uuid4().hex[:12],
            query=query,
            answer=answer_text,
            findings=findings,
            calculations=[tc for tc in ev.tool_calls if not tc.error],
            assumptions=assumptions,
            reasoning_trace=trace,
        )

        # Optional LLM narration (Claude when available; mock -> keep template).
        if self.llm.backend == "anthropic":
            block = prompts.build_evidence_block(result.calculations, ev.hits)
            res = self.llm.generate(
                prompts.SYSTEM_PROMPT,
                prompts.build_composition_prompt(query, block),
                model=model,
            )
            if res.text.strip():
                result.answer = res.text.strip()
            result.usage = res.usage
            trace.append(f"llm: {res.backend} ({res.usage.input_tokens}->{res.usage.output_tokens} tok)")
        else:
            trace.append("llm: mock (templated answer)")

        result = guardrails.verify(result, plan, self.cfg)
        result.model_used = model if self.llm.backend == "anthropic" else "mock"
        result.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        result.reasoning_trace = trace
        return result

    def resolve_approval(self, result: AnalysisResult, decision: str, approver: str, reason: str = "") -> AnalysisResult:
        """Human-in-the-loop resolution of a pending approval."""
        status = ApprovalStatus.APPROVED if decision == "approve" else ApprovalStatus.REJECTED
        result.approval = ApprovalDecision(
            status=status, approver=approver, reason=reason or result.approval.reason,
            decided_at=datetime.now(timezone.utc),
        )
        if status == ApprovalStatus.REJECTED:
            result.answer = "[Withheld pending human review] " + result.answer
        return result

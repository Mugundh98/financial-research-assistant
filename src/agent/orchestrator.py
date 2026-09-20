"""The agent: plan -> retrieve -> compute -> compose -> verify -> approve.

Deterministic evidence-gathering (retrieval + cited tools) is the backbone, so
every figure is sourced and reproducible. The LLM only writes the narrative
(with a mock fallback that yields a templated answer). Guardrails then verify
the result. The single return type is always :class:`AnalysisResult`.
"""
from __future__ import annotations

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
    Role,
    ToolCall,
)
from ..ingestion import SECClient, TickerResolver, extract_candidate_tickers, fetch_company
from ..ingestion.corpus import Corpus
from ..observability import AuditLogger, CostMeter, Stopwatch
from ..retrieval import DocumentRetriever, FactStore, chunk_corpus, hit_to_citation
from ..security import can, filter_approved, redact, required_capability
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
    def __init__(self, corpus: Corpus, cfg: Optional[Settings] = None, llm: Optional[BaseLLM] = None,
                 audit: Optional[AuditLogger] = None, cost_meter: Optional[CostMeter] = None):
        self.cfg = cfg or default_settings
        self.corpus = corpus
        # Approved-only enforcement: unapproved records never enter the indexes.
        approved_facts = filter_approved(corpus.facts)
        approved_docs = filter_approved(corpus.documents)
        self.factstore = FactStore(approved_facts, corpus.companies)
        self.retriever = DocumentRetriever().build(chunk_corpus(approved_docs))
        self.registry = default_registry()
        self.llm = llm or get_llm(self.cfg)
        self.audit = audit if audit is not None else AuditLogger()
        self.cost = cost_meter if cost_meter is not None else CostMeter()
        self._client: Optional[SECClient] = None       # lazy (network) for on-demand ingest
        self._resolver: Optional[TickerResolver] = None

    # ---- on-demand SEC coverage ------------------------------------------ #
    def _sec(self) -> SECClient:
        if self._client is None:
            self._client = SECClient()
        return self._client

    def _resolver_obj(self) -> TickerResolver:
        if self._resolver is None:
            self._resolver = TickerResolver(self._sec())
        return self._resolver

    def _has_unknown_candidate(self, query: str) -> bool:
        """Offline check: does the query mention a ticker/alias not in the corpus?"""
        known = {c.ticker.upper() for c in self.corpus.companies if c.ticker}
        return bool(extract_candidate_tickers(query) - known)

    def _rebuild_indexes(self) -> None:
        self.factstore = FactStore(filter_approved(self.corpus.facts), self.corpus.companies)
        self.retriever = DocumentRetriever().build(chunk_corpus(filter_approved(self.corpus.documents)))

    def _try_dynamic_ingest(self, query: str, access: AccessContext, qid: str) -> list[str]:
        """Resolve unknown tickers via SEC and ingest them live. Returns new tickers."""
        try:
            matches = self._resolver_obj().resolve(query)
        except Exception as e:  # noqa: BLE001 - offline / network issue -> no ingest
            self.audit.log("dynamic_resolve_failed", query_id=qid, error=str(e))
            return []
        existing = {c.cik for c in self.corpus.companies}
        ingested: list[str] = []
        for cik, ticker in matches[:3]:
            if cik in existing:
                continue
            try:
                company, facts, docs = fetch_company(self._sec(), cik)
                self.corpus.companies.append(company)
                self.corpus.facts.extend(facts)
                self.corpus.documents.extend(docs)
                existing.add(cik)
                ingested.append(ticker)
                self.audit.log("dynamic_ingest", query_id=qid, user_id=access.user_id,
                               role=access.role.value, ticker=ticker, cik=cik,
                               facts=len(facts), documents=len(docs))
            except Exception as e:  # noqa: BLE001
                self.audit.log("dynamic_ingest_failed", query_id=qid, ticker=ticker, error=str(e))
        if ingested:
            self._rebuild_indexes()
        return ingested

    _NUMERIC_INTENTS = {"metric", "growth", "margin", "compare", "scenario"}

    def _fallback_or_refuse(self, plan: Plan, query: str, access: AccessContext,
                            qid: str, sw: Stopwatch, trace: list[str]) -> AnalysisResult:
        """No covered company/evidence: a labeled LLM general-knowledge answer for
        qualitative questions (real backend only), otherwise a clean refusal.
        Numeric/advice questions are never answered from model memory."""
        covered = ", ".join(c.ticker for c in self.corpus.companies if c.ticker)
        can_fallback = (
            self.llm.is_real
            and not plan.is_advice
            and plan.intent not in self._NUMERIC_INTENTS
        )
        if can_fallback:
            model = self.llm.model_for_tier(select_model(plan, self.cfg))
            try:
                res = self.llm.generate(prompts.FALLBACK_SYSTEM_PROMPT,
                                        prompts.build_fallback_prompt(query), model=model)
            except Exception as e:  # noqa: BLE001 - provider error -> fall through to refusal
                self.audit.log("llm_error", query_id=qid, backend=self.llm.backend, error=str(e))
                res = None
            if res is not None:
                answer, _ = redact((res.text or "").strip() or "I don't have enough information to answer that.")
                result = AnalysisResult(
                    query_id=qid, query=query, answer=answer, findings=[], calculations=[],
                    confidence=0.2, requires_human_approval=True,
                    approval=ApprovalDecision(status=ApprovalStatus.PENDING,
                                              reason="Unverified general-knowledge answer; human review required."),
                    disclaimers=[guardrails.RESEARCH_DISCLAIMER, guardrails.UNVERIFIED_DISCLAIMER],
                    caveats=["Answer is from the model's general knowledge, not SEC filings, and is unverified."],
                    model_used=model, usage=res.usage,
                    reasoning_trace=trace + ["llm-fallback: general knowledge (unverified)"],
                )
                self.cost.record(result.usage)
                result.latency_ms = sw.total()
                self.audit.log("llm_fallback", query_id=qid, user_id=access.user_id,
                               role=access.role.value, intent=plan.intent)
                return result

        self.audit.log("refused_scope", query_id=qid, user_id=access.user_id, role=access.role.value)
        result = AnalysisResult(
            query_id=qid, query=query, refused=True,
            refusal_reason="No approved SEC data covers this question.",
            answer=(f"I can only answer from approved SEC data and couldn't find any for this. "
                    f"Try a ticker symbol (e.g. AMZN) so I can fetch its filings, "
                    f"or set ANTHROPIC_API_KEY for labeled general-knowledge answers. "
                    f"Preloaded: {covered}."),
            disclaimers=[guardrails.RESEARCH_DISCLAIMER],
            reasoning_trace=trace + ["scope: refused (no data)"],
        )
        result.latency_ms = sw.total()
        return result

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
        access = access or AccessContext(role=Role(self.cfg.default_role))
        sw = Stopwatch()
        qid = uuid.uuid4().hex[:12]
        trace: list[str] = []
        self.audit.log("query_received", query_id=qid, user_id=access.user_id, role=access.role.value, query=query)

        plan = plan_query(query, self.corpus.companies)
        trace.append(f"plan: {plan}")
        sw.lap("plan")

        # On-demand coverage: fetch any unknown-but-real SEC company, then re-plan.
        if self._has_unknown_candidate(query):
            added = self._try_dynamic_ingest(query, access, qid)
            if added:
                plan = plan_query(query, self.corpus.companies)
                trace.append(f"dynamic ingest: {added}")
            sw.lap("dynamic_ingest")

        # Scope guard: no covered company -> labeled LLM fallback or refuse.
        if not plan.tickers:
            return self._fallback_or_refuse(plan, query, access, qid, sw, trace)

        # Access control: refuse capabilities the caller's role lacks.
        cap = required_capability(plan.intent)
        if not can(access.role, cap):
            self.audit.log("access_denied", query_id=qid, user_id=access.user_id,
                           role=access.role.value, capability=cap, intent=plan.intent)
            denied = AnalysisResult(
                query_id=qid, query=query, refused=True,
                refusal_reason=f"Role '{access.role.value}' is not permitted to run '{plan.intent}' (needs '{cap}').",
                answer=f"Access denied: this request needs the '{cap}' capability, which the '{access.role.value}' role lacks.",
                disclaimers=[guardrails.RESEARCH_DISCLAIMER],
                reasoning_trace=trace + [f"access: denied ({cap})"],
            )
            denied.latency_ms = sw.total()
            return denied

        tier = select_model(plan, self.cfg)
        model = self.llm.model_for_tier(tier)
        trace.append(f"router: {tier} -> {model}")

        ev = self._gather(plan)
        trace.append(f"evidence: {len(ev.hits)} doc hits, "
                     f"{len([t for t in ev.tool_calls if not t.error])}/{len(ev.tool_calls)} tools ok")
        self.audit.log("evidence_gathered", query_id=qid, user_id=access.user_id, role=access.role.value,
                       doc_hits=len(ev.hits), tools=[t.tool for t in ev.tool_calls],
                       tools_ok=len([t for t in ev.tool_calls if not t.error]))
        sw.lap("gather")

        findings = self._findings(plan, ev)
        assumptions = self._assumptions(plan, ev)
        answer_text = self._template_answer(plan, ev, findings)

        result = AnalysisResult(
            query_id=qid,
            query=query,
            answer=answer_text,
            findings=findings,
            calculations=[tc for tc in ev.tool_calls if not tc.error],
            assumptions=assumptions,
            reasoning_trace=trace,
        )

        # Optional LLM narration (any real backend writes prose; mock -> template).
        if self.llm.is_real:
            try:
                block = prompts.build_evidence_block(result.calculations, ev.hits)
                res = self.llm.generate(
                    prompts.SYSTEM_PROMPT,
                    prompts.build_composition_prompt(query, block),
                    model=model,
                )
                if res.text.strip():
                    result.answer = res.text.strip()
                result.usage = res.usage
                trace.append(f"llm: {res.backend} {res.model} "
                             f"({res.usage.input_tokens}->{res.usage.output_tokens} tok, ${res.usage.cost_usd:.4f})")
            except Exception as e:  # noqa: BLE001 - degrade to the deterministic template
                self.audit.log("llm_error", query_id=qid, backend=self.llm.backend, error=str(e))
                trace.append(f"llm error ({self.llm.backend}): {e}; used template")
        else:
            trace.append("llm: mock (templated answer)")
        sw.lap("compose")

        result = guardrails.verify(result, plan, self.cfg)
        sw.lap("verify")

        # PII redaction on user-facing text.
        redactions = 0
        result.answer, n = redact(result.answer)
        redactions += n
        for claim in result.findings:
            claim.statement, n = redact(claim.statement)
            redactions += n
        if redactions:
            result.caveats.append(f"{redactions} potential PII value(s) were redacted.")

        # Token economics.
        self.cost.record(result.usage)

        result.model_used = model if self.llm.is_real else "mock"
        result.latency_ms = sw.total()
        trace.append(f"timing_ms: {sw.stages}")
        result.reasoning_trace = trace

        self.audit.log(
            "responded", query_id=qid, user_id=access.user_id, role=access.role.value,
            findings=len(result.findings), confidence=result.confidence,
            requires_approval=result.requires_human_approval, refused=result.refused,
            redactions=redactions, latency_ms=result.latency_ms,
            tokens={"in": result.usage.input_tokens, "out": result.usage.output_tokens},
            cost_usd=result.usage.cost_usd,
        )
        return result

    def resolve_approval(self, result: AnalysisResult, decision: str, approver: str,
                         access: Optional[AccessContext] = None, reason: str = "") -> AnalysisResult:
        """Human-in-the-loop resolution of a pending approval (admin-only)."""
        if access is not None and not can(access.role, "approve"):
            self.audit.log("approval_denied", query_id=result.query_id,
                           user_id=access.user_id, role=access.role.value)
            result.caveats.append(f"Approval attempt by '{access.role.value}' denied (requires admin).")
            return result
        status = ApprovalStatus.APPROVED if decision == "approve" else ApprovalStatus.REJECTED
        result.approval = ApprovalDecision(
            status=status, approver=approver, reason=reason or result.approval.reason,
            decided_at=datetime.now(timezone.utc),
        )
        if status == ApprovalStatus.REJECTED:
            result.answer = "[Withheld pending human review] " + result.answer
        self.audit.log("approval_resolved", query_id=result.query_id,
                       user_id=(access.user_id if access else approver),
                       role=(access.role.value if access else "admin"),
                       status=status.value, approver=approver)
        return result

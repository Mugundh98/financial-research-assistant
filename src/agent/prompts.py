"""Prompt & context engineering.

The system prompt encodes the safety contract; the composition prompt hands the
model the already-gathered, already-computed evidence and asks only for prose.
Numbers are never delegated to the model, which is the core defense against
unsupported financial conclusions.
"""
from __future__ import annotations

from ..contracts.models import RetrievalHit, ToolCall

SYSTEM_PROMPT = """You are a financial-research and decision-intelligence assistant for professional analysts.

Rules you must follow:
1. Use ONLY the evidence provided below (reported financial facts, pre-computed calculations, and filing excerpts). Never introduce a number or claim that is not in the evidence.
2. The calculations were computed deterministically and are correct — restate them, never recompute or round away meaning.
3. Do NOT provide personalized investment advice or buy/sell/hold recommendations. You may present sourced facts, comparisons, and clearly-labelled scenarios.
4. Attribute claims to their source and note when the underlying data is not recent.
5. If the evidence does not support an answer, say so plainly rather than speculating.
Be concise, precise, and neutral."""


def _fmt_value(value, unit) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if unit in ("USD", "currency"):
        if abs(v) >= 1e9:
            return f"${v / 1e9:,.1f}B"
        if abs(v) >= 1e6:
            return f"${v / 1e6:,.1f}M"
        return f"${v:,.0f}"
    if unit == "ratio":
        return f"{v:.1%}"
    return f"{v:,.2f}"


def render_toolcall(tc: ToolCall) -> str:
    if tc.error:
        return f"- [calc:{tc.tool}] unavailable ({tc.error})"
    ticker = tc.inputs.get("ticker", "")
    metric = tc.inputs.get("metric", "")
    return f"- [calc:{tc.tool}] {ticker} {metric}: {_fmt_value(tc.output, tc.unit)}  (formula: {tc.formula})"


def render_hit(hit: RetrievalHit) -> str:
    text = " ".join(hit.chunk.text.split())[:280]
    return f"- [doc:{hit.chunk.company}/{hit.chunk.section}] {text}..."


def build_evidence_block(tool_calls: list[ToolCall], hits: list[RetrievalHit]) -> str:
    lines: list[str] = []
    if tool_calls:
        lines.append("Computed figures (deterministic, sourced):")
        lines += [render_toolcall(tc) for tc in tool_calls]
    if hits:
        lines.append("\nFiling excerpts:")
        lines += [render_hit(h) for h in hits]
    return "\n".join(lines) if lines else "(no evidence found)"


FALLBACK_SYSTEM_PROMPT = """You are a financial-research assistant answering a GENERAL question for which no approved SEC filing data is available.

Rules:
- Answer only in general, educational terms.
- Do NOT state specific financial figures, prices, valuations, or estimates for any company.
- Do NOT give investment advice or buy/sell/hold recommendations.
- If the question needs company-specific financial data you do not have, say so plainly.
Keep it brief and clearly hedged."""


def build_fallback_prompt(query: str) -> str:
    return (
        f"Question: {query}\n\n"
        "Answer in general terms only — no specific company figures, no advice. "
        "If it requires data you don't have, say so."
    )


def build_composition_prompt(query: str, evidence_block: str) -> str:
    return (
        f"Question:\n{query}\n\n"
        f"Evidence:\n{evidence_block}\n\n"
        "Write a concise, sourced answer (3-6 sentences) for an analyst. "
        "Reference the companies and figures from the evidence. "
        "Do not invent numbers and do not give investment advice."
    )

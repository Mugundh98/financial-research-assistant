"""Streamlit dashboard for the Financial-Research & Decision-Intelligence agent.

Runs the agent in-process (no API server needed) and surfaces everything the
guardrails produce: the sourced answer, cited findings, deterministic
calculations, assumptions, freshness/confidence, the human-approval gate, a
provenance table, and the reasoning trace (explainability).

Run: streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent import Agent  # noqa: E402
from src.agent.prompts import _fmt_value  # noqa: E402
from src.contracts.models import AccessContext, ApprovalStatus, Role  # noqa: E402
from src.ingestion.corpus import Corpus  # noqa: E402
from src.provenance import build_provenance  # noqa: E402

st.set_page_config(page_title="Financial Research Assistant", page_icon="📊", layout="wide")

EXAMPLES = [
    "How fast is NVIDIA's revenue growing, and how does it compare to Microsoft?",
    "What are the main risks facing NVIDIA?",
    "What is Apple's net margin?",
    "Project Microsoft revenue over the next 3 years.",
    "Should I buy Apple stock?",
]


@st.cache_resource(show_spinner="Loading agent + corpus…")
def get_agent() -> Agent:
    return Agent(Corpus.load())


def fmt_output(value, unit) -> str:
    if isinstance(value, dict):
        if "scenarios" in value:
            return " · ".join(f"{s['name']}: {_fmt_value(s['final_value'], unit)}" for s in value["scenarios"])
        return "—"
    return _fmt_value(value, unit)


agent = get_agent()

# ---- sidebar ------------------------------------------------------------- #
with st.sidebar:
    st.header("📊 Research Assistant")
    st.caption("Approved SEC-sourced financial analysis")
    role = st.selectbox("Role", ["analyst", "viewer", "admin"], help="Access level for this request")
    st.divider()
    st.subheader("Try an example")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True):
            st.session_state["query"] = ex
    st.divider()
    cost = agent.cost.summary()
    st.metric("Session queries", cost["queries"])
    st.metric("Session cost (USD)", f"${cost['cost_usd']:.4f}")
    st.caption(f"LLM backend: `{agent.llm.backend}`")

# ---- main ---------------------------------------------------------------- #
st.title("Financial-Research & Decision-Intelligence")

query = st.text_input(
    "Ask about AAPL, MSFT, or NVDA",
    value=st.session_state.get("query", ""),
    placeholder="e.g. How fast is NVIDIA's revenue growing vs Microsoft?",
)
run = st.button("Run analysis", type="primary")

if run and query.strip():
    access = AccessContext(user_id=f"dashboard-{role}", role=Role(role))
    with st.spinner("Analyzing…"):
        st.session_state["result"] = agent.answer(query, access=access).model_copy(deep=True)
        st.session_state["access_role"] = role

result = st.session_state.get("result")
if result:
    if result.refused:
        st.warning(f"**Refused:** {result.refusal_reason}\n\n{result.answer}")
    else:
        # top metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Confidence", f"{result.confidence:.0%}")
        c2.metric("Latency", f"{result.latency_ms:.0f} ms")
        c3.metric("Model", result.model_used or "—")
        fresh = result.freshness
        c4.metric("Freshest source", str(fresh.newest_as_of or "—"),
                  delta="stale" if fresh.is_stale else "current",
                  delta_color="inverse" if fresh.is_stale else "normal")

        st.subheader("Answer")
        st.markdown(result.answer)

        # human approval gate
        if result.requires_human_approval and result.approval.status == ApprovalStatus.PENDING:
            st.warning(f"⏳ **Human approval required** — {result.approval.reason}")
            a1, a2, _ = st.columns([1, 1, 3])
            if a1.button("✅ Approve", use_container_width=True):
                acc = AccessContext(user_id=f"dashboard-{st.session_state['access_role']}",
                                    role=Role(st.session_state["access_role"]))
                agent.resolve_approval(result, "approve", approver=acc.user_id, access=acc)
                st.rerun()
            if a2.button("❌ Reject", use_container_width=True):
                acc = AccessContext(user_id=f"dashboard-{st.session_state['access_role']}",
                                    role=Role(st.session_state["access_role"]))
                agent.resolve_approval(result, "reject", approver=acc.user_id, access=acc)
                st.rerun()
        elif result.approval.status != ApprovalStatus.NOT_REQUIRED:
            st.info(f"Approval: **{result.approval.status.value}**"
                    + (f" by {result.approval.approver}" if result.approval.approver else ""))

        # findings
        if result.findings:
            st.subheader("Findings")
            for f in result.findings:
                links = " · ".join(
                    f"[{c.source_type.value}{(' ' + str(c.as_of)) if c.as_of else ''}]({c.source_url})"
                    for c in f.citations if c.source_url
                )
                st.markdown(f"- {f.statement}")
                if links:
                    st.caption("   ↳ " + links)

        # calculations
        if result.calculations:
            st.subheader("Calculations (deterministic)")
            st.dataframe(
                [{"tool": tc.tool, "ticker": tc.inputs.get("ticker", ""),
                  "metric": tc.inputs.get("metric", ""),
                  "result": fmt_output(tc.output, tc.unit), "formula": tc.formula}
                 for tc in result.calculations],
                use_container_width=True, hide_index=True,
            )

        if result.assumptions:
            st.subheader("Assumptions")
            for a in result.assumptions:
                st.markdown(f"- {a.text}  \n  _{a.basis}_")

        # provenance
        with st.expander(f"🔎 Provenance ({len(result.citations)} sources)"):
            prov = build_provenance(result)
            st.write({k: prov[k] for k in ("source_count", "by_type", "as_of_oldest", "as_of_newest", "is_stale")})
            st.dataframe(prov["sources"], use_container_width=True, hide_index=True)

        # explainability
        with st.expander("🧠 Reasoning trace (explainability)"):
            for step in result.reasoning_trace:
                st.text(step)

    # disclaimers always
    for d in result.disclaimers:
        st.caption(f"⚠️ {d}")
    for cav in result.caveats:
        st.caption(f"• {cav}")

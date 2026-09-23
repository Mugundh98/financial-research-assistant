"""Streamlit dashboard for the Financial-Research & Decision-Intelligence agent.

Runs the agent in-process (no API server needed) and surfaces everything the
guardrails produce: the sourced answer, cited findings, deterministic
calculations, assumptions, freshness/confidence, the human-approval gate, a
provenance table, and the reasoning trace (explainability).

Sign-in (demo email login) gates the app so each user's queries and tickers are
persisted to a local SQLite profile that can be reviewed later.

Run: streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent import Agent, plan_query  # noqa: E402
from src.agent.prompts import _fmt_value  # noqa: E402
from src.contracts.models import AccessContext, ApprovalStatus, Role  # noqa: E402
from src.ingestion.corpus import Corpus  # noqa: E402
from src.provenance import build_provenance  # noqa: E402
from src.storage import AppDB  # noqa: E402

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


@st.cache_resource
def get_db() -> AppDB:
    return AppDB()


def fmt_output(value, unit) -> str:
    if isinstance(value, dict):
        if "scenarios" in value:
            return " · ".join(f"{s['name']}: {_fmt_value(s['final_value'], unit)}" for s in value["scenarios"])
        return "—"
    return _fmt_value(value, unit)


db = get_db()

# ---- login gate (demo email sign-in) ------------------------------------- #
if "user_email" not in st.session_state:
    st.title("📊 Financial-Research Assistant")
    st.caption("Sign in to continue — your queries and tickers are saved to your profile.")
    with st.form("login"):
        email = st.text_input("Email", placeholder="you@firm.com")
        name = st.text_input("Name (optional)")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        if email.strip():
            em = email.strip().lower()
            db.upsert_user(em, name.strip() or None)
            st.session_state["user_email"] = em
            st.session_state["user_name"] = name.strip() or em
            st.rerun()
        else:
            st.error("Please enter an email to sign in.")
    st.stop()

user_email = st.session_state["user_email"]
user_name = st.session_state.get("user_name", user_email)

agent = get_agent()

# ---- sidebar ------------------------------------------------------------- #
with st.sidebar:
    st.header("📊 Research Assistant")
    st.caption(f"Signed in as **{user_name}**")
    if st.button("Log out", use_container_width=True):
        for k in ("user_email", "user_name", "result", "access_role", "query"):
            st.session_state.pop(k, None)
        st.rerun()
    st.divider()
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
    "Ask about a US public company (by ticker or name)",
    value=st.session_state.get("query", ""),
    placeholder="e.g. How fast is NVIDIA's revenue growing vs Microsoft?",
)
run = st.button("Run analysis", type="primary")

if run and query.strip():
    access = AccessContext(user_id=user_email, role=Role(role))
    with st.spinner("Analyzing…"):
        result = agent.answer(query, access=access).model_copy(deep=True)
    st.session_state["result"] = result
    st.session_state["access_role"] = role
    # persist this query + the tickers it touched to the user's profile
    plan = plan_query(query, agent.corpus.companies)
    companies = {c.ticker: c.name for c in agent.corpus.companies if c.ticker}
    db.record_query(user_email, query=query, tickers=plan.tickers,
                    intent=plan.intent, result=result, companies=companies)

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
                acc = AccessContext(user_id=user_email, role=Role(st.session_state["access_role"]))
                agent.resolve_approval(result, "approve", approver=user_email, access=acc)
                st.rerun()
            if a2.button("❌ Reject", use_container_width=True):
                acc = AccessContext(user_id=user_email, role=Role(st.session_state["access_role"]))
                agent.resolve_approval(result, "reject", approver=user_email, access=acc)
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

# ---- per-user activity (from the local database) ------------------------- #
st.divider()
with st.expander("👤 My activity (saved to your profile)"):
    tickers = db.get_user_tickers(user_email)
    history = db.get_history(user_email, limit=20)
    if tickers:
        st.caption("**Tickers you've looked at**")
        st.dataframe(tickers, use_container_width=True, hide_index=True)
    if history:
        st.caption("**Recent queries**")
        st.dataframe(history, use_container_width=True, hide_index=True)
    if not tickers and not history:
        st.caption("No activity yet — run a query above.")

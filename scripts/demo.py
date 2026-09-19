"""Narrated end-to-end demo of the Financial-Research assistant.

Runs a curated sequence of queries that exercises retrieval, deterministic
calculations, citations, freshness, scenarios, governance (RBAC + human
approval), and safe-communication refusals.

    python -m scripts.demo
"""
from __future__ import annotations

from src.agent import Agent
from src.contracts.models import AccessContext, Role
from src.ingestion.corpus import Corpus
from src.provenance import build_provenance

_PUNCT = {0x2019: 0x27, 0x2018: 0x27, 0x201C: 0x22, 0x201D: 0x22,
          0x2013: 0x2D, 0x2014: 0x2D, 0x2026: 0x2E, 0x2022: 0x2D,
          0x00A0: 0x20, 0x2212: 0x2D}


def clean(s: str) -> str:
    return (s or "").translate(_PUNCT)


def rule(title: str = "") -> None:
    print("\n" + "=" * 74)
    if title:
        print(f"  {title}")
        print("=" * 74)


def show(r, n_findings: int = 2) -> None:
    print("  ANSWER:")
    for line in clean(r.answer).splitlines():
        print(f"    {line}")
    if r.calculations:
        print("  CALCULATIONS (deterministic, cited):")
        for tc in r.calculations[:3]:
            val = tc.output if not isinstance(tc.output, dict) else "scenarios"
            print(f"    - {tc.inputs.get('ticker','')} {tc.tool}: {val}  [{len(tc.citations)} cite]")
    cited = [f for f in r.findings if f.citations]
    if cited:
        c = cited[0].citations[0]
        print(f"  SAMPLE CITATION: {c.source_type.value} as_of={c.as_of} -> {c.source_url}")
    print(f"  GOVERNANCE: confidence={r.confidence:.0%} | fresh_newest={r.freshness.newest_as_of} "
          f"stale={r.freshness.is_stale} | approval={r.approval.status.value} "
          f"(required={r.requires_human_approval}) | refused={r.refused}")
    if r.disclaimers:
        print("  DISCLAIMERS: " + " | ".join(clean(d) for d in r.disclaimers))


def main() -> None:
    print("Loading agent + real SEC corpus (AAPL, MSFT, NVDA)...")
    agent = Agent(Corpus.load())
    analyst = AccessContext(user_id="analyst@firm.com", role=Role.ANALYST)
    viewer = AccessContext(user_id="viewer@firm.com", role=Role.VIEWER)
    admin = AccessContext(user_id="admin@firm.com", role=Role.ADMIN)
    print(f"LLM backend: {agent.llm.backend}  (set ANTHROPIC_API_KEY to use Claude)")

    rule("1. PEER COMPARISON  (retrieval + cited tools + synthesis)")
    q = "How fast is NVIDIA's revenue growing, and how does it compare to Microsoft?"
    print(f"Q ({analyst.role.value}): {q}")
    r = agent.answer(q, access=analyst)
    show(r)
    prov = build_provenance(r)
    print(f"  PROVENANCE: {prov['source_count']} sources {prov['by_type']} "
          f"as_of {prov['as_of_oldest']}..{prov['as_of_newest']}")

    rule("2. QUALITATIVE RISK  (unstructured retrieval, scoped + cited)")
    q = "What are the main risks facing NVIDIA?"
    print(f"Q ({analyst.role.value}): {q}")
    show(agent.answer(q, access=analyst))

    rule("3. PROFITABILITY  (margin from cited inputs)")
    q = "What is Apple's net margin?"
    print(f"Q ({analyst.role.value}): {q}")
    show(agent.answer(q, access=analyst))

    rule("4. SCENARIO + HUMAN APPROVAL  (RBAC + HITL)")
    q = "Project Microsoft revenue over the next 3 years."
    print(f"Q ({viewer.role.value}): {q}")
    rv = agent.answer(q, access=viewer)
    print(f"  -> viewer refused (access): {rv.refused} :: {clean(rv.answer)[:72]}")
    print(f"\nQ ({analyst.role.value}): {q}")
    ra = agent.answer(q, access=analyst)
    show(ra)
    print("  ...analyst tries to approve own answer:")
    agent.resolve_approval(ra, "approve", approver=analyst.user_id, access=analyst)
    print(f"    status={ra.approval.status.value} (analyst cannot approve)")
    print("  ...admin approves:")
    agent.resolve_approval(ra, "approve", approver=admin.user_id, access=admin)
    print(f"    status={ra.approval.status.value} by {ra.approval.approver}")

    rule("5. ADVICE  (refused as a recommendation; facts only)")
    q = "Should I buy Apple stock?"
    print(f"Q ({analyst.role.value}): {q}")
    show(agent.answer(q, access=analyst))

    rule("6. OUT OF SCOPE  (no covered company -> refuse, don't fabricate)")
    q = "What are Tesla's main risks?"
    print(f"Q ({analyst.role.value}): {q}")
    r = agent.answer(q, access=analyst)
    print(f"  refused={r.refused} :: {clean(r.answer)}")

    rule("SESSION TELEMETRY")
    print(f"  token/cost: {agent.cost.summary()}")
    print(f"  audit events logged this session: {len(agent.audit.events)}")
    print("\nDemo complete.")


if __name__ == "__main__":
    main()

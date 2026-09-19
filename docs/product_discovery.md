# Product Discovery

## Problem

Investment and corporate-finance professionals spend disproportionate time
**gathering** approved financial data and market context, **recomputing** the
same metrics, and **manually citing** sources before they can reason. General
LLM chatbots are unusable for this: they hallucinate figures, cannot show a
source, do arithmetic unreliably, and give advice they are not permitted to give.

The opportunity is an assistant that behaves like a **diligent junior analyst
under supervision**: it only uses approved records, lets deterministic tools do
the math, cites every number, flags stale data, and escalates anything that
looks like a recommendation to a human.

## Target users & personas

| Persona | Goal | Pain today |
|---|---|---|
| **Equity research analyst** | Pull reported figures, growth/margins, compare peers, draft with citations | Manual data pulls from filings; recomputing CAGR/margins; citation bookkeeping |
| **Portfolio manager** | Quick, sourced read on a name or comparison before a decision | Can't trust ungrounded summaries; needs provenance and freshness |
| **Corporate strategy / FP&A** | Benchmark against peers; simple forward scenarios | Spreadsheet sprawl; assumptions not documented |
| **Compliance / model risk** | Ensure no unsupported claims or advice reach clients | No audit trail; black-box tools; advice leakage |

## Jobs to be done

- "When I ask about a covered company, **give me the reported number with its
  source and as-of date**, not an estimate."
- "When I compare two companies, **compute growth/margins consistently** and show
  which is faster — with the math shown."
- "When I explore a forward scenario, **make the assumptions explicit** and label
  it as illustrative, not a forecast."
- "When I (or a user) ask for a recommendation, **don't give one** — route it to a
  human and surface only sourced facts."
- "Give me an **audit trail** and a **freshness signal** I can defend."

## Representative use cases (all handled today)

1. **Metric lookup** — "What was Apple's FY2024 revenue?" → cited value.
2. **Growth/trend** — "How fast is NVIDIA's revenue growing?" → YoY + CAGR, cited.
3. **Peer comparison** — "Compare NVIDIA and Microsoft revenue." → per-company
   figures + who is faster.
4. **Profitability** — "What is Apple's net margin?" → margin from cited inputs.
5. **Scenario** — "Project Microsoft revenue over 3 years." → labelled scenarios +
   assumptions + human-approval gate.
6. **Qualitative risk** — "What are NVIDIA's main risks?" → cited Risk-Factors text.
7. **Advice (correctly refused)** — "Should I buy Apple?" → sourced facts only,
   no recommendation, human sign-off required.

## Success metrics

| Dimension | Metric | Target (prototype) | Current |
|---|---|---|---|
| Numeric accuracy | reported values match filings | 100% | **11/11 checks** |
| Retrieval quality | hit@3 (correct company+section) | ≥ 0.80 | **0.857 (hybrid)** |
| Faithfulness | findings with a citation | 100% | **100%** |
| Safety | advice gated + disclaimed; out-of-scope refused | 100% | **8/8 checks** |
| Latency | p50 per query (mock LLM) | < 250 ms | **~50 ms** |
| Cost | $ per query (mock / cached) | ~$0 | **$0** |

## Scope

**In scope (prototype):** US public companies with SEC filings (demo corpus:
AAPL, MSFT, NVDA); reported financials + 10-K narrative; deterministic metrics;
sourced synthesis; governance (access, audit, approval).

**Out of scope / non-goals:** personalized investment advice; real-time market
data or intraday prices; trade execution; non-SEC/private data; tax or legal
advice; guaranteeing filings are error-free (we reflect what was filed).

## Assumptions & constraints

- SEC EDGAR is the authoritative "approved records" source; data is only as
  fresh as the latest filing (annual 10-K cadence in the prototype).
- The assistant advises **research**, never a buy/sell/hold decision.
- Every quantitative claim must be traceable to a source or it is dropped.

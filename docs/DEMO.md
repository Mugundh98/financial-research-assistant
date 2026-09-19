# Demo Walkthrough

A reproducible end-to-end demo of the assistant on **real SEC data** (AAPL, MSFT,
NVDA). It runs with **no API key** — the deterministic mock LLM composes the
prose, so figures, citations, and governance behave identically to a real-Claude
run. Regenerate this transcript any time with:

```bash
python -m scripts.demo
```

## What the demo shows

1. **Peer comparison** — retrieval + cited deterministic tools + synthesis
   ("NVIDIA vs Microsoft revenue"); every number carries a SEC citation.
2. **Qualitative risk** — unstructured retrieval scoped to NVDA's Risk Factors,
   cited to the 10-K.
3. **Profitability** — net margin computed from cited inputs.
4. **Scenario + human approval** — a `viewer` is denied (RBAC); an `analyst` gets
   an approval-gated projection; the analyst **cannot self-approve**; an `admin`
   approves (human-in-the-loop).
5. **Advice** — "Should I buy Apple?" returns **sourced facts only**, adds a
   no-recommendation disclaimer, and requires human sign-off.
6. **Out of scope** — a non-covered company (Tesla) is **refused, not fabricated**.
7. **Session telemetry** — token/cost economics and audit-event count.

## Transcript

```text
Loading agent + real SEC corpus (AAPL, MSFT, NVDA)...
LLM backend: mock  (set ANTHROPIC_API_KEY to use Claude)

==========================================================================
  1. PEER COMPARISON  (retrieval + cited tools + synthesis)
==========================================================================
Q (analyst): How fast is NVIDIA's revenue growing, and how does it compare to Microsoft?
  ANSWER:
    Based on SEC filings:
    - NVDA revenue: $215.9B, +65.5% YoY, 68.3% 4y CAGR
    - MSFT revenue: $331.8B, +17.8% YoY, 13.7% 4y CAGR
    
    NVDA shows the faster revenue growth (68.3% CAGR).
  CALCULATIONS (deterministic, cited):
    - NVDA get_metric: 215938000000.0  [1 cite]
    - NVDA growth_rate: 0.654735357900948  [2 cite]
    - NVDA cagr: 0.6830139148028267  [2 cite]
  SAMPLE CITATION: financial_fact as_of=2026-01-25 -> https://data.sec.gov/api/xbrl/companyconcept/CIK0001045810/us-gaap/Revenues.json
  GOVERNANCE: confidence=85% | fresh_newest=2026-06-30 stale=False | approval=not_required (required=False) | refused=False
  DISCLAIMERS: This is research assistance, not personalized investment advice.
  PROVENANCE: 10 sources {'financial_fact': 6, 'document': 4} as_of 2022-01-30..2026-06-30

==========================================================================
  2. QUALITATIVE RISK  (unstructured retrieval, scoped + cited)
==========================================================================
Q (analyst): What are the main risks facing NVIDIA?
  ANSWER:
    Key risk disclosures from the latest 10-K (Risk Factors):
    - NVIDIA CORP (Risk Factors): We entered into multi-year cloud service agreements to support our research and development activities. The timing and availability of these cloud services have changed and may continue to shift, impacting our revenue,...
    - NVIDIA CORP (Risk Factors): The following risk factors should be considered in addition to the other information in this Annual Report on Form 10-K. The following risks could harm our business, financial condition, results of operations or...
    - NVIDIA CORP (Risk Factors): Risks Related to Our Global Operating Business - Adverse economic conditions may harm our business. - International sales and operations are a significant part of our business, which exposes us to risks that could harm...
    - NVIDIA CORP (Risk Factors): These areas could damage our reputation, deter customers, affect product design, or result in legal or regulatory proceedings and liability. - Our operating results may be adversely impacted by additional tax...
  CALCULATIONS (deterministic, cited):
    - NVDA get_metric: 215938000000.0  [1 cite]
  SAMPLE CITATION: financial_fact as_of=2026-01-25 -> https://data.sec.gov/api/xbrl/companyconcept/CIK0001045810/us-gaap/Revenues.json
  GOVERNANCE: confidence=65% | fresh_newest=2026-01-25 stale=False | approval=not_required (required=False) | refused=False
  DISCLAIMERS: This is research assistance, not personalized investment advice.

==========================================================================
  3. PROFITABILITY  (margin from cited inputs)
==========================================================================
Q (analyst): What is Apple's net margin?
  ANSWER:
    Based on SEC filings:
    - AAPL net income margin was 26.9%.
  CALCULATIONS (deterministic, cited):
    - AAPL margin: 0.2691506412181824  [2 cite]
  SAMPLE CITATION: financial_fact as_of=2025-09-27 -> https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/NetIncomeLoss.json
  GOVERNANCE: confidence=65% | fresh_newest=2025-09-27 stale=False | approval=not_required (required=False) | refused=False
  DISCLAIMERS: This is research assistance, not personalized investment advice.

==========================================================================
  4. SCENARIO + HUMAN APPROVAL  (RBAC + HITL)
==========================================================================
Q (viewer): Project Microsoft revenue over the next 3 years.
  -> viewer refused (access): True :: Access denied: this request needs the 'scenario' capability, which the '

Q (analyst): Project Microsoft revenue over the next 3 years.
  ANSWER:
    Scenario projections (illustrative, not forecasts):
    - MSFT revenue scenarios to FY2029: conservative $384.1B, base $441.7B, bull $504.7B.
  CALCULATIONS (deterministic, cited):
    - MSFT compare_scenarios: scenarios  [1 cite]
  SAMPLE CITATION: financial_fact as_of=2026-06-30 -> https://data.sec.gov/api/xbrl/companyconcept/CIK0000789019/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json
  GOVERNANCE: confidence=65% | fresh_newest=2026-06-30 stale=False | approval=pending (required=True) | refused=False
  DISCLAIMERS: This is research assistance, not personalized investment advice.
  ...analyst tries to approve own answer:
    status=pending (analyst cannot approve)
  ...admin approves:
    status=approved by admin@firm.com

==========================================================================
  5. ADVICE  (refused as a recommendation; facts only)
==========================================================================
Q (analyst): Should I buy Apple stock?
  ANSWER:
    Based on SEC filings:
    - AAPL revenue was $416.2B (latest reported).
    - AAPL revenue changed +6.4% year over year.
    - AAPL revenue compounded at 3.3%/yr over ~4 years.
  CALCULATIONS (deterministic, cited):
    - AAPL get_metric: 416161000000.0  [1 cite]
    - AAPL growth_rate: 0.0642551178283274  [2 cite]
    - AAPL cagr: 0.03275991627577457  [2 cite]
  SAMPLE CITATION: financial_fact as_of=2025-09-27 -> https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json
  GOVERNANCE: confidence=85% | fresh_newest=2025-09-27 stale=False | approval=pending (required=True) | refused=False
  DISCLAIMERS: This is research assistance, not personalized investment advice. | The assistant does not make buy/sell/hold recommendations.

==========================================================================
  6. OUT OF SCOPE  (no covered company -> refuse, don't fabricate)
==========================================================================
Q (analyst): What are Tesla's main risks?
  refused=True :: I can only answer about covered companies (AAPL, MSFT, NVDA); none was identified in your question.

==========================================================================
  SESSION TELEMETRY
==========================================================================
  token/cost: {'queries': 5, 'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'cost_usd': 0.0}
  audit events logged this session: 21

Demo complete.
```

## Dashboard walkthrough

Launch the UI (same agent, in-process):

```bash
streamlit run dashboard/app.py     # http://localhost:8501
```

1. **Pick a role** in the sidebar (viewer / analyst / admin).
2. Click the example **"How fast is NVIDIA's revenue growing… compare to
   Microsoft?"**, then **Run analysis**. You'll see:
   - a metrics row — **confidence, latency, model, freshest-source** (with a
     current/stale badge);
   - the **answer**;
   - **Findings**, each with **clickable citation links** to the SEC source;
   - a **Calculations** table (tool, result, formula);
   - **Provenance** and **Reasoning trace** expanders (explainability).
3. Run **"Should I buy Apple stock?"** — an amber **"Human approval required"**
   banner appears with the no-recommendation disclaimer; as **admin** you get
   **Approve / Reject** buttons.
4. Switch the role to **viewer** and run **"Project Microsoft revenue…"** — the
   request is **access-denied** (scenarios need analyst+).

## Run it yourself

```bash
pip install -r requirements.txt
python -m scripts.ingest --tickers AAPL MSFT NVDA   # fetch + cache real SEC data
python -m scripts.demo                              # this walkthrough
python -m scripts.evaluate                          # 30-check scorecard
pytest                                              # 28 unit tests
```

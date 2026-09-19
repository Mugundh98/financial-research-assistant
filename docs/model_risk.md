# Model Risk & Governance

Framed against the spirit of **SR 11-7 / OCC model-risk guidance**: identify the
models, assess conceptual soundness, test implementation, analyze outcomes, and
monitor in use — with proportionate controls for a research prototype.

## 1. Intended use

A **decision-support research assistant** that retrieves approved SEC financial
records and filing narrative, performs deterministic calculations, compares
scenarios, and produces source-cited analysis for professional users. It is
**not** an advice engine, a trading system, or a system of record.

**Users:** analysts, PMs, corporate finance, with compliance oversight.
**Not for:** retail advice, automated trading, or unreviewed client-facing output.

## 2. Model inventory & risk tiering

| Component | Type | What it does | Hallucination risk | Tier |
|---|---|---|---|---|
| Deterministic calculators (`tools/`) | Rule-based | All arithmetic (growth, CAGR, margin, NPV, IRR, scenarios) | **None** (pure Python) | Low |
| Structured retrieval (`FactStore`) | Deterministic lookup | Exact reported figures from XBRL | None | Low |
| Vector/BM25/hybrid retrieval | ML (LSA/BM25) | Rank filing passages | Low (returns real text) | Medium |
| LLM narrator (Claude / mock) | Generative | Writes prose **only**, from supplied evidence | Contained (no numbers, guardrailed) | Medium |
| Guardrails (`guardrails.py`) | Rule-based | Drop uncited claims, freshness, safe-comms, approval | Reduces risk | Control |

**Key design control:** the generative model never computes or sources numbers —
those come from deterministic tools and structured lookups. This removes the
highest-severity failure mode (fabricated financials) by construction.

## 3. Conceptual soundness

- **Separation of concerns:** deterministic backbone (retrieve + compute) +
  generative narration + rule-based verification. Numbers are reproducible.
- **Provenance-first:** every fact/chunk carries `source_url`, `accession`,
  `as_of`; every claim must cite or it is removed.
- **Fiscal-period correctness:** fiscal year is derived from the reporting period
  end (not SEC's filing-year field), and periods are classified by duration —
  preventing comparative-year mislabeling.

## 4. Limitations

- **Coverage:** prototype corpus is AAPL/MSFT/NVDA, 10-K only. Out-of-scope
  companies are refused, not guessed.
- **Freshness:** annual-filing cadence; intra-year (10-Q) data is not ingested,
  so "latest" can be up to ~1 year old (surfaced via the freshness signal).
- **Section extraction** is heuristic; narrative snippets may occasionally start
  mid-context (does not affect cited figures).
- **Scenario projections** are mechanical (constant-growth), explicitly labelled
  illustrative, and gated for human approval — not forecasts.
- **Retrieval** uses LSA/BM25 by default (upgradeable to neural embeddings);
  semantic recall is good but not state-of-the-art.

## 5. Failure modes & mitigations

| Failure mode | Mitigation |
|---|---|
| Fabricated figure | LLM never emits numbers; all figures from tools/FactStore |
| Unsupported claim | Guardrail drops any finding without a citation |
| Stale data presented as current | Freshness computed + `is_stale` surfaced; caveat added |
| Advice / recommendation leakage | Advice detected → no-rec disclaimer + human-approval gate |
| Out-of-scope / irrelevant question | Scope guard refuses (no covered company) |
| Prompt injection via filing text | Retrieved text is data, not instructions; LLM output is prose-only and re-verified by guardrails; numbers unaffected |
| PII exposure | Regex redaction of emails/SSNs/cards/phones on output |
| Unauthorized action | Role-based access; approvals are admin-only |
| Silent errors | Append-only audit log of every stage |

## 6. Outcomes analysis (evaluation)

Evaluated by `scripts/evaluate.py` (see `evals/report.json`):

- **Numeric accuracy:** 11/11 — math identities + reported values vs public
  ground truth + tool-vs-manual consistency.
- **Retrieval:** hybrid hit@3 = 0.857 (> vector 0.714, BM25 0.571).
- **Generation faithfulness:** 9/9 — 100% citation coverage; tool outputs
  re-derive exactly from the FactStore.
- **Safe communication:** 8/8 — advice gated + disclaimed, scenarios gated,
  out-of-scope/irrelevant refused, research disclaimer always present.

Plus a 28-case `pytest` suite over calculations, contracts, planning, the fact
store, and guardrails.

## 7. Ongoing monitoring & oversight

- **Audit log** (`audit_logs/*.jsonl`): query, plan, evidence, decisions,
  approvals — reconstructable per `query_id`.
- **Token/cost + latency** metered per query and per session.
- **Human-in-the-loop:** low-confidence, forward-looking, or advice-adjacent
  answers require admin approval before they are considered final.
- **Re-run evals** on any change to ingestion, retrieval, tools, or prompts.

## 8. Assumptions & disclaimers

- Reflects data **as filed** with the SEC; does not independently audit issuers.
- **Not investment advice**; no buy/sell/hold recommendations; not a fiduciary.
- Approximate LLM pricing is used for cost estimates; the mock backend is $0.

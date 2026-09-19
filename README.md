# Financial-Research & Decision-Intelligence Assistant

An agent that retrieves **approved** financial records and market research (from
SEC EDGAR), performs **tool-assisted** deterministic calculations, compares
scenarios, explains its assumptions, produces **source-cited** analysis, and
**refuses to state conclusions it cannot support** — shipped with an evaluation
suite for numeric accuracy, freshness, source provenance, and safe communication.

> Built as an engineering assignment. Data source is **real** (SEC EDGAR, no API
> key). The LLM layer defaults to **Anthropic Claude** but automatically falls
> back to a deterministic **mock** model when no key is present, so the whole
> pipeline and all evaluations run with zero secrets.

> **Reviewers:** start with [SUBMISSION.md](SUBMISSION.md) (summary + rubric map)
> and [docs/DEMO.md](docs/DEMO.md) (end-to-end walkthrough).

## Rubric coverage

| # | Capability | Where it lives | Depth |
|---|---|---|---|
| 1 | AI for financial services | Whole system; `docs/product_discovery.md` | core |
| 2 | Product discovery | `docs/product_discovery.md` | doc |
| 3 | Retrieval over structured **and** unstructured data | `src/retrieval/` (facts + documents) | core |
| 4 | Data contracts | `src/contracts/`, enforced in `src/ingestion/normalize.py` | core |
| 5 | Vector **and** hybrid search | `src/retrieval/{vector,keyword,hybrid}.py` | core |
| 6 | Knowledge graphs | `src/retrieval/graph.py` (networkx) | lighter |
| 7 | Tool/function calling for deterministic calcs | `src/tools/` | core |
| 8 | Structured outputs | `AnalysisResult` contract | core |
| 9 | Agent orchestration | `src/agent/orchestrator.py` | core |
| 10 | Model & capability selection | `src/agent/router.py` | lighter |
| 11 | Prompt & context engineering | `src/agent/prompts.py` | core |
| 12 | Source provenance | `Citation` on every claim; `src/provenance/` | core |
| 13 | Temporal freshness | `as_of` stamps + `src/provenance/freshness.py` | core |
| 14 | Numeric evaluation | `src/eval/numeric.py` | core |
| 15 | Retrieval & generation evaluation | `src/eval/{retrieval,generation}.py` | core |
| 16 | Model risk | `docs/model_risk.md` | doc |
| 17 | Explainability | `reasoning_trace` + dashboard trace view | core |
| 18 | Security & access controls | `src/security/` (approved-only, roles, PII) | core |
| 19 | Audit logs | `src/observability/audit.py` | core |
| 20 | Token economics | `src/observability/tokens.py` | lighter |
| 21 | Latency/cost trade-offs | `src/observability/` + `docs/model_risk.md` | lighter |
| 22 | API & dashboard deployment | `src/api/` (FastAPI) + `dashboard/` (Streamlit) | core |
| 23 | Human approval | Approval gate in orchestrator + dashboard | core |

## Architecture

```
Query ─▶ Security/Access ─▶ Orchestrator ─▶ Retrieval (structured + vector/hybrid + graph)
                                   │
                                   ├─▶ Deterministic tools (calcs, scenarios)
                                   ├─▶ LLM (router: fast/strong or mock) — drafts, never computes
                                   ├─▶ Guardrails (citations required, freshness, safe comms)
                                   └─▶ Human-approval gate ─▶ AnalysisResult (structured, cited)
Cross-cutting: provenance · freshness · audit logs · token/latency accounting · explainability
```

## Quickstart

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # optional; set ANTHROPIC_API_KEY + SEC_USER_AGENT contact
```

Commands land as phases are implemented (see **Build status**):

```bash
python -m scripts.ingest --tickers AAPL MSFT NVDA   # fetch + validate real SEC data
python -m scripts.evaluate                          # evaluation scorecard (30 checks)
pytest                                              # unit tests (28)
python -m src.api.app                               # FastAPI service (http://localhost:8000)
streamlit run dashboard/app.py                      # dashboard (http://localhost:8501)
```

## Build status

- [x] **P0** Scaffold, config, data contracts, README
- [x] **P1** Real SEC ingestion — client + cache + normalization + filing-section extraction + `scripts.ingest` CLI
- [x] **P2** Retrieval — chunking, LSA vector + BM25 keyword + hybrid (RRF), structured `FactStore` (duration-based fiscal-year derivation), networkx knowledge graph
- [x] **P3** Deterministic tools — cited `ToolCall`s (growth, CAGR, margin, ratio, projection, scenario compare, NPV, IRR) + function-calling registry with JSON schemas
- [x] **P4** Agent — LLM client (Claude + mock fallback), capability router, deterministic plan→retrieve→compute→compose pipeline, guardrails (citation enforcement, freshness, safe-comms), human-approval gate
- [x] **P5** Governance — RBAC + approved-only + PII redaction (`security/`), JSONL audit log + token/cost + per-stage latency (`observability/`), provenance reporting (`provenance/`)
- [x] **P6** Evaluation — `eval/` suites (numeric accuracy, retrieval hit@3/MRR, generation faithfulness, safe-comms) + `scripts.evaluate` scorecard (30/30) + `pytest` suite (28 tests)
- [x] **P7** Deployment — FastAPI service (`src/api/app.py`: query/approve/provenance/costs/audit) + Streamlit dashboard (`dashboard/app.py`: cited findings, approval gate, provenance, reasoning trace)
- [x] **P8** Docs — [product discovery](docs/product_discovery.md), [model risk & governance](docs/model_risk.md), [architecture](docs/architecture.md)

**All 8 phases complete — all 23 rubric capabilities implemented and evaluated.**

## Documentation

- [**Submission note**](SUBMISSION.md) — reviewer summary, 2-minute run, rubric map, eval results.
- [**Demo walkthrough**](docs/DEMO.md) — narrated transcript + dashboard walkthrough (`python -m scripts.demo`).
- [**Product discovery**](docs/product_discovery.md) — personas, jobs-to-be-done, use cases, success metrics, scope.
- [**Model risk & governance**](docs/model_risk.md) — SR 11-7-style risk tiering, failure modes & mitigations, evaluation, oversight.
- [**Architecture**](docs/architecture.md) — system diagram, query lifecycle, module map, design decisions, latency/cost trade-offs.

## Notes on the data source

SEC requires a descriptive contact in the request `User-Agent`. Set `SEC_USER_AGENT`
in `.env`. Responses are cached under `data/cache/` (git-ignored), so the first run
needs network access and subsequent runs are reproducible/offline.

## Disclaimer

This is a research-assistant prototype. It surfaces sourced data and calculations
and **does not provide personalized investment advice**.

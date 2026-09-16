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
python -m src.api.app                               # FastAPI service
streamlit run dashboard/app.py                      # dashboard
pytest -q                                           # tests + evals
```

## Build status

- [x] **P0** Scaffold, config, data contracts, README
- [x] **P1** Real SEC ingestion — client + cache + normalization + filing-section extraction + `scripts.ingest` CLI
- [ ] **P2** Retrieval (vector + BM25 + hybrid + graph)
- [ ] **P3** Deterministic tools + structured outputs
- [ ] **P4** Agent orchestration + router + guardrails + human approval
- [ ] **P5** Provenance, freshness, security, audit, token/latency
- [ ] **P6** Evaluation (numeric, retrieval, generation, safe-comms)
- [ ] **P7** FastAPI + Streamlit
- [ ] **P8** Docs (product discovery, model risk, architecture)

## Notes on the data source

SEC requires a descriptive contact in the request `User-Agent`. Set `SEC_USER_AGENT`
in `.env`. Responses are cached under `data/cache/` (git-ignored), so the first run
needs network access and subsequent runs are reproducible/offline.

## Disclaimer

This is a research-assistant prototype. It surfaces sourced data and calculations
and **does not provide personalized investment advice**.

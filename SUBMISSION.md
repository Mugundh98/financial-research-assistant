# Submission Note — Financial-Research & Decision-Intelligence Assistant

**Author:** Mugundh · **Repo:** https://github.com/Mugundh98/financial-research-assistant

## The task

> Develop an agent that retrieves approved financial records and market research,
> performs tool-assisted calculations, compares scenarios, explains assumptions,
> produces source-cited analysis and prevents unsupported financial conclusions.
> Include evaluation for numeric accuracy, freshness, source provenance and safe
> user communication.

This submission implements that agent on **real SEC EDGAR data** and covers **all
23 capabilities** on the engineer checklist, each with working code (not stubs)
and an evaluation harness.

## Run it in 2 minutes

```bash
pip install -r requirements.txt
python -m scripts.ingest --tickers AAPL MSFT NVDA   # fetch + cache real SEC data
python -m scripts.demo                              # narrated end-to-end demo
python -m scripts.evaluate                          # evaluation scorecard (30 checks)
pytest                                              # unit tests (28)
streamlit run dashboard/app.py                      # dashboard (http://localhost:8501)
python -m src.api.app                               # REST API   (http://localhost:8000)
```

No API key is required. The LLM layer is **multi-provider** — set `LLM_BACKEND` to
`anthropic` (Claude), `gemini` (Google), or `mock`; each falls back to the
deterministic **mock** if its key is absent, so the pipeline, demo, and evals run
with zero secrets. Put `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` in `.env` to enable
real narration.

## Design in one paragraph

A **deterministic backbone** does everything that must be correct — retrieve
approved SEC records and compute every figure with rule-based tools — while the
**LLM writes only the prose**, and **guardrails verify** the result before it is
returned. Because the model never produces numbers, the highest-severity failure
mode (fabricated financials) is removed by construction; every claim that lacks a
citation is dropped, freshness is surfaced, advice is refused, and low-confidence
or forward-looking answers are routed to a human-approval gate.

## Rubric coverage (23/23)

| Capability | Where |
|---|---|
| AI for financial services | whole system; `docs/product_discovery.md` |
| Product discovery | `docs/product_discovery.md` |
| Retrieval over structured **and** unstructured data | `src/retrieval/` (`FactStore` + documents) |
| Data contracts | `src/contracts/models.py` (enforced in `src/ingestion/normalize.py`) |
| Vector **and** hybrid search | `src/retrieval/{vector,keyword,document_retriever}.py` (RRF) |
| Knowledge graphs | `src/retrieval/graph.py` (networkx) |
| Tool/function calling for deterministic calcs | `src/tools/` (+ Anthropic-format registry) |
| Structured outputs | `AnalysisResult` / `ToolCall` contracts |
| Agent orchestration | `src/agent/orchestrator.py` |
| Model & capability selection | `src/agent/router.py` |
| Prompt & context engineering | `src/agent/prompts.py` |
| Source provenance | `Citation` on every claim; `src/provenance/` |
| Temporal freshness | `as_of` stamps + `src/agent/guardrails.py::compute_freshness` |
| Numeric evaluation | `src/eval/numeric.py` |
| Retrieval & generation evaluation | `src/eval/{retrieval,generation}.py` |
| Model risk | `docs/model_risk.md` |
| Explainability | `reasoning_trace` + dashboard trace view |
| Security & access controls | `src/security/` (RBAC, approved-only, PII) |
| Audit logs | `src/observability/audit.py` |
| Token economics | `src/observability/metrics.py::CostMeter` |
| Latency/cost trade-offs | `Stopwatch` + `docs/architecture.md` |
| API & dashboard deployment | `src/api/app.py` + `dashboard/app.py` |
| Human approval | approval gate in orchestrator + dashboard/API |

## Evaluation results

`python -m scripts.evaluate` → **30/30** (report in `evals/report.json`):

| Suite | Result | Notes |
|---|---|---|
| Numeric accuracy | 11/11 | math identities + reported values vs public ground truth + tool-vs-manual |
| Retrieval | 2/2 | hybrid **hit@3 = 0.857** (> vector 0.714, BM25 0.571) |
| Generation faithfulness | 9/9 | 100% citation coverage; tool outputs re-derive from the FactStore |
| Safe communication | 8/8 | advice/scenario gated, out-of-scope refused, disclaimer always present |

Plus **28** `pytest` cases over calculations, contracts, planning, the fact
store, and guardrails.

## Data

Source: **SEC EDGAR** (no API key; official filings are the "approved records").
Preloaded corpus: **AAPL, MSFT, NVDA** — 7,583 validated XBRL facts + 9 filing
sections (Business / Risk Factors / MD&A), bundled so the repo runs offline. **Any
other US public company is fetched from SEC on demand** (by ticker or well-known
name) and answered with citations. Every fetch is cached to `data/cache/`. Fiscal
years are derived from the reporting-period end (periods classified by duration)
to avoid SEC's comparative-year mislabeling. When no SEC data exists, qualitative
questions get a **labeled, unverified** LLM answer (only with a real key); numeric
or advice questions **refuse** rather than fabricate.

## Known limitations (by design / scope)

- Three companies are preloaded; any other US filer is **auto-fetched on demand**
  (10-K only). Truly unavailable questions **refuse** (numeric/advice) or return a
  **labeled, unverified** LLM answer (qualitative, with a key) — never a guessed figure.
- Freshness is at annual-filing cadence (10-Q/news not ingested) — surfaced via
  the freshness signal rather than hidden.
- Retrieval uses LSA + BM25 by default (neural embeddings are a one-function
  upgrade); section extraction is heuristic (does not affect cited figures).
- Scenario projections are mechanical constant-growth, explicitly labelled
  illustrative and human-gated — not forecasts.

## Where to look first

`README.md` (rubric map + quickstart) → `docs/DEMO.md` (walkthrough) →
`docs/architecture.md` → `src/agent/orchestrator.py` (the pipeline) →
`docs/model_risk.md`.

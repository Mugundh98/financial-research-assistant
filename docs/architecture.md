# Architecture

## Overview

A **deterministic backbone** (retrieve approved data → compute with tools) does
everything that must be correct and reproducible; a **generative model** writes
only the prose; **guardrails** verify the result before it is returned. This is
what lets the system use real, current SEC data yet never fabricate a figure.

```
                          ┌──────────────────────────── Agent (orchestrator) ───────────────────────────┐
  User ──query+role──▶    │  plan ─▶ [access + scope guard] ─▶ retrieve ─▶ compute ─▶ compose ─▶ verify   │ ──▶ AnalysisResult
        (API / dashboard) │   │            │                     │            │           │         │      │     (structured,
                          │  router     security               retrieval    tools      LLM      guardrails│      cited, JSON)
                          └───┼────────────┼─────────────────────┼────────────┼───────────┼─────────┼──────┘
                              │            │                     │            │           │         │
                    model/capability   RBAC + approved-only   vector+BM25   deterministic  Claude   citation/freshness/
                      selection        + PII redaction        +hybrid+KG    calculators   (or mock) safe-comms + approval
                              │                                     │            │                        │
                        cross-cutting:  audit log · token economics · per-stage latency · provenance · reasoning trace
```

## Query lifecycle

1. **Plan** (`agent/planning.py`) — rule-based: tickers, intent, metrics, advice flag.
2. **Guard** (`security/`) — scope (covered companies only), role capability, approved-only data.
3. **Route** (`agent/router.py`) — fast vs strong model by task complexity.
4. **Retrieve** — structured facts (`FactStore`) + document chunks (hybrid) + optional graph.
5. **Compute** (`tools/`) — deterministic, **cited** `ToolCall`s (growth, CAGR, margin, scenarios…).
6. **Compose** (`agent/orchestrator.py` + `prompts.py`) — deterministic findings; LLM writes the narrative (mock → templated).
7. **Verify** (`agent/guardrails.py`) — drop uncited claims, freshness, safe-comms, confidence, approval gate.
8. **Govern** — PII redaction, audit log, cost/latency accounting; return one `AnalysisResult`.

## Module map

| Path | Responsibility |
|---|---|
| `src/contracts/` | Pydantic data contracts (the boundary types) |
| `src/ingestion/` | SEC EDGAR client + cache, XBRL/narrative normalization, corpus builder |
| `src/retrieval/` | chunking, LSA vectors, BM25, hybrid (RRF), `FactStore`, knowledge graph |
| `src/tools/` | pure calculations + fact-aware tools + function-calling registry |
| `src/agent/` | planning, router, prompts, LLM client, orchestrator, guardrails |
| `src/security/` | access control (RBAC), approved-only, PII redaction |
| `src/observability/` | audit log, token/cost meter, latency stopwatch |
| `src/provenance/` | source/as-of reporting |
| `src/eval/` | numeric / retrieval / generation / safety evaluation |
| `src/api/` | FastAPI service |
| `dashboard/` | Streamlit UI |

## Key design decisions

- **Deterministic backbone + LLM narration.** Tools and structured lookups own
  every number; the LLM only writes prose from supplied evidence. Removes the
  worst failure mode (fabricated financials) and makes results reproducible.
- **Provider-agnostic LLM with mock fallback.** Default Claude; a deterministic
  mock runs the entire pipeline + evals with **zero API keys** — critical for a
  gradeable, reproducible deliverable.
- **Cache-first real data.** SEC EDGAR (no key; official "approved records");
  every fetch cached to `data/cache/` for reproducible, offline-after-first runs.
- **Contracts everywhere.** One validated shape at every boundary; the agent's
  only output is `AnalysisResult`.
- **Fiscal-period correctness.** Fiscal year derived from period end; periods
  classified by duration (annual/quarter/instant) — avoids SEC `fy` mislabeling.

## Retrieval design

- **Structured** (`FactStore`): typed queries over XBRL facts; exact figures with
  provenance; annual series de-duplicated to the latest restatement.
- **Unstructured**: sentence-aware chunking → **LSA vectors** (TF-IDF→SVD, offline;
  neural-embeddings-upgradeable) + **BM25** keyword → fused with **Reciprocal Rank
  Fusion**. Hybrid measured best (hit@3 0.857).
- **Knowledge graph** (networkx): company ↔ sector ↔ concept ↔ filing relations
  for lookups flat retrieval can't answer.

## Latency & cost trade-offs

Per-query, mock backend (measured via the `Stopwatch`): **~50 ms total** —
dominated by retrieval/tool `gather` (~48 ms), with plan/compose/verify < 1 ms
each. Cost is **$0** (mock + cached data).

Trade-offs the router and design make:
- **Model tier:** simple lookups → a fast/cheap model; comparisons/scenarios/risk
  synthesis → a stronger model. The LLM is invoked once, for prose only, so token
  spend is bounded and independent of the (free, deterministic) computation.
- **Embeddings:** LSA is free/offline/instant; neural embeddings improve recall at
  the cost of a model download and more compute — a config swap, not a rewrite.
- **Freshness vs cost:** annual 10-K ingestion is cheap and cached; adding 10-Q /
  news would improve freshness at higher ingestion and storage cost.
- **Caching:** first SEC fetch pays network latency; subsequent runs are local.

## Extensibility

More companies/tickers (one ingest command), 10-Q/news sources, neural embeddings,
a real LLM key (drop-in), persistent audit/result store, and a full LLM tool-use
loop (the registry already emits Anthropic-format schemas).

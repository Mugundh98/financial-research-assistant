"""FastAPI service for the Financial-Research & Decision-Intelligence agent.

Loads the agent once at startup and exposes the pipeline over HTTP:
  GET  /health            service + corpus status
  GET  /companies         covered companies
  POST /query             run a query (role-aware) -> AnalysisResult
  GET  /provenance/{id}   source/as-of summary for a prior answer
  POST /approve/{id}      human approval (admin only)
  GET  /costs             session token/cost economics
  GET  /audit             recent audit events

Run: python -m src.api.app   (defaults to http://0.0.0.0:8000)
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..agent import Agent
from ..config import settings
from ..contracts.models import AccessContext, AnalysisResult, Role
from ..ingestion.corpus import Corpus
from ..observability import AuditLogger
from ..provenance import build_provenance

app = FastAPI(title="Financial-Research & Decision-Intelligence API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

settings.ensure_dirs()
_corpus = Corpus.load()
_agent = Agent(_corpus, audit=AuditLogger(path=settings.audit_dir / "api_audit.jsonl"))
_results: dict[str, AnalysisResult] = {}


class QueryRequest(BaseModel):
    query: str
    role: str = "analyst"
    user_id: str = "api-user"


class ApproveRequest(BaseModel):
    decision: str = "approve"          # "approve" | "reject"
    approver: str = "admin@firm.com"
    role: str = "admin"


def _access(role: str, user_id: str) -> AccessContext:
    try:
        return AccessContext(user_id=user_id, role=Role(role))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid role '{role}' (viewer|analyst|admin)")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_backend": _agent.llm.backend,
        "companies": len(_corpus.companies),
        "facts": len(_corpus.facts),
        "documents": len(_corpus.documents),
    }


@app.get("/companies")
def companies() -> list[dict]:
    return [
        {"ticker": c.ticker, "name": c.name, "cik": c.cik, "sector": c.sic_description}
        for c in _corpus.companies
    ]


@app.post("/query")
def query(req: QueryRequest) -> dict:
    access = _access(req.role, req.user_id)
    result = _agent.answer(req.query, access=access)
    _results[result.query_id] = result
    return result.model_dump(mode="json")


@app.get("/provenance/{query_id}")
def provenance(query_id: str) -> dict:
    result = _results.get(query_id)
    if not result:
        raise HTTPException(status_code=404, detail="unknown query_id")
    return build_provenance(result)


@app.post("/approve/{query_id}")
def approve(query_id: str, req: ApproveRequest) -> dict:
    result = _results.get(query_id)
    if not result:
        raise HTTPException(status_code=404, detail="unknown query_id")
    access = _access(req.role, req.approver)
    result = _agent.resolve_approval(result, req.decision, approver=req.approver, access=access)
    _results[query_id] = result
    return result.model_dump(mode="json")


@app.get("/costs")
def costs() -> dict:
    return _agent.cost.summary()


@app.get("/audit")
def audit(limit: int = 20) -> list[dict]:
    return [e.model_dump(mode="json") for e in _agent.audit.events[-limit:]]


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()

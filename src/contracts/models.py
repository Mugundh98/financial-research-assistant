"""Data contracts for the Financial-Research & Decision-Intelligence assistant.

These Pydantic models are the single source of truth for every piece of data
that crosses a boundary in the system: ingested SEC data, retrieval results,
deterministic tool calls, and the final structured analysis the agent returns.

Design principles
-----------------
* Ingested-data models use ``extra="forbid"`` so malformed upstream data fails
  loudly at the contract boundary (this is the "data contracts" guarantee).
* Every fact/document/chunk carries provenance (source, source_url, accession)
  and a temporal stamp (``as_of``) so downstream code can enforce citation and
  freshness rules.
* The agent's only permitted output shape is :class:`AnalysisResult`.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class SourceType(str, Enum):
    FINANCIAL_FACT = "financial_fact"
    DOCUMENT = "document"


class RetrievalMethod(str, Enum):
    VECTOR = "vector"
    BM25 = "bm25"
    HYBRID = "hybrid"
    GRAPH = "graph"
    STRUCTURED = "structured"


class Role(str, Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMIN = "admin"


class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# --------------------------------------------------------------------------- #
# Ingested data contracts
# --------------------------------------------------------------------------- #
class Company(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cik: str  # zero-padded 10 digits
    ticker: Optional[str] = None
    name: str
    sic: Optional[str] = None
    sic_description: Optional[str] = None
    fiscal_year_end: Optional[str] = None

    @field_validator("cik", mode="before")
    @classmethod
    def _pad_cik(cls, v: Any) -> str:
        digits = "".join(ch for ch in str(v) if ch.isdigit())
        return digits.zfill(10) if digits else "0000000000"


class FinancialFact(BaseModel):
    """One XBRL observation from an approved SEC filing, fully sourced."""

    model_config = ConfigDict(extra="forbid")

    id: str
    cik: str
    company: Optional[str] = None
    taxonomy: str = "us-gaap"
    concept: str                      # e.g. "Revenues", "NetIncomeLoss"
    label: Optional[str] = None
    value: float
    unit: str = "USD"
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None   # "FY", "Q1".."Q4"
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    filed: Optional[date] = None
    form: Optional[str] = None            # "10-K", "10-Q"
    accession: Optional[str] = None
    frame: Optional[str] = None

    # governance / provenance
    source: str = "SEC EDGAR"
    source_url: Optional[str] = None
    approved: bool = True
    as_of: Optional[date] = None


class Document(BaseModel):
    """An unstructured research/narrative unit (e.g. a filing section)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    cik: Optional[str] = None
    company: Optional[str] = None
    title: str
    section: Optional[str] = None         # "Risk Factors", "MD&A", ...
    text: str
    form: Optional[str] = None
    accession: Optional[str] = None
    filed: Optional[date] = None
    as_of: Optional[date] = None
    source: str = "SEC EDGAR"
    source_url: Optional[str] = None
    approved: bool = True


class Chunk(BaseModel):
    """A retrievable slice of a Document, with denormalized provenance."""

    model_config = ConfigDict(extra="forbid")

    id: str
    doc_id: str
    text: str
    ordinal: int = 0

    cik: Optional[str] = None
    company: Optional[str] = None
    section: Optional[str] = None
    form: Optional[str] = None
    accession: Optional[str] = None
    filed: Optional[date] = None
    as_of: Optional[date] = None
    source: str = "SEC EDGAR"
    source_url: Optional[str] = None
    approved: bool = True

    embedding: Optional[list[float]] = Field(default=None, repr=False)


# --------------------------------------------------------------------------- #
# Provenance / retrieval
# --------------------------------------------------------------------------- #
class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: SourceType
    source: str = "SEC EDGAR"
    source_url: Optional[str] = None
    as_of: Optional[date] = None
    form: Optional[str] = None
    accession: Optional[str] = None
    snippet: Optional[str] = None


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk: Chunk
    score: float
    method: RetrievalMethod


# --------------------------------------------------------------------------- #
# Deterministic calculation / reasoning artifacts
# --------------------------------------------------------------------------- #
class ToolCall(BaseModel):
    """A deterministic calculation, with the sources of its inputs attached."""

    model_config = ConfigDict(extra="forbid")

    tool: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    output: Any = None
    formula: Optional[str] = None
    unit: Optional[str] = None
    citations: list[Citation] = Field(default_factory=list)
    error: Optional[str] = None


class Assumption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    basis: Optional[str] = None
    citations: list[Citation] = Field(default_factory=list)


class Claim(BaseModel):
    """A statement in the analysis. Must have citations to be ``supported``."""

    model_config = ConfigDict(extra="forbid")

    statement: str
    citations: list[Citation] = Field(default_factory=list)
    supported: bool = False
    kind: Literal["fact", "calculation", "comparison", "qualitative"] = "qualitative"


class ScenarioResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    metrics: dict[str, float] = Field(default_factory=dict)
    calculations: list[ToolCall] = Field(default_factory=list)


class ScenarioComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarios: list[ScenarioResult] = Field(default_factory=list)
    deltas: dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


# --------------------------------------------------------------------------- #
# Freshness / cost / approval / access / audit
# --------------------------------------------------------------------------- #
class FreshnessInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oldest_as_of: Optional[date] = None
    newest_as_of: Optional[date] = None
    max_age_days: Optional[int] = None
    is_stale: bool = False
    stale_sources: list[str] = Field(default_factory=list)


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    reason: Optional[str] = None
    approver: Optional[str] = None
    decided_at: Optional[datetime] = None


class AccessContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = "demo-user"
    role: Role = Role.ANALYST


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event: str
    query_id: Optional[str] = None
    user_id: Optional[str] = None
    role: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# The agent's single structured output
# --------------------------------------------------------------------------- #
class AnalysisResult(BaseModel):
    """The one permitted output shape of the agent (structured outputs)."""

    model_config = ConfigDict(extra="forbid")

    query_id: str
    query: str
    answer: str = ""

    findings: list[Claim] = Field(default_factory=list)
    calculations: list[ToolCall] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    comparison: Optional[ScenarioComparison] = None
    citations: list[Citation] = Field(default_factory=list)

    freshness: FreshnessInfo = Field(default_factory=FreshnessInfo)
    confidence: float = 0.0
    caveats: list[str] = Field(default_factory=list)
    disclaimers: list[str] = Field(default_factory=list)
    reasoning_trace: list[str] = Field(default_factory=list)  # explainability

    requires_human_approval: bool = False
    approval: ApprovalDecision = Field(default_factory=ApprovalDecision)

    refused: bool = False
    refusal_reason: Optional[str] = None

    model_used: Optional[str] = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: Optional[float] = None

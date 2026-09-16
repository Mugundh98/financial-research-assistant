"""Central configuration (env-driven, with safe defaults).

Uses pydantic-settings so every value can be overridden via .env or the
environment. Defaults are chosen so the whole system runs with NO secrets:
the LLM layer falls back to a deterministic mock when no API key is present.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
CORPUS_DIR = DATA_DIR / "corpus"
AUDIT_DIR = BASE_DIR / "audit_logs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- LLM ----
    llm_backend: str = "anthropic"          # "anthropic" | "mock"
    anthropic_api_key: str | None = None
    llm_model_strong: str = "claude-sonnet-5"
    llm_model_fast: str = "claude-haiku-4-5-20251001"
    llm_max_tokens: int = 1500
    llm_temperature: float = 0.0

    # ---- SEC EDGAR ----
    sec_user_agent: str = "ey-wft-assignment/1.0 (contact: set-your-contact@example.com)"
    sec_base_data: str = "https://data.sec.gov"
    sec_base_www: str = "https://www.sec.gov"
    request_timeout: float = 30.0
    sec_min_interval: float = 0.2           # politeness throttle (~5 req/s)

    # ---- Access control ----
    default_role: str = "analyst"           # viewer | analyst | admin

    # ---- Freshness / guardrails ----
    staleness_days: int = 200
    min_citations_for_claim: int = 1
    require_approval_default: bool = False

    # ---- Paths (not env-driven, but centralized here) ----
    base_dir: Path = Field(default=BASE_DIR)
    data_dir: Path = Field(default=DATA_DIR)
    cache_dir: Path = Field(default=CACHE_DIR)
    corpus_dir: Path = Field(default=CORPUS_DIR)
    audit_dir: Path = Field(default=AUDIT_DIR)

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.cache_dir, self.corpus_dir, self.audit_dir):
            Path(d).mkdir(parents=True, exist_ok=True)


settings = Settings()

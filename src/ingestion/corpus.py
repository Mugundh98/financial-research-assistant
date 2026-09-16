"""Assemble and persist the local corpus of approved data.

A :class:`Corpus` bundles the three ingested contract types (companies,
financial facts, documents). It is saved as plain JSON under ``data/corpus/`` so
downstream phases (retrieval, tools, agent, eval) load a fixed, validated
snapshot without re-hitting the network.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel, Field

from ..config import settings
from ..contracts.models import Company, Document, FinancialFact
from .filings import documents_for_company
from .normalize import CORE_CONCEPTS, company_from_submissions, facts_from_company_facts
from .sec_client import SECClient


class Corpus(BaseModel):
    companies: list[Company] = Field(default_factory=list)
    facts: list[FinancialFact] = Field(default_factory=list)
    documents: list[Document] = Field(default_factory=list)

    def save(self, directory: Optional[Path] = None) -> Path:
        d = Path(directory or settings.corpus_dir)
        d.mkdir(parents=True, exist_ok=True)
        for name, items in (
            ("companies.json", self.companies),
            ("facts.json", self.facts),
            ("documents.json", self.documents),
        ):
            (d / name).write_text(
                json.dumps([i.model_dump(mode="json") for i in items], indent=2),
                encoding="utf-8",
            )
        return d

    @classmethod
    def load(cls, directory: Optional[Path] = None) -> "Corpus":
        d = Path(directory or settings.corpus_dir)

        def _read(name: str) -> list:
            p = d / name
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

        return cls(
            companies=[Company(**x) for x in _read("companies.json")],
            facts=[FinancialFact(**x) for x in _read("facts.json")],
            documents=[Document(**x) for x in _read("documents.json")],
        )

    def facts_for(self, cik: str) -> list[FinancialFact]:
        cik10 = SECClient.pad_cik(cik)
        return [f for f in self.facts if f.cik == cik10]


def build_corpus(
    tickers: Iterable[str],
    client: Optional[SECClient] = None,
    concepts: Optional[list[str]] = None,
    sections: Optional[list[str]] = None,
    form: str = "10-K",
    force: bool = False,
    save: bool = True,
    verbose: bool = True,
) -> Corpus:
    client = client or SECClient()
    concepts = concepts if concepts is not None else CORE_CONCEPTS
    corpus = Corpus()

    for ticker in tickers:
        cik = client.resolve_cik(ticker)
        if not cik:
            if verbose:
                print(f"[warn] could not resolve ticker {ticker}")
            continue
        sub = client.submissions(cik, force=force)
        company = company_from_submissions(sub)
        corpus.companies.append(company)

        facts = facts_from_company_facts(
            cik, client.company_facts(cik, force=force), concepts=concepts
        )
        corpus.facts.extend(facts)

        docs = documents_for_company(
            client, cik, company.name, form=form, sections=sections, force=force
        )
        corpus.documents.extend(docs)

        if verbose:
            secs = ", ".join(f"{d.section}({len(d.text)}c)" for d in docs) or "none"
            print(f"[ok] {ticker} {company.name}: {len(facts)} facts | sections: {secs}")

    if save:
        out = corpus.save()
        if verbose:
            print(f"[saved] corpus -> {out}")
    return corpus

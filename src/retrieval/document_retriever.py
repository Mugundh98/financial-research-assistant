"""Unified document retriever: vector + BM25 + hybrid, with provenance.

Owns one shared chunk list and both indexes built over it, and returns
``RetrievalHit`` objects (chunk + score + method) that carry enough provenance
to be turned into citations.
"""
from __future__ import annotations

from typing import Optional

from ..contracts.models import Chunk, Citation, RetrievalHit, RetrievalMethod, SourceType
from .chunking import chunk_corpus
from .fusion import reciprocal_rank_fusion
from .keyword import BM25Index
from .vector import VectorIndex


class DocumentRetriever:
    def __init__(self, embedder=None):
        self.vector = VectorIndex(embedder)
        self.keyword = BM25Index()
        self.chunks: list[Chunk] = []

    def build(self, chunks: list[Chunk]) -> "DocumentRetriever":
        self.chunks = list(chunks)
        self.vector.build(self.chunks)
        self.keyword.build(self.chunks)
        return self

    @classmethod
    def from_corpus(cls, corpus, embedder=None, **chunk_kwargs) -> "DocumentRetriever":
        return cls(embedder).build(chunk_corpus(corpus.documents, **chunk_kwargs))

    def _allowed(self, cik: Optional[str], section: Optional[str]) -> Optional[list[int]]:
        if cik is None and section is None:
            return None
        return [
            i
            for i, c in enumerate(self.chunks)
            if (cik is None or c.cik == cik) and (section is None or c.section == section)
        ]

    def search(
        self,
        query: str,
        k: int = 5,
        method: str = "hybrid",
        cik: Optional[str] = None,
        section: Optional[str] = None,
        pool: int = 20,
    ) -> list[RetrievalHit]:
        allowed = self._allowed(cik, section)

        if method == "vector":
            return [self._hit(i, s, RetrievalMethod.VECTOR) for i, s in self.vector.search(query, k, allowed)]
        if method == "bm25":
            return [self._hit(i, s, RetrievalMethod.BM25) for i, s in self.keyword.search(query, k, allowed)]

        # hybrid: fuse the two ranked lists with RRF
        v = self.vector.search(query, pool, allowed)
        b = self.keyword.search(query, pool, allowed)
        fused = reciprocal_rank_fusion([[i for i, _ in v], [i for i, _ in b]])
        ranked = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [self._hit(i, s, RetrievalMethod.HYBRID) for i, s in ranked]

    def _hit(self, idx: int, score: float, method: RetrievalMethod) -> RetrievalHit:
        return RetrievalHit(chunk=self.chunks[idx], score=float(score), method=method)


def hit_to_citation(hit: RetrievalHit) -> Citation:
    c = hit.chunk
    snippet = c.text[:200] + ("…" if len(c.text) > 200 else "")
    return Citation(
        source_id=c.id,
        source_type=SourceType.DOCUMENT,
        source=c.source,
        source_url=c.source_url,
        as_of=c.as_of,
        form=c.form,
        accession=c.accession,
        snippet=snippet,
    )

"""Sparse keyword search over chunks (BM25)."""
from __future__ import annotations

import re
from typing import Iterable, Optional

from rank_bm25 import BM25Okapi

from ..contracts.models import Chunk
from .common import topk

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class BM25Index:
    method = "bm25"

    def __init__(self):
        self.chunks: list[Chunk] = []
        self.bm25: Optional[BM25Okapi] = None

    def build(self, chunks: list[Chunk]) -> "BM25Index":
        self.chunks = list(chunks)
        corpus = [tokenize(c.text) for c in self.chunks]
        if corpus:
            self.bm25 = BM25Okapi(corpus)
        return self

    def search(self, query: str, k: int = 5, allowed: Optional[Iterable[int]] = None) -> list[tuple[int, float]]:
        if self.bm25 is None or not self.chunks:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        return topk(scores, k, allowed)

"""Dense vector search over chunks (cosine similarity)."""
from __future__ import annotations

from typing import Iterable, Optional

import numpy as np

from ..contracts.models import Chunk
from .common import topk
from .embeddings import get_embedder


class VectorIndex:
    method = "vector"

    def __init__(self, embedder=None):
        self.embedder = embedder or get_embedder()
        self.chunks: list[Chunk] = []
        self.matrix: Optional[np.ndarray] = None

    def build(self, chunks: list[Chunk]) -> "VectorIndex":
        self.chunks = list(chunks)
        texts = [c.text for c in self.chunks]
        if texts:
            self.embedder.fit(texts)
            self.matrix = self.embedder.encode(texts)
        return self

    def search(self, query: str, k: int = 5, allowed: Optional[Iterable[int]] = None) -> list[tuple[int, float]]:
        if self.matrix is None or not self.chunks:
            return []
        q = self.embedder.encode([query])[0]
        scores = self.matrix @ q
        return topk(scores, k, allowed)

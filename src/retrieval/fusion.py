"""Rank fusion for hybrid retrieval."""
from __future__ import annotations

from typing import Sequence


def reciprocal_rank_fusion(rankings: Sequence[Sequence[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion.

    Each input is a ranked list of item indices (best first). An item's fused
    score is the sum over lists of ``1 / (k + rank)``. RRF is robust because it
    combines *ranks*, not raw scores, so the very different score scales of
    vector cosine and BM25 don't need normalization.
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return fused

"""Small shared helpers for retrieval indexes."""
from __future__ import annotations

from typing import Iterable, Optional

import numpy as np


def topk(scores, k: int, allowed: Optional[Iterable[int]] = None) -> list[tuple[int, float]]:
    """Return the (index, score) pairs of the top-k highest scores.

    If ``allowed`` is given, only those indices are eligible (others masked out).
    """
    arr = np.asarray(scores, dtype=float)
    if arr.size == 0:
        return []
    if allowed is not None:
        masked = np.full(arr.shape, -np.inf)
        idx_allowed = np.asarray(list(allowed), dtype=int)
        if idx_allowed.size:
            masked[idx_allowed] = arr[idx_allowed]
        arr = masked
    order = np.argsort(-arr)[: max(k, 0)]
    out: list[tuple[int, float]] = []
    for i in order:
        s = arr[int(i)]
        if np.isfinite(s):
            out.append((int(i), float(s)))
    return out

"""Retrieval evaluation: hit@3 and MRR for vector vs BM25 vs hybrid.

Labeled queries name the company + section that should be retrieved. Reported
per method so the hybrid advantage is visible; the suite passes if hybrid clears
a hit@3 bar and is no worse than the better single method on MRR.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..config import settings
from ..retrieval import DocumentRetriever
from .base import SuiteResult

METHODS = ["vector", "bm25", "hybrid"]


def _match(hit, label) -> bool:
    company_ok = label["company"].lower() in (hit.chunk.company or "").lower()
    section_ok = (not label.get("section")) or hit.chunk.section == label["section"]
    return company_ok and section_ok


def run_retrieval(corpus, labels_path: Optional[Path] = None, k: int = 5) -> SuiteResult:
    s = SuiteResult("retrieval")
    retriever = DocumentRetriever.from_corpus(corpus)
    path = labels_path or (settings.base_dir / "evals" / "retrieval_labels.json")
    labels = json.loads(Path(path).read_text(encoding="utf-8"))
    n = len(labels)

    agg = {m: {"hit@3": 0, "mrr": 0.0} for m in METHODS}
    for label in labels:
        for m in METHODS:
            hits = retriever.search(label["query"], k=k, method=m)
            rank = next((i + 1 for i, h in enumerate(hits) if _match(h, label)), None)
            if rank:
                agg[m]["mrr"] += 1.0 / rank
                if rank <= 3:
                    agg[m]["hit@3"] += 1

    for m in METHODS:
        agg[m] = {"hit@3_rate": round(agg[m]["hit@3"] / n, 3), "mrr": round(agg[m]["mrr"] / n, 3)}
    s.metrics = {"n": n, "by_method": agg}

    hy, ve, bm = agg["hybrid"], agg["vector"], agg["bm25"]
    s.add("hybrid hit@3 >= 0.70", hy["hit@3_rate"] >= 0.70, str(hy))
    s.add("hybrid MRR >= min(vector, bm25)", hy["mrr"] >= min(ve["mrr"], bm["mrr"]),
          f"hybrid={hy['mrr']} vector={ve['mrr']} bm25={bm['mrr']}")
    return s

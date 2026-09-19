"""Run the full evaluation suite and print a scorecard.

    python -m scripts.evaluate            # print scorecard
    python -m scripts.evaluate --json out.json

Writes evals/report.json by default.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.agent import Agent
from src.config import settings
from src.eval import run_generation, run_numeric, run_retrieval, run_safety
from src.ingestion.corpus import Corpus
from src.observability import AuditLogger


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=str(settings.base_dir / "evals" / "report.json"))
    args = ap.parse_args()

    corpus = Corpus.load()
    # quiet, throwaway audit log for eval runs
    agent = Agent(corpus, audit=AuditLogger(path=settings.audit_dir / "eval_audit.jsonl"))

    suites = [
        run_numeric(corpus),
        run_retrieval(corpus),
        run_generation(agent),
        run_safety(agent),
    ]

    print("\n" + "=" * 64)
    print("  EVALUATION SCORECARD")
    print("=" * 64)
    total_p = total_n = 0
    for s in suites:
        total_p += s.passed
        total_n += s.total
        bar = "PASS" if s.passed == s.total else "FAIL"
        print(f"\n[{bar}] {s.name}: {s.passed}/{s.total} ({s.rate:.0%})")
        if s.metrics:
            print(f"      metrics: {s.metrics}")
        for c in s.cases:
            mark = "ok " if c.passed else "XX "
            print(f"      {mark} {c.name}" + (f"  ({c.detail})" if c.detail and not c.passed else ""))

    print("\n" + "-" * 64)
    print(f"  TOTAL: {total_p}/{total_n} ({total_p / total_n:.0%})")
    print("-" * 64)

    report = {"total_passed": total_p, "total": total_n,
              "suites": [s.to_dict() for s in suites]}
    Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  report -> {args.json}\n")


if __name__ == "__main__":
    main()

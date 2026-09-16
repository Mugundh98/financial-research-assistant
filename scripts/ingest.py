"""CLI: ingest approved SEC EDGAR data into the local corpus.

Usage:
    python -m scripts.ingest --tickers AAPL MSFT NVDA
    python -m scripts.ingest --tickers AAPL --force
"""
from __future__ import annotations

import argparse

from src.ingestion.corpus import build_corpus


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tickers", nargs="+", default=["AAPL", "MSFT", "NVDA"])
    ap.add_argument("--form", default="10-K")
    ap.add_argument(
        "--force", action="store_true", help="bypass cache and re-fetch from SEC"
    )
    args = ap.parse_args()

    corpus = build_corpus(args.tickers, form=args.form, force=args.force)
    print(
        f"\nCorpus totals: {len(corpus.companies)} companies, "
        f"{len(corpus.facts)} facts, {len(corpus.documents)} documents"
    )


if __name__ == "__main__":
    main()

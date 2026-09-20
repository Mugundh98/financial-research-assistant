"""Resolve a free-text query to SEC tickers/CIKs beyond the preloaded corpus.

Two-stage and deliberately conservative to avoid false positives:
* explicit **ticker symbols** (upper-case tokens), minus a stoplist of common
  finance acronyms, validated against SEC's full ticker list; and
* a small curated **alias map** of well-known company names -> tickers.

Anything else should be asked for by ticker. This keeps normal queries offline
(the SEC ticker list is only consulted when a plausible unknown ticker appears).
"""
from __future__ import annotations

import re

from .sec_client import SECClient

# Well-known names -> ticker (kept small/unambiguous; use a ticker for the rest).
ALIASES: dict[str, str] = {
    "apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA", "amazon": "AMZN",
    "alphabet": "GOOGL", "google": "GOOGL", "facebook": "META", "netflix": "NFLX",
    "tesla": "TSLA", "intel": "INTC", "oracle": "ORCL", "salesforce": "CRM",
    "adobe": "ADBE", "cisco": "CSCO", "qualcomm": "QCOM", "broadcom": "AVGO",
    "jpmorgan": "JPM", "walmart": "WMT", "disney": "DIS", "boeing": "BA",
    "exxon": "XOM", "chevron": "CVX", "pfizer": "PFE", "starbucks": "SBUX",
    "uber": "UBER", "paypal": "PYPL", "coinbase": "COIN", "palantir": "PLTR",
}

# Upper-case tokens that look like tickers but are not.
TICKER_STOP: set[str] = {
    "A", "I", "AI", "US", "SEC", "EPS", "CAGR", "USD", "YOY", "GAAP", "CEO",
    "CFO", "IPO", "ETF", "API", "OK", "FY", "THE", "AND", "OR", "VS", "Q",
    "AN", "IT", "BY", "MD", "GDP", "ESG", "R", "D",
}

_UPPER = re.compile(r"\b[A-Z]{1,5}\b")
_WORD = re.compile(r"[a-zA-Z]{3,}")


def extract_candidate_tickers(query: str) -> set[str]:
    """Offline: candidate tickers implied by the query (upper-case + aliases)."""
    out: set[str] = set()
    for tok in _UPPER.findall(query):
        if tok not in TICKER_STOP:
            out.add(tok)
    for word in _WORD.findall(query.lower()):
        if word in ALIASES:
            out.add(ALIASES[word])
    return out


class TickerResolver:
    def __init__(self, client: SECClient):
        self.client = client
        self._map: dict[str, str] | None = None

    def _ticker_map(self) -> dict[str, str]:
        if self._map is None:
            data = self.client.company_tickers()
            self._map = {
                str(row["ticker"]).upper(): SECClient.pad_cik(row["cik_str"])
                for row in data.values()
            }
        return self._map

    def resolve(self, query: str) -> list[tuple[str, str]]:
        """Return [(cik, ticker)] for candidates that are real SEC filers."""
        mapping = self._ticker_map()
        found: dict[str, tuple[str, str]] = {}
        for ticker in extract_candidate_tickers(query):
            cik = mapping.get(ticker)
            if cik:
                found[cik] = (cik, ticker)
        return list(found.values())

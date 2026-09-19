"""PII redaction for user-facing text.

A defense-in-depth scrub of the answer and finding statements. SEC filings
rarely contain PII, but the assistant must never surface emails, SSNs, card
numbers, or phone numbers if any leak into retrieved text.
"""
from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("PHONE", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
]


def redact(text: str) -> tuple[str, int]:
    """Return (redacted_text, count_of_redactions)."""
    if not text:
        return text, 0
    total = 0
    for label, pattern in _PATTERNS:
        text, n = pattern.subn(f"[REDACTED-{label}]", text)
        total += n
    return text, total

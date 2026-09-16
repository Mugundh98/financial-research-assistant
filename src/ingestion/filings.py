"""Extract unstructured narrative sections from SEC filings into Documents.

10-K filings carry the qualitative "market research"-style context (business
overview, risk factors, management's discussion). We fetch the primary filing
document, convert it to text, and best-effort split out the standard Items.

Section splitting on raw filing HTML is inherently heuristic (filings also list
the Items in a table of contents). We take the longest span between an Item
header and the next Item header, which reliably skips the short TOC entries, and
fall back to the whole filing if nothing parses.
"""
from __future__ import annotations

import html as html_lib
import re
from typing import Optional

from ..config import settings
from ..contracts.models import Document
from .normalize import _parse_date
from .sec_client import SECClient

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t   ]+")
_MULTINL_RE = re.compile(r"\n{3,}")

def _fuzzy(phrase: str) -> str:
    """Regex for a title tolerant of intra-word spacing artifacts from HTML
    (e.g. filings that render "RISK" as "RIS K")."""
    words = phrase.split()
    return r"\s+".join(r"\s*".join(re.escape(ch) for ch in w) for w in words)


def _header(item: str, title: str) -> str:
    """A real section header: 'Item <n>' immediately followed by its title.
    In-text cross-references like 'Item 1A of this Form 10-K' don't match
    because the title does not follow the item number."""
    return rf"item\s*{item}[^A-Za-z0-9]{{0,8}}{_fuzzy(title)}"


# section name -> (start-header patterns, end-header patterns)
SECTIONS: dict[str, tuple[list[str], list[str]]] = {
    "Business": (
        [_header("1", "business")],
        [_header("1a", "risk factors")],
    ),
    "Risk Factors": (
        [_header("1a", "risk factors")],
        [_header("1b", "unresolved"), _header("2", "properties"), _header("3", "legal")],
    ),
    "MD&A": (
        [_header("7", "management")],
        [_header("7a", "quantitative"), _header("8", "financial")],
    ),
}
DEFAULT_SECTIONS = ["Business", "Risk Factors", "MD&A"]


def html_to_text(raw: str) -> str:
    raw = _SCRIPT_STYLE_RE.sub(" ", raw)
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    raw = re.sub(r"</(p|div|tr|li|h[1-6]|table)>", "\n", raw, flags=re.I)
    text = _TAG_RE.sub(" ", raw)
    text = html_lib.unescape(text)
    text = _WS_RE.sub(" ", text)
    text = _MULTINL_RE.sub("\n\n", text)
    return text.strip()


def _find_section(
    text: str, starts: list[re.Pattern], ends: list[re.Pattern],
    min_len: int = 400, cap: int = 40000,
) -> str:
    # Among all "Item N + title" header matches, take the one that yields the
    # longest span to the next section header. This reliably skips the short
    # table-of-contents entries and lands on the real section body.
    best = ""
    for sre in starts:
        for m in sre.finditer(text):
            start = m.end()
            end = len(text)
            for ere in ends:
                em = ere.search(text, start)
                if em:
                    end = min(end, em.start())
            span = text[start:end].strip()
            if len(span) > len(best):
                best = span
    return best[:cap] if len(best) >= min_len else ""


def latest_filing(sub: dict, form: str = "10-K") -> Optional[tuple[str, str, str, str]]:
    """Return (filing_date, accession, primary_document, report_date) for the
    most recent filing of ``form``, or None."""
    recent = (sub.get("filings") or {}).get("recent") or {}
    forms = recent.get("form", [])
    accns = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    dates = recent.get("filingDate", [])
    reports = recent.get("reportDate", [])
    best: Optional[tuple[str, str, str, str]] = None
    for i, f in enumerate(forms):
        if f != form:
            continue
        fd = dates[i] if i < len(dates) else ""
        if best is None or (fd or "") > best[0]:
            best = (
                fd,
                accns[i] if i < len(accns) else "",
                docs[i] if i < len(docs) else "",
                reports[i] if i < len(reports) else "",
            )
    return best


def filing_url(cik: str, accession: str, primary_document: str) -> str:
    accn_nodash = accession.replace("-", "")
    cik_int = int(re.sub(r"\D", "", str(cik)) or "0")
    return f"{settings.sec_base_www}/Archives/edgar/data/{cik_int}/{accn_nodash}/{primary_document}"


def documents_for_company(
    client: SECClient,
    cik: str,
    company_name: Optional[str],
    form: str = "10-K",
    sections: Optional[list[str]] = None,
    force: bool = False,
) -> list[Document]:
    cik10 = client.pad_cik(cik)
    sub = client.submissions(cik)
    latest = latest_filing(sub, form)
    if not latest or not latest[2]:
        return []
    filing_date, accession, primary_doc, report_date = latest
    url = filing_url(cik10, accession, primary_doc)
    text = html_to_text(client.get_text(url, force=force))
    filed = _parse_date(filing_date)
    as_of = _parse_date(report_date) or filed

    out: list[Document] = []
    for name in sections or DEFAULT_SECTIONS:
        pats = SECTIONS.get(name)
        if not pats:
            continue
        starts = [re.compile(p, re.I) for p in pats[0]]
        ends = [re.compile(p, re.I) for p in pats[1]]
        body = _find_section(text, starts, ends)
        if not body:
            continue
        out.append(
            Document(
                id=f"{cik10}:{accession}:{name}".replace(" ", "_").replace("&", "and"),
                cik=cik10,
                company=company_name,
                title=f"{company_name} {form} — {name}",
                section=name,
                text=body,
                form=form,
                accession=accession,
                filed=filed,
                as_of=as_of,
                source_url=url,
                approved=True,
            )
        )

    if not out:  # fallback: whole filing as a single capped document
        out.append(
            Document(
                id=f"{cik10}:{accession}:full",
                cik=cik10,
                company=company_name,
                title=f"{company_name} {form}",
                section="Full Filing",
                text=text[:60000],
                form=form,
                accession=accession,
                filed=filed,
                as_of=as_of,
                source_url=url,
                approved=True,
            )
        )
    return out

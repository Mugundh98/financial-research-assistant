"""Split Documents into retrievable Chunks, preserving provenance.

Sentence-aware packing keeps chunks near a target size with a small overlap so
context isn't severed mid-thought. Every Chunk copies its parent Document's
provenance (source_url, accession, as_of, approved) so a retrieved chunk can be
cited directly.
"""
from __future__ import annotations

import re

from ..contracts.models import Chunk, Document

_WS = re.compile(r"\s+")
_SENT_SPLIT = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9(\"'])")


def _split_long(sentence: str, limit: int) -> list[str]:
    if len(sentence) <= limit:
        return [sentence]
    return [sentence[i : i + limit] for i in range(0, len(sentence), limit)]


def _sentences(text: str, hard_limit: int) -> list[str]:
    text = _WS.sub(" ", text).strip()
    if not text:
        return []
    out: list[str] = []
    for part in _SENT_SPLIT.split(text):
        part = part.strip()
        if part:
            out.extend(_split_long(part, hard_limit))
    return out


def _make_chunk(doc: Document, ordinal: int, text: str) -> Chunk:
    return Chunk(
        id=f"{doc.id}#{ordinal}",
        doc_id=doc.id,
        text=text,
        ordinal=ordinal,
        cik=doc.cik,
        company=doc.company,
        section=doc.section,
        form=doc.form,
        accession=doc.accession,
        filed=doc.filed,
        as_of=doc.as_of,
        source=doc.source,
        source_url=doc.source_url,
        approved=doc.approved,
    )


def chunk_document(doc: Document, target_chars: int = 1100, overlap_chars: int = 150) -> list[Chunk]:
    sentences = _sentences(doc.text, target_chars)
    chunks: list[Chunk] = []
    buf: list[str] = []
    size = 0
    ordinal = 0

    def flush() -> None:
        nonlocal buf, size, ordinal
        text = " ".join(buf).strip()
        if text:
            chunks.append(_make_chunk(doc, ordinal, text))
            ordinal += 1

    for sent in sentences:
        if buf and size + len(sent) + 1 > target_chars:
            flush()
            # start next window with a small overlapping tail
            carry: list[str] = []
            csize = 0
            for prev in reversed(buf):
                if csize + len(prev) > overlap_chars:
                    break
                carry.insert(0, prev)
                csize += len(prev) + 1
            buf, size = carry, csize
        buf.append(sent)
        size += len(sent) + 1
    flush()
    return chunks


def chunk_corpus(documents, target_chars: int = 1100, overlap_chars: int = 150) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in documents:
        chunks.extend(chunk_document(doc, target_chars, overlap_chars))
    return chunks

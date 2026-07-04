"""Basic text chunking utilities for local ingestion."""

from __future__ import annotations

import re

from app.research_document import DocumentChunk, ResearchDocument


def _estimate_tokens(text: str) -> int:
    """Estimate tokens cheaply for chunk sizing without a tokenizer dependency."""

    return max(1, len(re.findall(r"\S+", text)))


def chunk_document(
    document: ResearchDocument,
    max_words: int = 220,
    overlap_words: int = 40,
) -> list[DocumentChunk]:
    """Split a document into overlapping word chunks.

    This is intentionally simple and deterministic. Later milestones can replace
    it with structure-aware chunking for protocols, tables, images, and OneNote
    page blocks.
    """

    words = re.findall(r"\S+", document.content)
    if not words:
        return []

    if overlap_words >= max_words:
        raise ValueError("overlap_words must be smaller than max_words.")

    chunks: list[DocumentChunk] = []
    start = 0
    chunk_index = 0

    while start < len(words):
        end = min(start + max_words, len(words))
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words)
        chunks.append(
            DocumentChunk(
                id=f"{document.id}:chunk:{chunk_index}",
                document_id=document.id,
                chunk_index=chunk_index,
                text=chunk_text,
                token_estimate=_estimate_tokens(chunk_text),
            )
        )

        if end == len(words):
            break

        start = end - overlap_words
        chunk_index += 1

    return chunks

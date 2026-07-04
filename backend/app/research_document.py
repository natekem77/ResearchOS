"""Provider-agnostic research document models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResearchDocument:
    """A normalized research note from any notebook or document provider.

    Providers such as Markdown, OneNote, Notion, or Obsidian should map their
    native records into this model before storage, chunking, indexing, or AI use.
    """

    id: str
    provider: str
    source_id: str
    title: str
    content: str
    source_path: str | None = None
    source_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentChunk:
    """A searchable piece of a research document."""

    id: str
    document_id: str
    chunk_index: int
    text: str
    token_estimate: int

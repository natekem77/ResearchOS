"""Vector index abstraction for ResearchOS search."""

from __future__ import annotations

import hashlib
import logging
import math
from pathlib import Path
from typing import Protocol

import chromadb

from app.config import Settings, get_settings
from app.research_document import DocumentChunk, ResearchDocument

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class VectorIndex(Protocol):
    """Interface for document vector indexes."""

    def upsert_chunks(self, document: ResearchDocument, chunks: list[DocumentChunk]) -> None:
        """Store vector-searchable chunks."""

    def search(self, query: str, limit: int = 10) -> list[dict[str, object]]:
        """Search indexed chunks."""


def _hash_embedding(text: str, dimensions: int = 64) -> list[float]:
    """Create a deterministic local embedding for development.

    This is not a semantic model. It keeps the ChromaDB integration functional
    without API keys or model downloads while keyword search remains the primary
    no-AI fallback.
    """

    vector = [0.0] * dimensions
    for word in text.lower().split():
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector

    return [value / norm for value in vector]


class ChromaVectorIndex:
    """ChromaDB-backed vector index using deterministic local embeddings."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        persist_path = Path(self.settings.chroma_persist_directory)
        if not persist_path.is_absolute():
            persist_path = PROJECT_ROOT / persist_path
        persist_path.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(persist_path))
        self.collection = self.client.get_or_create_collection(
            name="researchos_chunks",
            metadata={"description": "ResearchOS local document chunks"},
        )

    def upsert_chunks(self, document: ResearchDocument, chunks: list[DocumentChunk]) -> None:
        """Store chunk vectors in ChromaDB."""

        if not chunks:
            return

        self.collection.upsert(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            embeddings=[_hash_embedding(chunk.text) for chunk in chunks],
            metadatas=[
                {
                    "document_id": document.id,
                    "title": document.title,
                    "provider": document.provider,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in chunks
            ],
        )

    def search(self, query: str, limit: int = 10) -> list[dict[str, object]]:
        """Search ChromaDB and return normalized result dictionaries."""

        try:
            result = self.collection.query(
                query_embeddings=[_hash_embedding(query)],
                n_results=limit,
            )
        except Exception as exc:
            logger.warning("Vector search failed; keyword fallback can still be used: %s", exc)
            return []

        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        normalized: list[dict[str, object]] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] or {}
            normalized.append(
                {
                    "document_id": metadata.get("document_id"),
                    "title": metadata.get("title"),
                    "provider": metadata.get("provider"),
                    "chunk_id": chunk_id,
                    "snippet": documents[index],
                    "score": distances[index] if index < len(distances) else None,
                    "source": "vector",
                }
            )

        return normalized

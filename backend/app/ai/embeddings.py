"""Provider-independent embeddings extension point."""

from __future__ import annotations


class EmbeddingService:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("Embeddings providers are registered through AIService in a later milestone.")


"""Document ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.chunking import chunk_document
from app.experiment_extraction import extract_experiment
from app.markdown_provider import load_markdown_folder
from app.storage import SQLiteStore
from app.vector_index import ChromaVectorIndex


@dataclass(frozen=True)
class IngestionResult:
    """Summary of an ingestion run."""

    provider: str
    documents_ingested: int
    chunks_indexed: int
    experiments_extracted: int


def ingest_markdown_folder(folder_path: str | Path) -> IngestionResult:
    """Load Markdown documents, store them in SQLite, and index their chunks."""

    documents = load_markdown_folder(folder_path)
    store = SQLiteStore()
    index = ChromaVectorIndex()

    chunk_count = 0
    experiment_count = 0
    for document in documents:
        chunks = chunk_document(document)
        store.upsert_document(document, chunks)
        index.upsert_chunks(document, chunks)
        chunk_count += len(chunks)

        experiment = extract_experiment(document)
        if experiment is not None:
            store.upsert_experiment(experiment)
            experiment_count += 1

    return IngestionResult(
        provider="markdown",
        documents_ingested=len(documents),
        chunks_indexed=chunk_count,
        experiments_extracted=experiment_count,
    )

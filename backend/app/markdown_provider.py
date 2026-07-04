"""Local Markdown folder provider for development and demos."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.research_document import ResearchDocument


def _extract_title(markdown: str, fallback: str) -> str:
    """Return the first Markdown H1 as title, or a filename fallback."""

    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip() or fallback

    return fallback


def _document_id_for_path(path: Path) -> str:
    """Build a stable provider-agnostic ID for a Markdown file path."""

    digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"markdown:{digest}"


def load_markdown_folder(folder_path: str | Path) -> list[ResearchDocument]:
    """Load all Markdown files from a local folder as ResearchDocuments."""

    folder = Path(folder_path).expanduser().resolve()
    if not folder.exists():
        raise FileNotFoundError(f"Markdown folder does not exist: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Markdown path is not a directory: {folder}")

    documents: list[ResearchDocument] = []
    for path in sorted(folder.rglob("*.md")):
        content = path.read_text(encoding="utf-8")
        stat = path.stat()
        documents.append(
            ResearchDocument(
                id=_document_id_for_path(path),
                provider="markdown",
                source_id=str(path),
                title=_extract_title(content, fallback=path.stem.replace("_", " ").title()),
                content=content,
                source_path=str(path),
                created_at=None,
                updated_at=str(int(stat.st_mtime)),
                metadata={"filename": path.name},
            )
        )

    return documents

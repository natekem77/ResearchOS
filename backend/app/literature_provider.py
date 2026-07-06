"""Local literature provider for paper notes and PDFs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.research_document import ResearchDocument

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAPER_DIRS = [
    PROJECT_ROOT / "samples" / "papers",
    PROJECT_ROOT / "data" / "papers",
]

KNOWN_COMPOUNDS = ["SAG", "BMP4", "DMSO"]
KNOWN_MARKERS = ["SIX6", "BRN3B", "DAPI", "PAX6", "VSX2", "RAX", "CRX", "OTX2"]
KNOWN_CELL_TYPES = ["retinal progenitor", "retinal ganglion cell", "photoreceptor", "organoid"]
KNOWN_METHODS = ["immunostaining", "confocal", "brightfield", "RNA-seq", "flow cytometry", "qPCR"]


def _document_id_for_path(path: Path) -> str:
    """Build a stable literature document ID for a local paper file."""

    digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"literature:{digest}"


def _read_pdf(path: Path) -> str:
    """Extract text from a PDF with pypdf."""

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF ingestion requires pypdf. Install backend requirements first.") from exc

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(page for page in pages if page.strip())


def _read_paper_text(path: Path) -> str:
    """Read a supported local literature file."""

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    return path.read_text(encoding="utf-8")


def _first_line_title(text: str, fallback: str) -> str:
    """Extract a title from metadata, Markdown heading, or first non-empty line."""

    title_match = re.search(r"^Title:\s*(.+)$", text, re.I | re.M)
    if title_match:
        return title_match.group(1).strip()
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped
    return fallback


def _metadata_value(text: str, label: str) -> str | None:
    """Extract a simple metadata value from text."""

    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, re.I | re.M)
    return match.group(1).strip() if match else None


def _abstract(text: str) -> str | None:
    """Extract an abstract section when a simple heading is present."""

    match = re.search(
        r"(?:^|\n)Abstract:?\s*\n?(.*?)(?=\n(?:Keywords?|Introduction|Methods?|Results?):|\Z)",
        text,
        re.I | re.S,
    )
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()[:1500] or None


def _terms(text: str, candidates: list[str]) -> list[str]:
    """Return known scientific terms present in text."""

    found = []
    for term in candidates:
        if re.search(rf"(?<![A-Za-z0-9-]){re.escape(term)}(?![A-Za-z0-9-])", text, re.I):
            found.append(term)
    return sorted(set(found))


def _genes(text: str) -> list[str]:
    """Extract likely gene or marker symbols from paper text."""

    symbols = re.findall(r"\b[A-Z][A-Z0-9]{2,6}\b", text)
    return sorted(set(symbol for symbol in symbols if symbol not in {"PDF", "DOI"}))[:25]


def _metadata(text: str, path: Path) -> dict[str, str]:
    """Extract basic literature metadata and entities."""

    doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, re.I)
    year_match = re.search(r"\b(19|20)\d{2}\b", text)
    metadata = {
        "title": _first_line_title(text, path.stem.replace("_", " ").title()),
        "authors": _metadata_value(text, "Authors") or "",
        "year": _metadata_value(text, "Year") or (year_match.group(0) if year_match else ""),
        "journal": _metadata_value(text, "Journal") or "",
        "doi": _metadata_value(text, "DOI") or (doi_match.group(0) if doi_match else ""),
        "abstract": _abstract(text) or "",
        "compounds": ", ".join(_terms(text, KNOWN_COMPOUNDS)),
        "markers": ", ".join(_terms(text, KNOWN_MARKERS)),
        "genes": ", ".join(_genes(text)),
        "cell_types": ", ".join(_terms(text, KNOWN_CELL_TYPES)),
        "methods": ", ".join(_terms(text, KNOWN_METHODS)),
        "filename": path.name,
    }
    return metadata


def load_literature_documents(paths: list[str | Path] | None = None) -> list[ResearchDocument]:
    """Load local paper files as provider-agnostic ResearchDocuments."""

    roots = [Path(path).expanduser().resolve() for path in (paths or DEFAULT_PAPER_DIRS)]
    files: list[Path] = []
    for root in roots:
        if root.exists() and root.is_dir():
            files.extend(path for path in root.rglob("*") if path.suffix.lower() in {".pdf", ".txt", ".md"})

    documents: list[ResearchDocument] = []
    for path in sorted(set(files)):
        text = _read_paper_text(path)
        if not text.strip():
            continue
        metadata = _metadata(text, path)
        stat = path.stat()
        documents.append(
            ResearchDocument(
                id=_document_id_for_path(path),
                provider="literature",
                source_id=str(path),
                title=metadata["title"],
                content=text,
                source_path=str(path),
                created_at=None,
                updated_at=str(int(stat.st_mtime)),
                metadata=metadata,
            )
        )
    return documents

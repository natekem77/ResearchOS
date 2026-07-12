"""Persistent storage helpers for experiment attachments."""

from __future__ import annotations

import hashlib
import mimetypes
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings


MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024

ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".xlsx",
    ".xls",
    ".csv",
    ".tsv",
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".tif",
    ".tiff",
    ".heic",
    ".webp",
}

SPREADSHEET_EXTENSIONS = {".xlsx", ".xls", ".csv", ".tsv"}


class AttachmentStorageError(ValueError):
    """Raised when an attachment cannot be safely stored."""


@dataclass(frozen=True)
class StoredAttachment:
    """Metadata returned after storing an uploaded attachment."""

    storage_path: str
    original_filename: str
    safe_filename: str
    mime_type: str
    file_extension: str
    size_bytes: int
    checksum: str


def sanitize_filename(filename: str) -> str:
    """Return a safe display/storage filename while preserving the extension."""

    name = Path(filename or "attachment").name.strip() or "attachment"
    stem = Path(name).stem.strip() or "attachment"
    suffix = Path(name).suffix.lower()
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "attachment"
    return f"{safe_stem}{suffix}"


def classify_attachment_type(filename: str, mime_type: str | None = None) -> str:
    """Map an uploaded filename to the UI attachment type."""

    extension = Path(filename or "").suffix.lower()
    if extension in {".xlsx", ".xls", ".csv", ".tsv"}:
        return "spreadsheet"
    if extension == ".pdf":
        return "pdf"
    if extension in {".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".heic", ".webp"}:
        return "image"
    if extension in {".docx", ".txt", ".md"}:
        return "document"
    if mime_type and mime_type.startswith("image/"):
        return "image"
    return "file"


class LocalAttachmentStorage:
    """Local development file provider.

    Stored paths are object keys relative to ``data/attachments`` so device
    temporary paths are never persisted as permanent attachment locations.
    """

    def __init__(self, settings: Settings) -> None:
        self.base_dir = Path(settings.data_dir).resolve() / "attachments"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, *, experiment_id: str, filename: str, data: bytes, mime_type: str | None = None) -> StoredAttachment:
        safe_filename = sanitize_filename(filename)
        extension = Path(safe_filename).suffix.lower()
        if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
            raise AttachmentStorageError(f"Unsupported attachment type: {extension or 'unknown'}")
        size_bytes = len(data)
        if size_bytes > MAX_ATTACHMENT_BYTES:
            raise AttachmentStorageError("Attachment is too large. Maximum size is 50 MB.")
        checksum = hashlib.sha256(data).hexdigest()
        object_key = f"{sanitize_filename(experiment_id)}/{uuid.uuid4().hex}_{safe_filename}"
        destination = self.base_dir / object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        resolved_mime = mime_type or mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
        return StoredAttachment(
            storage_path=object_key,
            original_filename=Path(filename or safe_filename).name,
            safe_filename=safe_filename,
            mime_type=resolved_mime,
            file_extension=extension,
            size_bytes=size_bytes,
            checksum=checksum,
        )

    def path_for(self, storage_path: str) -> Path:
        candidate = (self.base_dir / storage_path).resolve()
        if not str(candidate).startswith(str(self.base_dir)):
            raise AttachmentStorageError("Invalid attachment storage path.")
        return candidate

    def delete(self, storage_path: str | None) -> None:
        if not storage_path:
            return
        try:
            path = self.path_for(storage_path)
        except AttachmentStorageError:
            return
        if path.exists() and path.is_file():
            path.unlink()


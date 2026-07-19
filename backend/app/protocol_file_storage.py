"""Storage adapter for uploaded protocol source documents."""

from __future__ import annotations

from pathlib import Path

from app.attachment_storage import AttachmentStorageError, LocalAttachmentStorage, StoredAttachment, sanitize_filename
from app.config import Settings


class ProtocolFileStorage:
    """Protocol upload storage facade.

    The current provider uses local development storage through the existing
    attachment object-key scheme. Keeping this facade separate lets protocol
    files move to shared lab or object storage without changing API handlers.
    """

    def __init__(self, settings: Settings) -> None:
        self._storage = LocalAttachmentStorage(settings)

    def save(
        self,
        *,
        import_id: str,
        filename: str,
        data: bytes,
        mime_type: str | None = None,
    ) -> StoredAttachment:
        return self._storage.save(
            experiment_id=f"protocol-imports/{sanitize_filename(import_id)}",
            filename=filename,
            data=data,
            mime_type=mime_type,
        )

    def open(self, storage_path: str) -> Path:
        return self._storage.path_for(storage_path)

    def delete(self, storage_path: str | None) -> None:
        self._storage.delete(storage_path)

    def metadata(self, storage_path: str) -> dict[str, object]:
        path = self.open(storage_path)
        stat = path.stat()
        return {
            "storage_path": storage_path,
            "size_bytes": stat.st_size,
            "exists": path.exists(),
        }


__all__ = ["AttachmentStorageError", "ProtocolFileStorage"]

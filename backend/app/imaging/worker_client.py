"""Worker status facade used by FastAPI and Settings."""

from __future__ import annotations

from .service import ImagingService


def current_worker_status(service: ImagingService) -> dict:
    return service.worker_status()


"""Database-backed imaging job queue facade."""

from __future__ import annotations

from .service import ImagingService


def claim_and_run_once(service: ImagingService, worker_id: str) -> dict | None:
    return service.run_job_once(worker_id)


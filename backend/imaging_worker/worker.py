"""Database-backed Mundi imaging worker."""

from __future__ import annotations

import os
import time

from app.config import get_settings
from app.imaging import ImagingService


def run_once(worker_id: str | None = None) -> dict[str, object] | None:
    service = ImagingService(settings=get_settings())
    resolved_worker_id = worker_id or os.environ.get("MUNDI_IMAGING_WORKER_ID", "mundi-imaging-worker")
    service.record_worker_heartbeat(resolved_worker_id, "ready")
    return service.run_job_once(resolved_worker_id)


def main() -> None:
    service = ImagingService(settings=get_settings())
    worker_id = os.environ.get("MUNDI_IMAGING_WORKER_ID", "mundi-imaging-worker")
    poll_seconds = float(os.environ.get("MUNDI_IMAGING_JOB_POLL_SECONDS", "3"))
    print(f"Mundi imaging worker starting worker_id={worker_id}")
    while True:
        service.record_worker_heartbeat(worker_id, "ready")
        job = service.run_job_once(worker_id)
        if job is not None:
            print(f"processed {job['id']} status={job['status']}")
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()


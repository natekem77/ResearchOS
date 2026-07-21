#!/usr/bin/env python3
"""Run the local Mundi compute agent for approved analysis workflows."""

from __future__ import annotations

import argparse
import os
import platform
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.analysis import AnalysisService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Mundi lab compute agent.")
    parser.add_argument("--worker-id", default=os.environ.get("MUNDI_COMPUTE_WORKER_ID", "local-compute-agent"))
    parser.add_argument("--display-name", default=os.environ.get("MUNDI_COMPUTE_WORKER_NAME", "Local Compute Agent"))
    parser.add_argument("--once", action="store_true", help="Claim and execute at most one job.")
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("MUNDI_COMPUTE_JOB_POLL_SECONDS", "5")))
    args = parser.parse_args()

    service = AnalysisService()
    worker = service.register_worker(
        {
            "worker_id": args.worker_id,
            "display_name": args.display_name,
            "hostname": platform.node(),
            "operating_system": platform.platform(),
            "architecture": platform.machine(),
            "cpu_count": os.cpu_count(),
            "supported_runtimes": ["python"],
            "supported_workflows": ["bulk_rnaseq_validation_qc"],
            "software_versions": {"python": platform.python_version()},
            "status": "ready",
            "maximum_concurrent_jobs": 1,
        }
    )
    print(f"Compute worker ready: {worker['worker_id']} ({worker['display_name']})")
    print(f"Database: {service.store.path}")
    print(f"Approved roots: {[str(root) for root in service.allowed_roots]}")

    while True:
        service.record_worker_heartbeat(args.worker_id, {"status": "ready", "running_job_count": 0})
        job = service.run_claimed_job_once(args.worker_id)
        if job is not None:
            print(f"processed analysis job {job['id']} status={job['status']}")
        if args.once:
            break
        time.sleep(args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

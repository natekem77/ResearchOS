#!/usr/bin/env python3
"""Run the local Mundi compute agent for approved analysis workflows."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.analysis import AnalysisService  # noqa: E402


def _deseq2_versions() -> dict[str, str]:
    rscript = shutil.which("Rscript")
    if not rscript:
        return {}
    try:
        completed = subprocess.run(
            [
                rscript,
                "-e",
                (
                    "suppressPackageStartupMessages(library(DESeq2)); "
                    "cat(paste0('R=', as.character(getRversion()), '\\n')); "
                    "cat(paste0('DESeq2=', as.character(packageVersion('DESeq2')), '\\n')); "
                    "cat(paste0('Bioconductor=', as.character(BiocManager::version()), '\\n'))"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    versions: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        versions[key.strip()] = value.strip()
    return versions


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Mundi lab compute agent.")
    parser.add_argument("--worker-id", default=os.environ.get("MUNDI_COMPUTE_WORKER_ID", "local-compute-agent"))
    parser.add_argument("--display-name", default=os.environ.get("MUNDI_COMPUTE_WORKER_NAME", "Local Compute Agent"))
    parser.add_argument("--once", action="store_true", help="Claim and execute at most one job.")
    parser.add_argument("--poll-seconds", type=float, default=float(os.environ.get("MUNDI_COMPUTE_JOB_POLL_SECONDS", "5")))
    args = parser.parse_args()

    service = AnalysisService()
    supported_workflows = ["bulk_rnaseq_validation_qc"]
    supported_runtimes = ["python"]
    software_versions = {"python": platform.python_version()}
    deseq2_versions = _deseq2_versions()
    if deseq2_versions:
        supported_workflows.append("bulk_rnaseq_deseq2")
        supported_runtimes.extend(["r", "deseq2"])
        software_versions.update(deseq2_versions)

    worker_payload = {
        "worker_id": args.worker_id,
        "display_name": args.display_name,
        "hostname": platform.node(),
        "operating_system": platform.platform(),
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count(),
        "supported_runtimes": supported_runtimes,
        "supported_workflows": supported_workflows,
        "software_versions": software_versions,
        "status": "ready",
        "maximum_concurrent_jobs": 1,
    }
    worker = service.register_worker(worker_payload)
    print(f"Compute worker ready: {worker['worker_id']} ({worker['display_name']})")
    print(f"Supported workflows: {', '.join(supported_workflows)}")
    if "bulk_rnaseq_deseq2" not in supported_workflows:
        print("DESeq2 unavailable: install Rscript, DESeq2, and BiocManager to enable the workflow.")
    print(f"Database: {service.store.path}")
    print(f"Approved roots: {[str(root) for root in service.allowed_roots]}")

    while True:
        try:
            service.record_worker_heartbeat(args.worker_id, {"status": "ready", "running_job_count": 0})
            job = service.run_claimed_job_once(args.worker_id)
            if job is not None:
                print(f"processed analysis job {job['id']} status={job['status']}")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"compute worker loop error: {exc}", file=sys.stderr)
            time.sleep(args.poll_seconds)
            service = AnalysisService()
            service.register_worker(worker_payload)
        if args.once:
            break
        time.sleep(args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

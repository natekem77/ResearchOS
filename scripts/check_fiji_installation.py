#!/usr/bin/env python3
"""Run the same headless Fiji preview path used by the Mundi worker."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from imaging_worker.fiji_runner import FijiRunner, FijiRunnerError  # noqa: E402


def main() -> int:
    fiji_path = os.environ.get("MUNDI_FIJI_PATH", "")
    if not fiji_path:
        print("MUNDI_FIJI_PATH is not set.")
        return 1
    try:
        runner = FijiRunner(fiji_path, timeout_seconds=int(os.environ.get("MUNDI_IMAGING_JOB_TIMEOUT_SECONDS", "120")))
        print(f"Executable found: {Path(fiji_path)}")
        print("Launching Fiji...")
        print("Executing headless macro...")
        status = runner.health_check()
    except FijiRunnerError as exc:
        print(f"Health check FAILED: {exc}")
        return 1
    print("Preview generated")
    print(f"Fiji exited in {status['elapsed_ms']} ms")
    print("Health check PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


#!/usr/bin/env python3
"""Check Mundi Fiji/ImageJ worker prerequisites."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def main() -> int:
    fiji_path = os.environ.get("MUNDI_FIJI_PATH", "")
    if not fiji_path:
        print("MUNDI_FIJI_PATH is not set.")
        return 1
    path = Path(fiji_path)
    if not path.exists():
        print(f"Fiji executable not found: {path}")
        return 1
    print(f"Fiji executable found: {path}")
    try:
        result = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=20, check=False)
    except Exception as exc:
        print(f"Fiji launch failed: {exc}")
        return 1
    output = (result.stdout or result.stderr).strip()
    print(output or "Fiji launched but did not report a version.")
    return 0 if result.returncode == 0 else result.returncode


if __name__ == "__main__":
    raise SystemExit(main())


#!/usr/bin/env python3
"""Dry-run or repair local development notebook Delta records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.general_experiments import GeneralExperimentService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair canonical rich notebook Delta JSON in local SQLite data.")
    parser.add_argument("--dry-run", action="store_true", help="Report affected document IDs without rewriting data.")
    parser.add_argument("--apply", action="store_true", help="Rewrite records after creating a database backup.")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup creation when used with --apply.")
    args = parser.parse_args()

    service = GeneralExperimentService(settings=get_settings())
    result = service.repair_notebook_delta_records(
        dry_run=not args.apply,
        create_backup=not args.no_backup,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

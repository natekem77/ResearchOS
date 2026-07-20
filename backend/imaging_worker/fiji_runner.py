"""Fiji runner facade for validated Mundi imaging workflows.

The MVP worker currently records Fiji discovery and executes deterministic
validated workflow outputs through ``ImagingService``. Future versions should
replace the placeholder execution with generated server-side ImageJ macros from
the allowlisted workflow registry.
"""

from __future__ import annotations

from pathlib import Path


def fiji_executable_available(path: str | None) -> bool:
    return bool(path and Path(path).exists())


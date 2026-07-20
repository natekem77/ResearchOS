"""Metadata extraction hooks for imaging assets.

The MVP keeps proprietary metadata failures non-fatal. Bio-Formats/Fiji-backed
metadata extraction can replace this facade without changing upload handlers.
"""

from __future__ import annotations

from typing import Any


def unavailable_metadata() -> dict[str, Any]:
    return {"metadata_status": "unavailable"}


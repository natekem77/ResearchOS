"""Typed names for Mundi imaging records.

The SQLite-backed MVP returns plain dictionaries at the API boundary, but these
aliases keep service and worker code from growing provider-specific record
shapes in multiple places.
"""

from __future__ import annotations

from typing import Any

ImagingAssetPayload = dict[str, Any]
ImagingJobPayload = dict[str, Any]
ImagingOutputPayload = dict[str, Any]
ImagingMeasurementPayload = dict[str, Any]


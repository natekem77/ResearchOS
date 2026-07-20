"""Allowlisted imaging workflows for the Mundi/Fiji MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImagingWorkflow:
    stable_key: str
    name: str
    description: str
    workflow_version: str
    parameter_schema: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.stable_key,
            "stable_key": self.stable_key,
            "name": self.name,
            "description": self.description,
            "workflow_version": self.workflow_version,
            "parameter_schema": self.parameter_schema,
            "enabled": True,
        }


WORKFLOWS = [
    ImagingWorkflow(
        "generate_preview",
        "Generate Preview",
        "Create a visualization PNG without modifying the raw image.",
        "1.0.0",
    ),
    ImagingWorkflow(
        "max_intensity_projection",
        "Maximum Intensity Z-Projection",
        "Create a maximum-intensity projection TIFF and preview PNG.",
        "1.0.0",
        {
            "channel": {"type": "string", "default": "all"},
            "start_slice": {"type": "integer", "nullable": True},
            "end_slice": {"type": "integer", "nullable": True},
        },
    ),
    ImagingWorkflow(
        "split_channels",
        "Split Channels",
        "Export selected channels as separate TIFF files.",
        "1.0.0",
        {"channels": {"type": "array", "items": {"type": "integer"}, "default": []}},
    ),
    ImagingWorkflow(
        "background_subtraction",
        "Background Subtraction",
        "Run rolling-ball background subtraction on a selected channel.",
        "1.0.0",
        {
            "channel": {"type": "integer", "default": 1},
            "rolling_ball_radius": {"type": "number", "default": 50},
            "light_background": {"type": "boolean", "default": False},
        },
    ),
    ImagingWorkflow(
        "threshold_area_measurement",
        "Threshold and Area Measurement",
        "Create a mask, overlay, CSV, and structured area measurements.",
        "1.0.0",
        {
            "channel": {"type": "integer", "default": 1},
            "threshold_method": {"type": "string", "default": "Otsu"},
            "manual_lower": {"type": "number", "nullable": True},
            "manual_upper": {"type": "number", "nullable": True},
            "minimum_object_area": {"type": "number", "nullable": True},
            "use_pixel_calibration": {"type": "boolean", "default": True},
        },
    ),
]


def workflow_by_key(stable_key: str) -> ImagingWorkflow | None:
    return next((workflow for workflow in WORKFLOWS if workflow.stable_key == stable_key), None)


def list_workflows() -> list[dict[str, Any]]:
    return [workflow.payload() for workflow in WORKFLOWS]


def validate_parameters(stable_key: str, parameters: dict[str, Any]) -> dict[str, Any]:
    workflow = workflow_by_key(stable_key)
    if workflow is None:
        raise ValueError("Unknown imaging workflow.")
    schema = workflow.parameter_schema
    clean: dict[str, Any] = {}
    for name, value in parameters.items():
        if name not in schema:
            raise ValueError(f"Unsupported parameter for workflow: {name}")
        clean[name] = value
    for name, spec in schema.items():
        if name not in clean and "default" in spec:
            clean[name] = spec["default"]
    return clean


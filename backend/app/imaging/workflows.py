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

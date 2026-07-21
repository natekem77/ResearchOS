"""Allowlisted analysis workflow definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnalysisWorkflow:
    stable_key: str
    name: str
    description: str
    workflow_version: str
    category: str
    modality: str
    parameter_schema: dict[str, Any]
    resource_request: dict[str, Any]
    supported_runtimes: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.stable_key,
            "stable_key": self.stable_key,
            "name": self.name,
            "description": self.description,
            "workflow_version": self.workflow_version,
            "category": self.category,
            "modality": self.modality,
            "parameter_schema": self.parameter_schema,
            "resource_request": self.resource_request,
            "supported_runtimes": list(self.supported_runtimes),
            "enabled": True,
        }


BULK_VALIDATION_QC = AnalysisWorkflow(
    stable_key="bulk_rnaseq_validation_qc",
    name="Bulk RNA-seq Dataset Validation/QC",
    description=(
        "Validate a bulk count matrix and sample metadata, then register "
        "structured QC summaries without moving source data to the phone."
    ),
    workflow_version="1.0.0",
    category="Bulk RNA-seq",
    modality="bulk_rna_seq",
    parameter_schema={
        "type": "object",
        "properties": {
            "sample_id_column": {
                "type": "string",
                "default": "sample",
                "description": "Column in sample metadata containing count-matrix sample names.",
            },
            "group_column": {
                "type": "string",
                "default": "condition",
                "description": "Optional metadata column summarized for group sizes.",
            },
        },
        "additionalProperties": False,
    },
    resource_request={
        "cpu_cores": 1,
        "ram_gb": 2,
        "gpu": "none",
        "runtime_class": "short",
    },
    supported_runtimes=("python",),
)


SCAFFOLD_WORKFLOWS = (
    AnalysisWorkflow(
        stable_key="deseq2_differential_expression",
        name="DESeq2 Differential Expression",
        description="Scaffolded workflow definition for future DESeq2 execution.",
        workflow_version="0.1.0-scaffold",
        category="Bulk RNA-seq",
        modality="bulk_rna_seq",
        parameter_schema={"type": "object", "properties": {}, "additionalProperties": False},
        resource_request={"cpu_cores": 4, "ram_gb": 16, "gpu": "none", "runtime_class": "medium"},
        supported_runtimes=("r", "container"),
    ),
    AnalysisWorkflow(
        stable_key="scanpy_standard_pipeline",
        name="Scanpy Standard Pipeline",
        description="Scaffolded workflow definition for future single-cell processing.",
        workflow_version="0.1.0-scaffold",
        category="Single-cell RNA-seq",
        modality="single_cell_rna_seq",
        parameter_schema={"type": "object", "properties": {}, "additionalProperties": False},
        resource_request={"cpu_cores": 8, "ram_gb": 64, "gpu": "optional", "runtime_class": "long"},
        supported_runtimes=("python", "container"),
    ),
    AnalysisWorkflow(
        stable_key="beta_vae_expression_model",
        name="beta-VAE Expression Model",
        description="Scaffolded model workflow definition for future beta-VAE training.",
        workflow_version="0.1.0-scaffold",
        category="Models",
        modality="expression_matrix",
        parameter_schema={
            "type": "object",
            "properties": {
                "latent_dim": {"type": "integer", "minimum": 2, "maximum": 128},
                "beta": {"type": "number", "minimum": 0},
            },
            "additionalProperties": False,
        },
        resource_request={"cpu_cores": 4, "ram_gb": 16, "gpu": "optional", "runtime_class": "medium"},
        supported_runtimes=("python", "pytorch", "container"),
    ),
)


def list_workflows() -> list[dict[str, Any]]:
    return [workflow.payload() for workflow in (BULK_VALIDATION_QC, *SCAFFOLD_WORKFLOWS)]


def workflow_by_key(stable_key: str) -> dict[str, Any] | None:
    for workflow in list_workflows():
        if workflow["stable_key"] == stable_key:
            return workflow
    return None


def validate_parameters(stable_key: str, parameters: dict[str, Any] | None) -> dict[str, Any]:
    workflow = workflow_by_key(stable_key)
    if workflow is None:
        raise ValueError("Unknown analysis workflow.")
    raw = dict(parameters or {})
    allowed = set((workflow.get("parameter_schema", {}).get("properties") or {}).keys())
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"Unsupported workflow parameter: {unknown[0]}")
    if stable_key == BULK_VALIDATION_QC.stable_key:
        return {
            "sample_id_column": str(raw.get("sample_id_column") or "sample").strip() or "sample",
            "group_column": str(raw.get("group_column") or "condition").strip() or "condition",
        }
    return raw

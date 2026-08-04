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
        status = "installed" if self.stable_key == "bulk_rnaseq_validation_qc" else "available"
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
            "status": status,
            "installed": status == "installed",
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

BULK_DESEQ2 = AnalysisWorkflow(
    stable_key="bulk_rnaseq_deseq2",
    name="DESeq2 Differential Expression",
    description=(
        "Run an approved bulk RNA-seq differential-expression workflow using "
        "a metadata-driven design and contrast."
    ),
    workflow_version="1.0.0",
    category="Bulk RNA-seq",
    modality="bulk_rna_seq",
    parameter_schema={
        "type": "object",
        "properties": {
            "sample_id_column": {"type": "string", "default": "sample"},
            "design_factors": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["condition"],
            },
            "contrast_factor": {"type": "string", "default": "condition"},
            "numerator_level": {"type": "string"},
            "denominator_level": {"type": "string"},
            "min_total_count": {"type": "integer", "minimum": 0, "default": 10},
            "min_samples_expressing": {"type": "integer", "minimum": 1, "default": 2},
            "independent_filtering": {"type": "boolean", "default": True},
            "alpha": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.05},
            "lfc_threshold": {"type": "number", "minimum": 0, "default": 1.0},
            "padj_method": {"type": "string", "default": "BH"},
            "lfc_shrinkage": {
                "type": "string",
                "enum": ["none", "apeglm", "ashr", "normal"],
                "default": "none",
            },
            "transformed_count_method": {
                "type": "string",
                "enum": ["vst", "rlog", "none"],
                "default": "vst",
            },
            "top_gene_count": {"type": "integer", "minimum": 5, "maximum": 200, "default": 50},
            "sample_annotation_columns": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["condition"],
            },
            "exclude_samples": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
            },
        },
        "required": ["contrast_factor", "numerator_level", "denominator_level"],
        "additionalProperties": False,
    },
    resource_request={
        "cpu_cores": 4,
        "ram_gb": 16,
        "gpu": "none",
        "runtime_class": "medium",
    },
    supported_runtimes=("r", "deseq2"),
)

SINGLE_CELL_SCANPY_STANDARD = AnalysisWorkflow(
    stable_key="single_cell_scanpy_standard",
    name="Scanpy Standard Pipeline",
    description=(
        "Run an approved single-cell RNA-seq workflow with QC filtering, "
        "normalization, HVG selection, PCA, neighbors, Leiden clustering, "
        "UMAP, marker-gene ranking, and processed AnnData output."
    ),
    workflow_version="1.0.0",
    category="Single-cell RNA-seq",
    modality="single_cell_rna_seq",
    parameter_schema={
        "type": "object",
        "properties": {
            "min_genes_per_cell": {"type": "integer", "minimum": 0, "default": 200},
            "max_genes_per_cell": {"type": ["integer", "null"], "default": None},
            "min_counts_per_cell": {"type": ["integer", "null"], "default": None},
            "max_counts_per_cell": {"type": ["integer", "null"], "default": None},
            "max_percent_mito": {"type": ["number", "null"], "minimum": 0, "default": 20},
            "min_cells_per_gene": {"type": "integer", "minimum": 0, "default": 3},
            "target_sum": {"type": "integer", "minimum": 1, "default": 10000},
            "n_top_hvg": {"type": "integer", "minimum": 1, "default": 2000},
            "regress_percent_mito": {"type": "boolean", "default": False},
            "regress_total_counts": {"type": "boolean", "default": False},
            "scale_max_value": {"type": ["number", "null"], "default": 10},
            "n_pcs": {"type": "integer", "minimum": 2, "default": 30},
            "n_neighbors": {"type": "integer", "minimum": 2, "default": 15},
            "umap_min_dist": {"type": "number", "minimum": 0, "default": 0.5},
            "umap_spread": {"type": "number", "minimum": 0, "default": 1.0},
            "random_seed": {"type": "integer", "default": 0},
            "leiden_resolution": {"type": "number", "minimum": 0, "default": 0.5},
            "cluster_key": {"type": "string", "default": "leiden"},
            "marker_method": {
                "type": "string",
                "enum": ["wilcoxon", "t-test", "logreg"],
                "default": "wilcoxon",
            },
            "marker_top_n": {"type": "integer", "minimum": 1, "default": 100},
            "marker_padj_threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.05},
            "marker_min_logfc": {"type": "number", "minimum": 0, "default": 0.25},
        },
        "additionalProperties": False,
    },
    resource_request={
        "cpu_cores": 4,
        "ram_gb": 16,
        "gpu": "none",
        "runtime_class": "medium",
    },
    supported_runtimes=("python", "scanpy", "anndata", "scipy"),
)


SCAFFOLD_WORKFLOWS = (
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
    return [
        workflow.payload()
        for workflow in (
            BULK_VALIDATION_QC,
            BULK_DESEQ2,
            SINGLE_CELL_SCANPY_STANDARD,
            *SCAFFOLD_WORKFLOWS,
        )
    ]


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
    if stable_key == BULK_DESEQ2.stable_key:
        design_factors = [
            str(item).strip()
            for item in raw.get("design_factors", ["condition"])
            if str(item).strip()
        ]
        if not design_factors:
            raise ValueError("At least one design factor is required.")
        contrast_factor = str(raw.get("contrast_factor") or design_factors[-1]).strip()
        numerator = str(raw.get("numerator_level") or "").strip()
        denominator = str(raw.get("denominator_level") or "").strip()
        if not contrast_factor or not numerator or not denominator:
            raise ValueError("DESeq2 contrast factor, numerator level, and denominator level are required.")
        if numerator == denominator:
            raise ValueError("DESeq2 contrast levels must be different.")
        return {
            "sample_id_column": str(raw.get("sample_id_column") or "sample").strip() or "sample",
            "design_factors": design_factors,
            "design_formula": "~ " + " + ".join(design_factors),
            "contrast_factor": contrast_factor,
            "numerator_level": numerator,
            "denominator_level": denominator,
            "min_total_count": max(0, int(raw.get("min_total_count", 10))),
            "min_samples_expressing": max(1, int(raw.get("min_samples_expressing", 2))),
            "independent_filtering": bool(raw.get("independent_filtering", True)),
            "alpha": float(raw.get("alpha", 0.05)),
            "lfc_threshold": max(0.0, float(raw.get("lfc_threshold", 1.0))),
            "padj_method": str(raw.get("padj_method") or "BH"),
            "lfc_shrinkage": str(raw.get("lfc_shrinkage") or "none"),
            "transformed_count_method": str(raw.get("transformed_count_method") or "vst"),
            "top_gene_count": max(5, min(200, int(raw.get("top_gene_count", 50)))),
            "sample_annotation_columns": [
                str(item).strip()
                for item in raw.get("sample_annotation_columns", [contrast_factor])
                if str(item).strip()
            ],
            "exclude_samples": [
                str(item).strip()
                for item in raw.get("exclude_samples", [])
                if str(item).strip()
            ],
        }
    if stable_key == SINGLE_CELL_SCANPY_STANDARD.stable_key:
        def optional_int(name: str) -> int | None:
            value = raw.get(name)
            return None if value in {None, ""} else int(value)

        def optional_float(name: str) -> float | None:
            value = raw.get(name)
            return None if value in {None, ""} else float(value)

        marker_method = str(raw.get("marker_method") or "wilcoxon")
        if marker_method not in {"wilcoxon", "t-test", "logreg"}:
            raise ValueError("Unsupported Scanpy marker method.")
        return {
            "min_genes_per_cell": max(0, int(raw.get("min_genes_per_cell", 200))),
            "max_genes_per_cell": optional_int("max_genes_per_cell"),
            "min_counts_per_cell": optional_int("min_counts_per_cell"),
            "max_counts_per_cell": optional_int("max_counts_per_cell"),
            "max_percent_mito": optional_float("max_percent_mito") if "max_percent_mito" in raw else 20.0,
            "min_cells_per_gene": max(0, int(raw.get("min_cells_per_gene", 3))),
            "target_sum": max(1, int(raw.get("target_sum", 10000))),
            "n_top_hvg": max(1, int(raw.get("n_top_hvg", 2000))),
            "regress_percent_mito": bool(raw.get("regress_percent_mito", False)),
            "regress_total_counts": bool(raw.get("regress_total_counts", False)),
            "scale_max_value": optional_float("scale_max_value") if "scale_max_value" in raw else 10.0,
            "n_pcs": max(2, int(raw.get("n_pcs", 30))),
            "n_neighbors": max(2, int(raw.get("n_neighbors", 15))),
            "umap_min_dist": max(0.0, float(raw.get("umap_min_dist", 0.5))),
            "umap_spread": max(0.0, float(raw.get("umap_spread", 1.0))),
            "random_seed": int(raw.get("random_seed", 0)),
            "leiden_resolution": max(0.0, float(raw.get("leiden_resolution", 0.5))),
            "cluster_key": str(raw.get("cluster_key") or "leiden").strip() or "leiden",
            "marker_method": marker_method,
            "marker_top_n": max(1, int(raw.get("marker_top_n", 100))),
            "marker_padj_threshold": max(0.0, min(1.0, float(raw.get("marker_padj_threshold", 0.05)))),
            "marker_min_logfc": max(0.0, float(raw.get("marker_min_logfc", 0.25))),
        }
    return raw

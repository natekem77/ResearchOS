"""Experiment lifecycle rules and deterministic recommendations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


LIFECYCLE_STAGES = [
    "Planning",
    "Approved",
    "Running",
    "Waiting",
    "Imaging",
    "Analysis",
    "Writing",
    "Submitted",
    "Published",
    "Archived",
    "Cancelled",
]

ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    "Planning": ["Approved", "Cancelled", "Archived"],
    "Approved": ["Running", "Planning", "Cancelled", "Archived"],
    "Running": ["Waiting", "Imaging", "Analysis", "Cancelled"],
    "Waiting": ["Running", "Imaging", "Analysis", "Cancelled"],
    "Imaging": ["Analysis", "Waiting", "Writing", "Cancelled"],
    "Analysis": ["Writing", "Imaging", "Archived", "Cancelled"],
    "Writing": ["Submitted", "Analysis", "Archived", "Cancelled"],
    "Submitted": ["Published", "Writing", "Archived"],
    "Published": ["Archived"],
    "Archived": [],
    "Cancelled": ["Archived"],
}

COMPLETION_CRITERIA: dict[str, list[str]] = {
    "Planning": ["Objective, protocol, controls, and expected readouts are defined."],
    "Approved": ["PI or responsible scientist has reviewed the plan."],
    "Running": ["Experiment session is active or wet-lab work is underway."],
    "Waiting": ["Treatment, incubation, differentiation, or assay waiting period is in progress."],
    "Imaging": ["Images or microscopy assets are being collected or reviewed."],
    "Analysis": ["Quantitative analysis, statistics, or comparisons are underway."],
    "Writing": ["Notebook summary, figure text, or manuscript/grant text is being drafted."],
    "Submitted": ["Manuscript, report, or reviewed package has been submitted."],
    "Published": ["Final public or internal publication record exists."],
    "Archived": ["Experiment is complete or inactive and preserved for reference."],
    "Cancelled": ["Experiment has been intentionally stopped."],
}

RECOMMENDED_ACTIONS: dict[str, list[str]] = {
    "Planning": ["Define controls.", "Choose readouts.", "Create or link protocol.", "Start an experiment session when approved."],
    "Approved": ["Start the experiment session.", "Prepare assets and protocol checklist."],
    "Running": ["Record session notes.", "Capture treatments/media changes.", "Document deviations."],
    "Waiting": ["Set reminder for next time point.", "Prepare imaging or analysis plan."],
    "Imaging": ["Import images.", "Confirm marker/timepoint metadata.", "Link image assets to experiment."],
    "Analysis": ["Upload GraphPad/spreadsheet outputs.", "Run statistics interpretation.", "Compare with related experiments."],
    "Writing": ["Draft notebook summary.", "Review provenance.", "Prepare figures or literature comparison."],
    "Submitted": ["Track review status.", "Archive submission package."],
    "Published": ["Link publication.", "Archive final evidence package."],
    "Archived": ["No active next action."],
    "Cancelled": ["Record cancellation reason.", "Archive relevant notes/assets."],
}


@dataclass(frozen=True)
class LifecycleTransition:
    """One lifecycle transition request."""

    to_stage: str
    reason: str | None = None
    actor: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_stage(stage: str) -> str:
    """Normalize user-provided stage labels to canonical stage names."""

    for candidate in LIFECYCLE_STAGES:
        if candidate.lower() == stage.strip().lower():
            return candidate
    raise ValueError(f"Unknown lifecycle stage: {stage}")


def lifecycle_definition(stage: str) -> dict[str, Any]:
    """Return rules and guidance for one lifecycle stage."""

    normalized = normalize_stage(stage)
    return {
        "stage": normalized,
        "allowed_transitions": ALLOWED_TRANSITIONS[normalized],
        "completion_criteria": COMPLETION_CRITERIA[normalized],
        "recommended_next_actions": RECOMMENDED_ACTIONS[normalized],
    }


def validate_transition(from_stage: str, to_stage: str) -> tuple[str, str]:
    """Validate and normalize a lifecycle transition."""

    source = normalize_stage(from_stage)
    target = normalize_stage(to_stage)
    if target not in ALLOWED_TRANSITIONS[source]:
        allowed = ", ".join(ALLOWED_TRANSITIONS[source]) or "none"
        raise ValueError(f"Invalid lifecycle transition from {source} to {target}. Allowed transitions: {allowed}.")
    return source, target


def remaining_stages(stage: str) -> list[str]:
    """Return later canonical stages for workspace display."""

    normalized = normalize_stage(stage)
    index = LIFECYCLE_STAGES.index(normalized)
    return LIFECYCLE_STAGES[index + 1 :]


def recommended_actions_for_experiment(stage: str, experiment: dict[str, Any], assets: list[dict[str, Any]]) -> list[str]:
    """Return deterministic next actions using lifecycle stage and linked assets."""

    normalized = normalize_stage(stage)
    actions = list(RECOMMENDED_ACTIONS[normalized])
    has_graphpad = any(str(asset.get("provider")) == "graphpad" for asset in assets)
    has_statistics = any(isinstance(asset.get("metadata"), dict) and asset["metadata"].get("statistics") for asset in assets)
    has_images = any(str(asset.get("provider")) == "microscopy" or str(asset.get("asset_type")) in {"image", "microscopy"} for asset in assets)
    if normalized in {"Running", "Waiting", "Imaging"} and not has_images:
        actions.append("Import or link microscopy/image assets when imaging is complete.")
    if normalized in {"Analysis", "Writing"} and not has_graphpad:
        actions.append("Upload GraphPad analysis if quantitative comparison is expected.")
    if normalized in {"Analysis", "Writing"} and not has_statistics:
        actions.append("Complete statistics before making final claims.")
    if not experiment.get("conclusions") and normalized in {"Analysis", "Writing", "Submitted"}:
        actions.append("Add experiment conclusions before submission or archive.")
    return list(dict.fromkeys(actions))

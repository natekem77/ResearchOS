"""Generic ResearchOS workflow engine.

The first workflow is the Experiment Workflow, but the data model is generic so
future workflows can cover manuscripts, grants, sequencing analyses, protocol
development, collaborations, and publication work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.storage import SQLiteStore


@dataclass(frozen=True)
class WorkflowTransition:
    """One requested workflow stage transition."""

    to_stage: str
    reason: str | None = None
    actor: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowState:
    """Persisted workflow state for one subject."""

    workflow_id: str
    workflow_type: str
    subject_id: str
    current_stage: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowHistory:
    """One workflow history event."""

    history_id: str
    workflow_id: str
    from_stage: str | None
    to_stage: str
    reason: str | None = None
    actor: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None


@dataclass(frozen=True)
class WorkflowStage:
    """Definition for one stage in a workflow."""

    name: str
    description: str
    allowed_transitions: list[str]
    completion_criteria: list[str]
    required_assets: list[str]
    recommended_actions: list[str]
    blocking_issues: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "allowed_transitions": self.allowed_transitions,
            "completion_criteria": self.completion_criteria,
            "required_assets": self.required_assets,
            "recommended_actions": self.recommended_actions,
            "blocking_issues": self.blocking_issues,
        }


@dataclass(frozen=True)
class WorkflowDefinition:
    """Definition for one workflow type."""

    workflow_type: str
    name: str
    description: str
    stages: list[WorkflowStage]
    future_subjects: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "workflow_type": self.workflow_type,
            "name": self.name,
            "description": self.description,
            "stages": [stage.as_dict() for stage in self.stages],
            "future_subjects": self.future_subjects,
        }


EXPERIMENT_STAGE_NAMES = [
    "Planning",
    "Approved",
    "Running",
    "Media Changes",
    "Treatment",
    "Waiting",
    "Imaging",
    "Quantification",
    "Statistics",
    "Interpretation",
    "Writing",
    "Submitted",
    "Published",
    "Archived",
    "Cancelled",
]


def _stage(
    name: str,
    description: str,
    allowed: list[str],
    criteria: list[str],
    required_assets: list[str],
    actions: list[str],
    blocking: list[str],
) -> WorkflowStage:
    return WorkflowStage(
        name=name,
        description=description,
        allowed_transitions=allowed,
        completion_criteria=criteria,
        required_assets=required_assets,
        recommended_actions=actions,
        blocking_issues=blocking,
    )


EXPERIMENT_WORKFLOW = WorkflowDefinition(
    workflow_type="experiment",
    name="Experiment Workflow",
    description="Canonical ResearchOS workflow for planning, running, analyzing, interpreting, and writing up laboratory experiments.",
    future_subjects=[
        "Protocol Development",
        "RNA-seq Analysis",
        "Microscopy Analysis",
        "Manuscript",
        "Grant",
        "Patent",
        "Publication",
    ],
    stages=[
        _stage(
            "Planning",
            "Define the scientific question, protocol, controls, expected readouts, and required assets.",
            ["Approved", "Cancelled", "Archived"],
            ["Objective, controls, protocol, and expected readouts are defined."],
            ["protocol_or_plan"],
            ["Define controls.", "Choose readouts.", "Create or link protocol.", "Request approval when the plan is ready."],
            ["Missing objective, controls, protocol, or readout plan."],
        ),
        _stage(
            "Approved",
            "Plan has been reviewed and is ready to run.",
            ["Running", "Planning", "Cancelled", "Archived"],
            ["PI or responsible scientist has reviewed the plan."],
            [],
            ["Start an experiment session.", "Prepare protocol checklist and materials."],
            ["Approval or protocol readiness is not documented."],
        ),
        _stage(
            "Running",
            "Wet-lab work is actively underway.",
            ["Media Changes", "Treatment", "Waiting", "Imaging", "Quantification", "Cancelled"],
            ["Session notes, observations, and deviations are captured."],
            ["notebook_observation"],
            ["Record session notes.", "Capture treatments/media changes.", "Document deviations."],
            ["No notebook observations or session notes are linked."],
        ),
        _stage(
            "Media Changes",
            "Media-change work is underway or needs documentation.",
            ["Treatment", "Waiting", "Running", "Cancelled"],
            ["Media change timing, composition, and deviations are recorded."],
            ["notebook_observation"],
            ["Record media composition.", "Capture timing.", "Move to treatment or waiting when complete."],
            ["Media change details are not captured in linked notes."],
        ),
        _stage(
            "Treatment",
            "Treatment, compound exposure, or perturbation has been applied.",
            ["Waiting", "Imaging", "Quantification", "Running", "Cancelled"],
            ["Treatment groups, concentrations, controls, and timing are documented."],
            ["notebook_observation"],
            ["Confirm treatment schedule.", "Record concentrations and controls.", "Set next time point."],
            ["Treatment schedule or controls are incomplete."],
        ),
        _stage(
            "Waiting",
            "Treatment, incubation, differentiation, or assay waiting period is in progress.",
            ["Imaging", "Quantification", "Treatment", "Running", "Cancelled"],
            ["Next time point or decision point is known."],
            [],
            ["Set reminder for next time point.", "Prepare imaging or quantification plan."],
            ["Next time point is not documented."],
        ),
        _stage(
            "Imaging",
            "Images or microscopy assets are being collected or reviewed.",
            ["Quantification", "Statistics", "Interpretation", "Waiting", "Cancelled"],
            ["Images are imported, linked, and have marker/timepoint metadata when available."],
            ["microscopy_image"],
            ["Import images.", "Confirm marker/timepoint metadata.", "Link image assets to experiment."],
            ["No microscopy/image assets are linked."],
        ),
        _stage(
            "Quantification",
            "Raw imaging or experimental readouts are being quantified.",
            ["Statistics", "Interpretation", "Imaging", "Cancelled"],
            ["Quantification output is saved as GraphPad, spreadsheet, CSV, or equivalent asset."],
            ["quantitative_asset"],
            ["Import quantification spreadsheet.", "Link GraphPad or exported CSV.", "Check group/sample labels."],
            ["No quantitative asset is linked."],
        ),
        _stage(
            "Statistics",
            "Statistical testing or quantitative interpretation is underway.",
            ["Interpretation", "Quantification", "Writing", "Cancelled"],
            ["Statistical tests, p-values, sample sizes, and limitations are captured when available."],
            ["statistics"],
            ["Run GraphPad/statistics interpretation.", "Review sample sizes.", "Check multiple-comparison correction."],
            ["No parsed statistics are linked."],
        ),
        _stage(
            "Interpretation",
            "Results are being interpreted against notebook observations, assets, statistics, and literature.",
            ["Writing", "Statistics", "Quantification", "Cancelled"],
            ["Observed findings, limitations, and uncertainties are written down."],
            ["statistics", "notebook_observation"],
            ["Review statistical significance.", "Write interpretation notes.", "Compare with related literature."],
            ["Statistics or interpretation notes are missing."],
        ),
        _stage(
            "Writing",
            "Notebook summary, manuscript text, figure text, grant text, or report text is being drafted.",
            ["Submitted", "Interpretation", "Statistics", "Archived", "Cancelled"],
            ["Summary, conclusions, provenance, and limitations are reviewed."],
            ["conclusion"],
            ["Draft notebook summary.", "Review provenance.", "Prepare figures or literature comparison."],
            ["Conclusions are not captured."],
        ),
        _stage(
            "Submitted",
            "A manuscript, report, or reviewed package has been submitted.",
            ["Published", "Writing", "Archived"],
            ["Submission package and date are recorded."],
            ["submission_record"],
            ["Track review status.", "Archive submission package."],
            ["Submission record is not linked."],
        ),
        _stage(
            "Published",
            "Final public or internal publication record exists.",
            ["Archived"],
            ["Publication or final report is linked."],
            ["publication_record"],
            ["Link publication.", "Archive final evidence package."],
            ["Publication record is not linked."],
        ),
        _stage(
            "Archived",
            "Experiment is complete or inactive and preserved for reference.",
            [],
            ["Experiment evidence package is preserved."],
            [],
            ["No active next action."],
            [],
        ),
        _stage(
            "Cancelled",
            "Experiment has been intentionally stopped.",
            ["Archived"],
            ["Cancellation reason and any reusable evidence are recorded."],
            ["cancellation_reason"],
            ["Record cancellation reason.", "Archive relevant notes/assets."],
            ["Cancellation reason is not recorded."],
        ),
    ],
)


WORKFLOW_DEFINITIONS = {
    EXPERIMENT_WORKFLOW.workflow_type: EXPERIMENT_WORKFLOW,
}


class WorkflowEngine:
    """Generic workflow orchestration service."""

    def __init__(self, store: SQLiteStore):
        self.store = store

    def definitions(self) -> list[dict[str, Any]]:
        """Return all workflow definitions currently registered."""

        return [definition.as_dict() for definition in WORKFLOW_DEFINITIONS.values()]

    def list_workflows(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        """Return workflows for all extracted experiments."""

        return [
            self.workflow_for_experiment(experiment)
            for experiment in self.store.list_experiments(workspace_id=workspace_id)
        ]

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        """Return one workflow payload."""

        state = self.store.get_workflow_state(workflow_id)
        if state is None:
            return None
        experiment = self.store.get_experiment(str(state.get("subject_id"))) if state.get("workflow_type") == "experiment" else None
        assets = self.store.list_assets_for_experiment(experiment) if experiment else []
        return self._payload(state, experiment or {}, assets)

    def workflow_for_experiment_reference(self, experiment_reference: str) -> dict[str, Any] | None:
        """Return or create the workflow for an experiment reference."""

        experiment = self.store.find_experiment_by_reference(experiment_reference)
        if experiment is None:
            return None
        return self.workflow_for_experiment(experiment)

    def workflow_for_experiment(self, experiment: dict[str, Any]) -> dict[str, Any]:
        """Return or create the workflow for one extracted experiment."""

        workflow_id = experiment_workflow_id(str(experiment["id"]))
        state = self.store.get_or_create_workflow_state(
            workflow_id=workflow_id,
            workflow_type="experiment",
            subject_id=str(experiment["id"]),
            initial_stage="Planning",
            metadata={"human_experiment_id": experiment.get("experiment_id")},
            owner_user_id=str(experiment.get("owner_user_id") or "") or None,
            created_by=str(experiment.get("created_by") or experiment.get("owner_user_id") or "") or None,
            workspace_id=str(experiment.get("workspace_id") or "") or None,
        )
        assets = self.store.list_assets_for_experiment(experiment)
        return self._payload(state, experiment, assets)

    def transition(
        self,
        workflow_id: str,
        to_stage: str,
        reason: str | None = None,
        actor: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Transition one workflow after validating its definition."""

        state = self.store.get_workflow_state(workflow_id)
        if state is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        workflow_type = str(state["workflow_type"])
        source = normalize_stage(workflow_type, str(state["current_stage"]))
        target = normalize_stage(workflow_type, to_stage)
        allowed = stage_definition(workflow_type, source).allowed_transitions
        if target not in allowed:
            allowed_text = ", ".join(allowed) or "none"
            raise ValueError(f"Invalid workflow transition from {source} to {target}. Allowed transitions: {allowed_text}.")
        self.store.transition_workflow(
            workflow_id=workflow_id,
            to_stage=target,
            reason=reason,
            actor=actor,
            metadata=metadata or {},
        )
        payload = self.get_workflow(workflow_id)
        if payload is None:
            raise ValueError(f"Workflow not found after transition: {workflow_id}")
        return payload

    def add_note(
        self,
        workflow_id: str,
        note: str,
        actor: str | None = None,
        stage: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one workflow note."""

        state = self.store.get_workflow_state(workflow_id)
        if state is None:
            raise ValueError(f"Workflow not found: {workflow_id}")
        note_stage = normalize_stage(str(state["workflow_type"]), stage or str(state["current_stage"]))
        self.store.add_workflow_note(
            workflow_id=workflow_id,
            stage=note_stage,
            note=note,
            actor=actor,
            metadata=metadata or {},
        )
        payload = self.get_workflow(workflow_id)
        if payload is None:
            raise ValueError(f"Workflow not found after note: {workflow_id}")
        return payload

    def stage_counts(self) -> dict[str, int]:
        """Return experiment workflow counts grouped by stage."""

        return self.store.workflow_stage_counts("experiment")

    def _payload(
        self,
        state: dict[str, Any],
        experiment: dict[str, Any],
        assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        workflow_type = str(state["workflow_type"])
        current_stage = normalize_stage(workflow_type, str(state["current_stage"]))
        definition = WORKFLOW_DEFINITIONS[workflow_type]
        current_definition = stage_definition(workflow_type, current_stage)
        completed = completed_stages(workflow_type, current_stage)
        remaining = remaining_stages(workflow_type, current_stage)
        blocking = blocking_issues_for_experiment(current_stage, experiment, assets, self.store.workflow_notes(str(state["workflow_id"])))
        actions = recommended_actions_for_experiment_workflow(current_stage, experiment, assets, blocking)
        return {
            "workflow_id": state["workflow_id"],
            "workflow_type": workflow_type,
            "subject_id": state["subject_id"],
            "subject": experiment,
            "current_stage": current_stage,
            "stage": current_definition.as_dict(),
            "definition": definition.as_dict(),
            "progress": workflow_progress(workflow_type, current_stage),
            "completed_stages": completed,
            "remaining_stages": remaining,
            "suggested_next_actions": actions,
            "recommended_next_actions": actions,
            "blocking_issues": blocking,
            "history": self.store.workflow_history(str(state["workflow_id"])),
            "notes": self.store.workflow_notes(str(state["workflow_id"])),
            "metadata": state.get("metadata") or {},
        }


def experiment_workflow_id(experiment_id: str) -> str:
    """Return stable workflow ID for an experiment."""

    return f"workflow:experiment:{experiment_id}"


def normalize_stage(workflow_type: str, stage: str) -> str:
    """Normalize a workflow stage label to canonical capitalization."""

    for candidate in stage_names(workflow_type):
        if candidate.lower() == stage.strip().lower():
            return candidate
    raise ValueError(f"Unknown {workflow_type} workflow stage: {stage}")


def stage_names(workflow_type: str) -> list[str]:
    """Return canonical stage names for a workflow type."""

    return [stage.name for stage in WORKFLOW_DEFINITIONS[workflow_type].stages]


def stage_definition(workflow_type: str, stage: str) -> WorkflowStage:
    """Return one stage definition."""

    normalized = normalize_stage(workflow_type, stage)
    for candidate in WORKFLOW_DEFINITIONS[workflow_type].stages:
        if candidate.name == normalized:
            return candidate
    raise ValueError(f"Unknown {workflow_type} workflow stage: {stage}")


def completed_stages(workflow_type: str, stage: str) -> list[str]:
    names = stage_names(workflow_type)
    normalized = normalize_stage(workflow_type, stage)
    index = names.index(normalized)
    return names[:index]


def remaining_stages(workflow_type: str, stage: str) -> list[str]:
    names = stage_names(workflow_type)
    normalized = normalize_stage(workflow_type, stage)
    index = names.index(normalized)
    return names[index + 1 :]


def workflow_progress(workflow_type: str, stage: str) -> dict[str, Any]:
    names = stage_names(workflow_type)
    normalized = normalize_stage(workflow_type, stage)
    index = names.index(normalized)
    active_stages = [name for name in names if name not in {"Archived", "Cancelled"}]
    denominator = max(len(active_stages) - 1, 1)
    numerator = min(index, denominator)
    return {
        "current_index": index,
        "total_stages": len(names),
        "percent": round((numerator / denominator) * 100, 1),
    }


def recommended_actions_for_experiment_workflow(
    stage: str,
    experiment: dict[str, Any],
    assets: list[dict[str, Any]],
    blocking_issues: list[str] | None = None,
) -> list[str]:
    """Return deterministic workflow actions using current evidence."""

    normalized = normalize_stage("experiment", stage)
    actions = list(stage_definition("experiment", normalized).recommended_actions)
    if has_images(assets) and not has_graphpad_or_quantitative_assets(assets):
        actions.append("Run GraphPad analysis or import a quantification spreadsheet.")
    if has_graphpad_or_quantitative_assets(assets) and not has_notebook_observation(experiment):
        actions.append("Complete notebook observations before interpretation.")
    if has_statistics(assets) and normalized in {"Statistics", "Interpretation"}:
        actions.append("Review statistical significance and limitations.")
    if not experiment.get("conclusions") and normalized in {"Interpretation", "Writing", "Submitted"}:
        actions.append("Write observed conclusions before advancing.")
    for issue in blocking_issues or []:
        if "No parsed statistics" in issue:
            actions.append("Complete statistics before making final claims.")
        if "No microscopy" in issue:
            actions.append("Import or link microscopy/image assets.")
    return list(dict.fromkeys(actions))


def blocking_issues_for_experiment(
    stage: str,
    experiment: dict[str, Any],
    assets: list[dict[str, Any]],
    notes: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Detect missing evidence for the current experiment workflow stage."""

    normalized = normalize_stage("experiment", stage)
    issues: list[str] = []
    if normalized in {"Running", "Media Changes", "Treatment", "Interpretation"} and not has_notebook_observation(experiment, notes):
        issues.append("No notebook observations are linked to the current workflow stage.")
    if normalized == "Imaging" and not has_images(assets):
        issues.append("No microscopy/image assets are linked.")
    if normalized == "Quantification" and not has_graphpad_or_quantitative_assets(assets):
        issues.append("No GraphPad, spreadsheet, or quantitative asset is linked.")
    if normalized in {"Statistics", "Interpretation", "Writing"} and not has_statistics(assets):
        issues.append("No parsed statistics are linked.")
    if normalized in {"Writing", "Submitted"} and not experiment.get("conclusions"):
        issues.append("No extracted conclusions are captured.")
    if normalized == "Treatment" and not (experiment.get("treatments") or experiment.get("compounds")):
        issues.append("Treatment groups or compounds are not captured.")
    return list(dict.fromkeys(issues))


def has_images(assets: list[dict[str, Any]]) -> bool:
    return any(str(asset.get("provider")) == "microscopy" or str(asset.get("asset_type")) in {"image", "microscopy"} for asset in assets)


def has_graphpad_or_quantitative_assets(assets: list[dict[str, Any]]) -> bool:
    return any(str(asset.get("provider")) in {"graphpad", "spreadsheet"} or str(asset.get("asset_type")) in {"graphpad", "spreadsheet", "csv"} for asset in assets)


def has_statistics(assets: list[dict[str, Any]]) -> bool:
    return any(isinstance(asset.get("metadata"), dict) and bool(asset["metadata"].get("statistics")) for asset in assets)


def has_notebook_observation(experiment: dict[str, Any], notes: list[dict[str, Any]] | None = None) -> bool:
    return bool(experiment.get("notes") or experiment.get("conclusions") or notes)

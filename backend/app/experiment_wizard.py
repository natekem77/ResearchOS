"""New Experiment Wizard service.

The wizard creates standard ResearchOS objects instead of introducing a
parallel planning database: a ResearchDocument, an Experiment, an Experiment
Workflow, an optional pending notebook draft, and an optional active session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from app.chunking import chunk_document
from app.experiments import Experiment
from app.research_document import ResearchDocument
from app.storage import SQLiteStore
from app.workflow_engine import WorkflowEngine


@dataclass(frozen=True)
class ExperimentWizardPayload:
    """Validated creation payload from a guided experiment wizard."""

    title: str
    experiment_id: str
    project: str | None = None
    workspace: str | None = None
    principal_investigator: str | None = None
    researcher: str | None = None
    date: str | None = None
    notes: str | None = None
    protocol_mode: str = "select_existing"
    protocol_id: str | None = None
    protocol_title: str | None = None
    protocol_notes: str | None = None
    cell_line: str | None = None
    organoid_batch: str | None = None
    treatments: list[dict[str, Any]] = field(default_factory=list)
    compounds: list[str] = field(default_factory=list)
    concentrations: list[str] = field(default_factory=list)
    timepoints: list[str] = field(default_factory=list)
    replicates: str | None = None
    controls: list[str] = field(default_factory=list)
    readouts: list[str] = field(default_factory=list)
    markers: list[str] = field(default_factory=list)
    microscopy: bool = False
    graphpad: bool = False
    rnaseq: bool = False
    flow_cytometry: bool = False
    other_readouts: str | None = None
    milestones: list[dict[str, Any]] = field(default_factory=list)
    create_notebook_draft: bool = True
    start_session: bool = False


class ExperimentWizardService:
    """Create a planned experiment from wizard inputs."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def create(
        self,
        payload: ExperimentWizardPayload,
        *,
        owner_user_id: str | None = None,
        created_by: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Create ResearchOS planning records for one experiment."""

        now = datetime.now(timezone.utc).isoformat()
        document_id = f"document:wizard:{uuid4().hex[:16]}"
        experiment_internal_id = f"experiment:{uuid4().hex[:16]}"
        markdown = self._markdown(payload)
        document = ResearchDocument(
            id=document_id,
            provider="wizard",
            source_id=payload.experiment_id,
            title=payload.title,
            content=markdown,
            created_at=now,
            updated_at=now,
            metadata={
                "experiment_id": payload.experiment_id,
                "project": payload.project or "",
                "principal_investigator": payload.principal_investigator or "",
                "researcher": payload.researcher or "",
                "protocol_id": payload.protocol_id or "",
                "protocol_title": payload.protocol_title or "",
                "wizard": "new_experiment",
            },
        )
        self.store.upsert_document(document, chunk_document(document), workspace_id=workspace_id)

        experiment = Experiment(
            id=experiment_internal_id,
            source_document_id=document_id,
            source_provider="wizard",
            title=payload.title,
            experiment_id=payload.experiment_id,
            date=payload.date or date.today().isoformat(),
            researcher=payload.researcher,
            cell_line=payload.cell_line,
            organoid_batch=payload.organoid_batch,
            compounds=_unique([*payload.compounds, *[str(item.get("compound") or "") for item in payload.treatments]]),
            treatments=_unique([_treatment_label(item) for item in payload.treatments]),
            concentrations=_unique([*payload.concentrations, *[str(item.get("concentration") or "") for item in payload.treatments]]),
            time_points=_unique(payload.timepoints),
            markers=_unique(payload.markers),
            antibodies=[],
            imaging_methods=_unique(["Microscopy"] if payload.microscopy else []),
            sequencing=_unique(["RNA-seq"] if payload.rnaseq else []),
            notes=payload.notes,
            conclusions="Planned experiment created from the ResearchOS New Experiment Wizard.",
        )
        self.store.upsert_experiment(experiment)
        experiment_record = self.store.get_experiment(experiment_internal_id)
        if experiment_record is None:
            raise RuntimeError("Experiment was not saved.")

        workflow = WorkflowEngine(self.store).workflow_for_experiment(experiment_record)
        self.store.add_workflow_note(
            workflow_id=str(workflow["workflow_id"]),
            stage="Planning",
            note="Experiment plan created from the New Experiment Wizard.",
            actor=created_by or owner_user_id or "ResearchOS",
            metadata={
                "source": "new_experiment_wizard",
                "controls": payload.controls,
                "readouts": payload.readouts,
                "milestones": payload.milestones,
            },
        )
        workflow = WorkflowEngine(self.store).workflow_for_experiment(experiment_record)

        pending_entry: dict[str, Any] | None = None
        if payload.create_notebook_draft:
            pending_entry = self.store.save_pending_entry(
                entry_id=None,
                title=f"{payload.experiment_id} planning draft",
                experiment_id=payload.experiment_id,
                template="retinal_organoid" if payload.organoid_batch else "general_experiment",
                structured=self._structured(payload),
                markdown=markdown,
                status="draft",
                owner_user_id=owner_user_id,
                created_by=created_by,
                workspace_id=workspace_id,
            )

        session: dict[str, Any] | None = None
        if payload.start_session:
            session = self.store.start_session(
                experiment_id=payload.experiment_id,
                notes=f"Started from New Experiment Wizard: {payload.title}",
                owner_user_id=owner_user_id,
                created_by=created_by,
                workspace_id=workspace_id,
            )

        return {
            "experiment": experiment_record,
            "workflow": workflow,
            "document": {
                "id": document.id,
                "title": document.title,
                "provider": document.provider,
            },
            "pending_entry": pending_entry,
            "session": session,
            "markdown": markdown,
            "copilot": self._copilot(payload),
            "message": "Experiment plan created. OneNote write-back remains disabled until approved.",
        }

    def _structured(self, payload: ExperimentWizardPayload) -> dict[str, Any]:
        return {
            "title": payload.title,
            "experiment_id": payload.experiment_id,
            "project": payload.project,
            "workspace": payload.workspace,
            "principal_investigator": payload.principal_investigator,
            "researcher": payload.researcher,
            "date": payload.date,
            "protocol": {
                "mode": payload.protocol_mode,
                "id": payload.protocol_id,
                "title": payload.protocol_title,
                "notes": payload.protocol_notes,
            },
            "experimental_design": {
                "cell_line": payload.cell_line,
                "organoid_batch": payload.organoid_batch,
                "treatments": payload.treatments,
                "compounds": payload.compounds,
                "concentrations": payload.concentrations,
                "timepoints": payload.timepoints,
                "replicates": payload.replicates,
                "controls": payload.controls,
            },
            "expected_readouts": {
                "readouts": payload.readouts,
                "markers": payload.markers,
                "microscopy": payload.microscopy,
                "graphpad": payload.graphpad,
                "rnaseq": payload.rnaseq,
                "flow_cytometry": payload.flow_cytometry,
                "other": payload.other_readouts,
            },
            "timeline": payload.milestones,
            "notes": payload.notes,
        }

    def _markdown(self, payload: ExperimentWizardPayload) -> str:
        lines = [
            f"# {payload.title}",
            "",
            "## Experiment Information",
            f"- Experiment ID: {payload.experiment_id}",
            f"- Project: {payload.project or 'TBD'}",
            f"- Workspace: {payload.workspace or 'Current ResearchOS workspace'}",
            f"- Principal investigator: {payload.principal_investigator or 'TBD'}",
            f"- Researcher: {payload.researcher or 'TBD'}",
            f"- Date: {payload.date or date.today().isoformat()}",
            "",
            "## Protocol",
            f"- Mode: {payload.protocol_mode}",
            f"- Protocol: {payload.protocol_title or payload.protocol_id or 'TBD'}",
            f"- Notes: {payload.protocol_notes or 'None'}",
            "",
            "## Experimental Design",
            f"- Cell line: {payload.cell_line or 'TBD'}",
            f"- Organoid batch: {payload.organoid_batch or 'TBD'}",
            f"- Compounds: {_join(payload.compounds)}",
            f"- Concentrations: {_join(payload.concentrations)}",
            f"- Timepoints: {_join(payload.timepoints)}",
            f"- Replicates: {payload.replicates or 'TBD'}",
            f"- Controls: {_join(payload.controls)}",
            "",
            "## Treatments",
        ]
        if payload.treatments:
            lines.extend(f"- {_treatment_label(item)}" for item in payload.treatments)
        else:
            lines.append("- TBD")
        lines.extend(
            [
                "",
                "## Expected Readouts",
                f"- Readouts: {_join(payload.readouts)}",
                f"- Markers/entities: {_join(payload.markers)}",
                f"- Microscopy: {_yes_no(payload.microscopy)}",
                f"- GraphPad: {_yes_no(payload.graphpad)}",
                f"- RNA-seq: {_yes_no(payload.rnaseq)}",
                f"- Flow cytometry: {_yes_no(payload.flow_cytometry)}",
                f"- Other: {payload.other_readouts or 'None'}",
                "",
                "## Timeline",
            ]
        )
        if payload.milestones:
            lines.extend(f"- {item.get('label') or 'Milestone'}: {item.get('detail') or item.get('date') or 'TBD'}" for item in payload.milestones)
        else:
            lines.append("- TBD")
        lines.extend(
            [
                "",
                "## ResearchOS Copilot Notes",
                *[f"- {item}" for item in self._copilot(payload)["suggestions"]],
                "",
                "## Notes",
                payload.notes or "No additional notes.",
                "",
                "## OneNote Status",
                "OneNote write-back is intentionally disabled until IT approves create/write permissions.",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    def _copilot(self, payload: ExperimentWizardPayload) -> dict[str, Any]:
        warnings: list[str] = []
        suggestions: list[str] = []
        related_previous_experiments: list[dict[str, Any]] = []

        if not payload.controls:
            warnings.append("No controls were specified.")
            suggestions.append("Add at least one negative or vehicle control before running the experiment.")
        if not payload.replicates:
            warnings.append("Replicate count is missing.")
            suggestions.append("Define biological and technical replicate counts before data collection.")
        if not payload.readouts and not payload.markers:
            warnings.append("Expected readouts are incomplete.")
            suggestions.append("Add measurable readouts so analysis can be planned upfront.")
        if payload.graphpad and not payload.replicates:
            suggestions.append("GraphPad analysis will be more interpretable if replicate counts are defined now.")

        terms = {term.lower() for term in [*payload.compounds, *payload.markers, payload.cell_line or "", payload.organoid_batch or ""] if term}
        for experiment in self.store.list_experiments():
            text = " ".join(
                [
                    str(experiment.get("title") or ""),
                    str(experiment.get("experiment_id") or ""),
                    " ".join(str(item) for item in experiment.get("compounds") or []),
                    " ".join(str(item) for item in experiment.get("markers") or []),
                    str(experiment.get("cell_line") or ""),
                    str(experiment.get("organoid_batch") or ""),
                ]
            ).lower()
            if terms and any(term in text for term in terms):
                related_previous_experiments.append(
                    {
                        "id": experiment.get("id"),
                        "title": experiment.get("title"),
                        "experiment_id": experiment.get("experiment_id"),
                    }
                )
            if len(related_previous_experiments) >= 5:
                break

        return {
            "potential_protocol_issues": warnings,
            "suggestions": suggestions or ["Plan is ready for review before running."],
            "missing_controls": [] if payload.controls else ["controls"],
            "suggested_readouts": [] if payload.readouts or payload.markers else ["microscopy", "quantification", "statistics"],
            "related_previous_experiments": related_previous_experiments,
            "ai_used": False,
            "provider": "local",
        }


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = value.strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            output.append(clean)
    return output


def _join(values: list[str]) -> str:
    return ", ".join(_unique(values)) if values else "TBD"


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _treatment_label(item: dict[str, Any]) -> str:
    compound = str(item.get("compound") or "").strip()
    concentration = str(item.get("concentration") or "").strip()
    timepoint = str(item.get("timepoint") or "").strip()
    notes = str(item.get("notes") or "").strip()
    parts = [part for part in [compound, concentration, timepoint, notes] if part]
    return " / ".join(parts) if parts else ""

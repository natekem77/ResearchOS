"""Research Copilot synthesis for Experiment Workspaces.

The Copilot never creates new experimental observations. It reorganizes facts
already present in an Experiment Workspace and marks speculative content as
suggested or inferred.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from app.ai_providers import AIProvider, AIProviderError, get_ai_provider
from app.config import Settings, get_settings


@dataclass
class ResearchCopilotService:
    """Build provenance-backed Copilot sections from a workspace payload."""

    settings: Settings | None = None
    ai_provider_factory: Callable[[Settings], AIProvider] = get_ai_provider

    def build(self, workspace: dict[str, Any], use_ai: bool = True) -> dict[str, Any]:
        """Return structured Copilot sections for an Experiment Workspace."""

        resolved_settings = self.settings or get_settings()
        experiment = workspace.get("experiment") if isinstance(workspace.get("experiment"), dict) else {}
        provenance = workspace.get("provenance") if isinstance(workspace.get("provenance"), list) else []
        sections = {
            "key_findings": self._key_findings(workspace, experiment, provenance),
            "potential_concerns": self._potential_concerns(workspace, provenance),
            "suggested_follow_up_experiments": self._follow_ups(workspace, experiment, provenance),
            "related_experiments": self._related_experiments(workspace, provenance),
            "related_literature": self._related_literature(workspace, provenance),
            "experimental_gaps": self._experimental_gaps(workspace, experiment, provenance),
            "potential_manuscript_statements": self._manuscript_statements(workspace, experiment, provenance),
            "grant_proposal_ideas": self._grant_ideas(workspace, experiment, provenance),
            "questions_worth_investigating": self._questions(workspace, experiment, provenance),
        }
        copilot = {
            "provider": "local-fallback",
            "principles": [
                "Observed statements come from extracted experiments, notebook records, statistics, or source documents.",
                "Inferred statements describe ResearchOS links across existing records.",
                "Suggested statements are hypotheses or next steps, not observations.",
                "Literature-supported statements are derived from linked literature records.",
            ],
            "sections": sections,
            "natural_summary": self._local_summary(experiment, sections),
        }
        if use_ai:
            ai_summary = self._ai_summary(resolved_settings, experiment, sections)
            if ai_summary:
                copilot["provider"] = ai_summary["provider"]
                copilot["natural_summary"] = ai_summary["text"]
            elif resolved_settings.ai_provider.lower().strip() not in {"", "none"}:
                copilot["ai_error"] = "AI provider was configured but unavailable; using deterministic local Copilot summary."
        return copilot

    def _key_findings(
        self,
        workspace: dict[str, Any],
        experiment: dict[str, Any],
        provenance: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        statements: list[dict[str, Any]] = []
        experiment_prov = _matching_provenance(provenance, "experiment")
        observed_added = False
        if experiment.get("conclusions"):
            statements.append(
                _statement(
                    str(experiment["conclusions"]),
                    "observed",
                    experiment_prov,
                )
            )
            observed_added = True
        compounds = workspace.get("compounds") or []
        markers = workspace.get("markers") or []
        if compounds or markers:
            statements.append(
                _statement(
                    f"Workspace links compounds {', '.join(map(str, compounds)) or 'none'} and markers {', '.join(map(str, markers)) or 'none'}.",
                    "inferred",
                    _matching_provenance(provenance, "entity"),
                )
            )
        for item in _statistic_interpretations(workspace)[:3]:
            statements.append(_statement(item, "observed", _matching_provenance(provenance, "statistics")))
            observed_added = True
        memory = workspace.get("scientific_memory") if isinstance(workspace.get("scientific_memory"), dict) else {}
        similar = memory.get("most_similar_experiments") if isinstance(memory.get("most_similar_experiments"), list) else []
        if similar:
            closest = similar[0]
            closest_experiment = closest.get("experiment") if isinstance(closest, dict) else {}
            if isinstance(closest_experiment, dict):
                statements.append(
                    _statement(
                        f"Scientific Memory links this experiment to {closest_experiment.get('experiment_id') or closest_experiment.get('title') or closest_experiment.get('id')} with similarity score {closest.get('similarity_score')}.",
                        "inferred",
                        _matching_provenance(provenance, "experiment"),
                    )
                )
        for item in (workspace.get("conclusions") or {}).get("referenced_from_literature", [])[:3]:
            statements.append(_statement(str(item), "literature-supported", _matching_provenance(provenance, "literature")))
        if not observed_added:
            statements.append(_statement("No explicit observed findings have been extracted yet.", "observed", experiment_prov))
        return statements

    def _potential_concerns(self, workspace: dict[str, Any], provenance: list[dict[str, Any]]) -> list[dict[str, Any]]:
        concerns = []
        experiment = workspace.get("experiment") if isinstance(workspace.get("experiment"), dict) else {}
        workflow = _workspace_workflow(workspace)
        current_stage = str(workflow.get("current_stage") or "")
        if not workspace.get("statistics"):
            concerns.append("No parsed statistics are linked to this workspace.")
        if not workspace.get("literature"):
            concerns.append("No literature references are linked through shared entities.")
        if not workspace.get("microscopy"):
            concerns.append("No microscopy/image assets are linked to this workspace.")
        for issue in workflow.get("blocking_issues", [])[:5]:
            concerns.append(str(issue))
        if current_stage in {"Analysis", "Quantification", "Statistics", "Interpretation", "Writing"} and workspace.get("microscopy") and not workspace.get("statistics"):
            concerns.append("Experiment has images but no GraphPad/statistics analysis linked yet.")
        if workspace.get("graphpad") and not _has_notebook_observation(workspace, experiment={}):
            concerns.append("Experiment has GraphPad assets but no notebook observations in the workspace.")
        if current_stage in {"Analysis", "Statistics", "Interpretation", "Writing"} and not workspace.get("statistics"):
            concerns.append(f"Lifecycle stage is {current_stage}, but no statistics are linked yet.")
        if current_stage == "Imaging" and not workspace.get("microscopy"):
            concerns.append("Lifecycle stage is Imaging, but no microscopy/image assets are linked yet.")
        concerns.extend(str(item) for item in workspace.get("limitations", [])[:3])
        return [_statement(item, "inferred", _matching_provenance(provenance, None)) for item in _unique(concerns)]

    def _follow_ups(
        self,
        workspace: dict[str, Any],
        experiment: dict[str, Any],
        provenance: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        compounds = workspace.get("compounds") or experiment.get("compounds") or []
        markers = workspace.get("markers") or experiment.get("markers") or []
        workflow = _workspace_workflow(workspace)
        suggestions = []
        for action in workflow.get("recommended_next_actions", [])[:4]:
            suggestions.append(str(action))
        if workspace.get("microscopy") and not workspace.get("graphpad"):
            suggestions.append("Run GraphPad analysis.")
        if workspace.get("graphpad") and not _has_notebook_observation(workspace, experiment):
            suggestions.append("Complete notebook observations.")
        if workspace.get("statistics") and workflow.get("current_stage") in {"Statistics", "Interpretation"}:
            suggestions.append("Review statistical significance.")
        if compounds and markers:
            suggestions.append(f"Repeat or extend {', '.join(map(str, compounds))} conditions with planned readouts for {', '.join(map(str, markers))}.")
        if workspace.get("statistics"):
            suggestions.append("Validate the linked quantitative trends with an independently planned replicate set.")
        else:
            suggestions.append("Add a quantitative analysis plan before interpreting treatment effects.")
        if workspace.get("microscopy"):
            suggestions.append("Pair image review with blinded quantification and source file provenance.")
        return [_statement(item, "suggested", _matching_provenance(provenance, None)) for item in suggestions]

    def _related_experiments(self, workspace: dict[str, Any], provenance: list[dict[str, Any]]) -> list[dict[str, Any]]:
        related = workspace.get("related_experiments") if isinstance(workspace.get("related_experiments"), list) else []
        statements = [
            _statement(
                str(item.get("experiment_id") or item.get("title") or item.get("id")),
                "inferred",
                _matching_provenance(provenance, "entity"),
            )
            for item in related[:6]
            if isinstance(item, dict)
        ]
        memory = workspace.get("scientific_memory") if isinstance(workspace.get("scientific_memory"), dict) else {}
        for item in (memory.get("most_similar_experiments") or [])[:4]:
            if not isinstance(item, dict):
                continue
            experiment = item.get("experiment") if isinstance(item.get("experiment"), dict) else {}
            similarities = ", ".join(str(value) for value in item.get("key_similarities", [])[:3])
            differences = ", ".join(str(value) for value in item.get("important_differences", [])[:2])
            statements.append(
                _statement(
                    f"{experiment.get('experiment_id') or experiment.get('title') or experiment.get('id')} resembles this workspace ({item.get('similarity_score')}); similarities: {similarities or 'metadata overlap'}; differences: {differences or 'not detected'}.",
                    "inferred",
                    _matching_provenance(provenance, "experiment"),
                )
            )
        return statements

    def _related_literature(self, workspace: dict[str, Any], provenance: list[dict[str, Any]]) -> list[dict[str, Any]]:
        literature = workspace.get("literature") if isinstance(workspace.get("literature"), list) else []
        return [
            _statement(
                str(item.get("title") or item.get("id")),
                "literature-supported",
                _matching_provenance(provenance, "literature"),
            )
            for item in literature[:6]
            if isinstance(item, dict)
        ] or [_statement("No related literature is currently linked.", "inferred", _matching_provenance(provenance, None))]

    def _experimental_gaps(
        self,
        workspace: dict[str, Any],
        experiment: dict[str, Any],
        provenance: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        gaps = []
        for field, label in [
            ("date", "Experiment date"),
            ("researcher", "Researcher"),
            ("cell_line", "Cell line"),
            ("organoid_batch", "Organoid batch"),
        ]:
            if not experiment.get(field):
                gaps.append(f"{label} is not captured in the extracted experiment metadata.")
        if not experiment.get("time_points"):
            gaps.append("Time points are not captured in the extracted experiment metadata.")
        if not experiment.get("concentrations"):
            gaps.append("Concentrations are not captured in the extracted experiment metadata.")
        workflow = _workspace_workflow(workspace)
        if not workflow.get("history"):
            gaps.append("Lifecycle history has not been initialized for this experiment.")
        return [_statement(item, "inferred", _matching_provenance(provenance, "experiment")) for item in gaps] or [
            _statement("No obvious metadata gaps were detected in the core extracted fields.", "inferred", _matching_provenance(provenance, "experiment"))
        ]

    def _manuscript_statements(
        self,
        workspace: dict[str, Any],
        experiment: dict[str, Any],
        provenance: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        statements = []
        if experiment.get("conclusions"):
            statements.append(f"In {experiment.get('experiment_id') or experiment.get('id')}, the extracted note reports: {experiment['conclusions']}")
        for item in _statistic_interpretations(workspace)[:2]:
            statements.append(f"Linked quantitative analysis reports: {item}")
        if not statements:
            statements.append("The current workspace does not yet contain enough observed evidence for a manuscript claim.")
        return [_statement(item, "suggested", _matching_provenance(provenance, "experiment")) for item in statements]

    def _grant_ideas(
        self,
        workspace: dict[str, Any],
        experiment: dict[str, Any],
        provenance: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        entities = [str(item) for item in [*(workspace.get("compounds") or []), *(workspace.get("markers") or [])] if item]
        if entities:
            ideas = [f"Use ResearchOS-linked evidence around {', '.join(entities[:5])} to motivate a focused validation aim."]
        else:
            ideas = ["Use the workspace gaps to define a reproducible data organization and validation aim."]
        if workspace.get("literature"):
            ideas.append("Frame the next aim around where local observations align or diverge from linked literature.")
        return [_statement(item, "suggested", _matching_provenance(provenance, None)) for item in ideas]

    def _questions(
        self,
        workspace: dict[str, Any],
        experiment: dict[str, Any],
        provenance: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        compounds = workspace.get("compounds") or experiment.get("compounds") or []
        markers = workspace.get("markers") or experiment.get("markers") or []
        questions = []
        if compounds:
            questions.append(f"Do {', '.join(map(str, compounds))} effects replicate across independent batches?")
        if markers:
            questions.append(f"Are {', '.join(map(str, markers))} changes consistent across imaging, statistics, and notebook observations?")
        if workspace.get("literature"):
            questions.append("Where do local results agree or diverge from linked literature?")
        workflow = _workspace_workflow(workspace)
        next_actions = workflow.get("recommended_next_actions") if isinstance(workflow.get("recommended_next_actions"), list) else []
        if next_actions:
            questions.append(f"What evidence is needed to move from {workflow.get('current_stage', 'the current stage')} to the next workflow stage?")
        if not questions:
            questions.append("What experimental variables should be captured before scientific interpretation?")
        return [_statement(item, "suggested", _matching_provenance(provenance, None)) for item in questions]

    def _local_summary(self, experiment: dict[str, Any], sections: dict[str, list[dict[str, Any]]]) -> str:
        label = experiment.get("experiment_id") or experiment.get("title") or experiment.get("id") or "This workspace"
        findings = " ".join(item["text"] for item in sections["key_findings"][:2])
        concerns = " ".join(item["text"] for item in sections["potential_concerns"][:2])
        return f"{label}: {findings} Concerns or gaps: {concerns}"

    def _ai_summary(self, settings: Settings, experiment: dict[str, Any], sections: dict[str, list[dict[str, Any]]]) -> dict[str, str] | None:
        try:
            provider = self.ai_provider_factory(settings)
            prompt = (
                "Write a concise ResearchOS Copilot summary using only the JSON sections below. "
                "Never invent observations. Label observations, inferences, suggestions, and literature-supported points clearly.\n\n"
                f"Experiment: {json.dumps(experiment, default=str)}\n"
                f"Sections: {json.dumps(sections, default=str)}"
            )
            return {"provider": provider.provider_name, "text": provider.chat(prompt)}
        except AIProviderError:
            return None


def _statement(text: str, category: str, provenance: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "text": text,
        "category": category,
        "provenance": provenance or [{"fact": "workspace", "source": "research_copilot", "provider": "ResearchOS"}],
    }


def _workspace_lifecycle(workspace: dict[str, Any]) -> dict[str, Any]:
    lifecycle = workspace.get("lifecycle")
    return lifecycle if isinstance(lifecycle, dict) else {}


def _workspace_workflow(workspace: dict[str, Any]) -> dict[str, Any]:
    workflow = workspace.get("workflow")
    if isinstance(workflow, dict):
        return workflow
    return _workspace_lifecycle(workspace)


def _has_notebook_observation(workspace: dict[str, Any], experiment: dict[str, Any]) -> bool:
    workflow = workspace.get("workflow") if isinstance(workspace.get("workflow"), dict) else {}
    return bool(experiment.get("notes") or experiment.get("conclusions") or workspace.get("notebook_entries") or workflow.get("notes"))


def _matching_provenance(provenance: list[dict[str, Any]], fact: str | None) -> list[dict[str, Any]]:
    if not provenance:
        return []
    if fact is None:
        return provenance[:3]
    matches = [item for item in provenance if str(item.get("fact") or "") == fact]
    return matches[:3] or provenance[:1]


def _statistic_interpretations(workspace: dict[str, Any]) -> list[str]:
    output = []
    for asset in workspace.get("statistics") or []:
        if not isinstance(asset, dict):
            continue
        interpretation = asset.get("interpretation") if isinstance(asset.get("interpretation"), dict) else {}
        summary = interpretation.get("summary") if isinstance(interpretation, dict) else None
        if summary:
            output.append(str(summary))
        results = interpretation.get("results") if isinstance(interpretation, dict) else []
        for result in results[:2] if isinstance(results, list) else []:
            if isinstance(result, dict) and result.get("interpretation"):
                output.append(str(result["interpretation"]))
        compact = asset.get("compact_summary") if isinstance(asset.get("compact_summary"), dict) else {}
        if compact.get("short_interpretation"):
            output.append(str(compact["short_interpretation"]))
    return _unique(output)


def _unique(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        output.append(cleaned)
    return output

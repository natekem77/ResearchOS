"""Experiment comparison helpers for ResearchOS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai_providers import AIProviderError, get_ai_provider
from app.config import Settings, get_settings

COMPARISON_FIELDS = [
    "title",
    "date",
    "researcher",
    "cell_line",
    "organoid_batch",
    "compounds",
    "treatments",
    "concentrations",
    "time_points",
    "markers",
    "imaging_methods",
    "sequencing",
    "notes",
    "conclusions",
]


@dataclass(frozen=True)
class ExperimentComparison:
    """Structured side-by-side experiment comparison."""

    experiment_ids: list[str]
    shared_features: dict[str, Any]
    differences: dict[str, dict[str, Any]]
    likely_scientific_interpretation: str
    limitations: list[str]
    source_experiment_records: list[dict[str, Any]]
    ai_used: bool
    provider: str


def _normalize_value(value: Any) -> Any:
    """Normalize experiment field values for comparison."""

    if isinstance(value, list):
        return sorted(str(item) for item in value if item)
    if value is None:
        return None
    return str(value)


def _shared_list_values(experiments: list[dict[str, Any]], field: str) -> list[str]:
    """Return shared values for list fields."""

    sets = [set(_normalize_value(experiment.get(field)) or []) for experiment in experiments]
    if not sets:
        return []
    return sorted(set.intersection(*sets))


def compare_experiments(
    experiments: list[dict[str, Any]],
    settings: Settings | None = None,
    use_ai: bool = True,
) -> ExperimentComparison:
    """Compare structured experiment records and optionally add AI narrative."""

    if len(experiments) < 2:
        raise ValueError("Select at least two experiments to compare.")

    resolved_settings = settings or get_settings()
    shared: dict[str, Any] = {}
    differences: dict[str, dict[str, Any]] = {}

    for field in COMPARISON_FIELDS:
        values_by_experiment = {
            str(experiment["id"]): _normalize_value(experiment.get(field))
            for experiment in experiments
        }
        values = list(values_by_experiment.values())

        if all(isinstance(value, list) for value in values):
            shared_values = _shared_list_values(experiments, field)
            if shared_values:
                shared[field] = shared_values
            if any(set(value or []) != set(shared_values) for value in values):
                differences[field] = values_by_experiment
            continue

        unique_values = {value for value in values if value not in (None, "")}
        if len(unique_values) == 1 and all(value not in (None, "") for value in values):
            shared[field] = next(iter(unique_values))
        elif unique_values or any(value in (None, "") for value in values):
            differences[field] = values_by_experiment

    interpretation = _local_interpretation(experiments, shared, differences)
    limitations = [
        "Comparison uses extracted structured fields and may miss details not captured by extraction.",
        "Source notes should be reviewed before making experimental decisions.",
    ]
    ai_used = False
    provider_name = "local-fallback"

    if use_ai:
        try:
            provider = get_ai_provider(settings=resolved_settings)
            interpretation = provider.chat(_comparison_prompt(experiments, shared, differences))
            ai_used = True
            provider_name = provider.provider_name
        except AIProviderError as exc:
            limitations.append(f"AI comparison narrative was not used: {exc}")

    return ExperimentComparison(
        experiment_ids=[str(experiment["id"]) for experiment in experiments],
        shared_features=shared,
        differences=differences,
        likely_scientific_interpretation=interpretation,
        limitations=limitations,
        source_experiment_records=experiments,
        ai_used=ai_used,
        provider=provider_name,
    )


def _local_interpretation(
    experiments: list[dict[str, Any]],
    shared: dict[str, Any],
    differences: dict[str, dict[str, Any]],
) -> str:
    """Create a readable local scientific interpretation."""

    titles = [str(experiment.get("title") or experiment.get("experiment_id") or experiment["id"]) for experiment in experiments]
    pieces = [f"Compared {len(experiments)} experiments: {', '.join(titles)}."]

    shared_markers = shared.get("markers")
    if shared_markers:
        pieces.append(f"They share marker(s): {', '.join(shared_markers)}.")
    shared_compounds = shared.get("compounds")
    if shared_compounds:
        pieces.append(f"They share compound(s): {', '.join(shared_compounds)}.")

    for field in ["compounds", "treatments", "concentrations", "time_points", "markers", "imaging_methods"]:
        if field in differences:
            pieces.append(f"The main difference includes {field.replace('_', ' ')}.")

    conclusions = [str(experiment.get("conclusions")) for experiment in experiments if experiment.get("conclusions")]
    if conclusions:
        pieces.append("Conclusions differ or complement each other: " + " ".join(conclusions))

    return " ".join(pieces)


def _comparison_prompt(
    experiments: list[dict[str, Any]],
    shared: dict[str, Any],
    differences: dict[str, dict[str, Any]],
) -> str:
    """Build an AI prompt for optional comparison narrative."""

    return (
        "Compare these scientific experiments using only the structured data below. "
        "Be concise, cite uncertainty, and avoid inventing results.\n\n"
        f"Experiments:\n{experiments}\n\n"
        f"Shared features:\n{shared}\n\n"
        f"Differences:\n{differences}"
    )

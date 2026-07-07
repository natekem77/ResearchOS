"""Scientific reasoning engine for ResearchOS.

This module collects local ResearchOS evidence across documents, experiments,
assets, statistics, literature, and timelines, then produces a structured,
deterministic reasoning response. If an AI provider is configured, the same
evidence package can be used for synthesis without changing the local evidence
collection path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.ai_providers import AIProviderError, get_ai_provider
from app.config import Settings, get_settings
from app.experiment_comparison import compare_experiments
from app.storage import SQLiteStore

STOPWORDS = {
    "about",
    "and",
    "are",
    "does",
    "early",
    "experiment",
    "experiments",
    "for",
    "from",
    "how",
    "improve",
    "in",
    "is",
    "of",
    "our",
    "the",
    "to",
    "what",
    "whether",
    "with",
}


@dataclass(frozen=True)
class ScientificReasoningResult:
    """Structured result returned by the scientific reasoning engine."""

    question: str
    answer: str
    reasoning: dict[str, Any]
    sources: list[dict[str, Any]]
    ai_used: bool
    provider: str


def _terms(question: str) -> list[str]:
    """Extract normalized search terms from a natural-language question."""

    return [
        term.lower()
        for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9+_-]{1,}", question)
        if term.lower() not in STOPWORDS
    ]


def _text_score(text: str, terms: list[str]) -> float:
    """Score a text block by simple deterministic term overlap."""

    haystack = text.lower()
    return float(sum(haystack.count(term) for term in terms))


def _experiment_text(experiment: dict[str, Any]) -> str:
    """Flatten useful experiment fields for relevance scoring."""

    fields = [
        experiment.get("id"),
        experiment.get("experiment_id"),
        experiment.get("title"),
        experiment.get("cell_line"),
        experiment.get("organoid_batch"),
        experiment.get("notes"),
        experiment.get("conclusions"),
        " ".join(str(value) for value in experiment.get("compounds") or []),
        " ".join(str(value) for value in experiment.get("treatments") or []),
        " ".join(str(value) for value in experiment.get("markers") or []),
        " ".join(str(value) for value in experiment.get("time_points") or []),
    ]
    return " ".join(str(field or "") for field in fields)


def _document_source(result: dict[str, Any], kind: str) -> dict[str, Any]:
    """Normalize keyword search results into source citations."""

    return {
        "kind": kind,
        "id": result.get("chunk_id") or result.get("document_id"),
        "document_id": result.get("document_id"),
        "title": result.get("title"),
        "provider": result.get("provider"),
        "snippet": result.get("snippet"),
        "score": result.get("score"),
    }


def _experiment_source(experiment: dict[str, Any], score: float) -> dict[str, Any]:
    """Return a compact experiment source object."""

    return {
        "kind": "experiment",
        "id": experiment.get("id"),
        "experiment_id": experiment.get("experiment_id"),
        "title": experiment.get("title"),
        "provider": experiment.get("source_provider"),
        "score": score,
        "snippet": experiment.get("conclusions") or experiment.get("notes") or "",
    }


def _asset_markers(asset: dict[str, Any]) -> list[str]:
    """Read marker metadata from a registered asset."""

    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    raw_markers = metadata.get("markers") if isinstance(metadata, dict) else []
    if isinstance(raw_markers, list):
        return [str(marker) for marker in raw_markers if str(marker).strip()]
    if isinstance(raw_markers, str):
        return [marker.strip() for marker in raw_markers.split(",") if marker.strip()]
    return []


def _asset_text(asset: dict[str, Any]) -> str:
    """Flatten useful asset fields for relevance scoring."""

    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    stats = metadata.get("statistics") if isinstance(metadata, dict) and isinstance(metadata.get("statistics"), dict) else {}
    fields = [
        asset.get("asset_id"),
        asset.get("asset_type"),
        asset.get("experiment_id"),
        asset.get("title"),
        asset.get("filename"),
        asset.get("provider"),
        asset.get("path"),
        " ".join(_asset_markers(asset)),
        metadata.get("timepoint") if isinstance(metadata, dict) else "",
        " ".join(str(value) for value in stats.get("variables", []) if value),
        " ".join(str(value) for value in stats.get("group_names", []) if value),
        " ".join(str(value) for value in stats.get("comparison_labels", []) if value),
        " ".join(str(value) for value in stats.get("statistical_tests", []) if value),
    ]
    return " ".join(str(field or "") for field in fields)


def _asset_source(asset: dict[str, Any], score: float) -> dict[str, Any]:
    """Return a compact asset source object."""

    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    statistics = metadata.get("statistics") if isinstance(metadata, dict) and isinstance(metadata.get("statistics"), dict) else None
    kind = "asset"
    if statistics:
        kind = "graphpad_statistics"
    elif asset.get("provider") == "microscopy" or asset.get("asset_type") in {"image", "microscopy"}:
        kind = "microscopy_asset"
    return {
        "kind": kind,
        "id": asset.get("asset_id"),
        "title": asset.get("title"),
        "filename": asset.get("filename"),
        "provider": asset.get("provider"),
        "experiment_id": asset.get("experiment_id"),
        "path": asset.get("path"),
        "markers": _asset_markers(asset),
        "timepoint": metadata.get("timepoint") if isinstance(metadata, dict) else None,
        "statistics": statistics,
        "score": score,
    }


def _timeline_events_for_reference(store: SQLiteStore, reference: str) -> list[dict[str, Any]]:
    """Build lightweight timeline events from assets linked to one reference."""

    events = []
    for asset in store.list_assets(experiment_id=reference):
        events.append(
            {
                "kind": "timeline_event",
                "id": asset.get("asset_id"),
                "title": asset.get("title") or asset.get("filename"),
                "event_type": "microscopy_asset"
                if asset.get("provider") == "microscopy"
                else "statistics_result"
                if isinstance((asset.get("metadata") or {}).get("statistics"), dict)
                else "asset",
                "timestamp": asset.get("updated_at") or asset.get("created_at"),
                "source": asset.get("provider"),
            }
        )
    return events


def _collect_evidence(question: str, store: SQLiteStore) -> dict[str, Any]:
    """Gather unified local evidence for scientific reasoning."""

    terms = _terms(question)
    documents = store.keyword_search(question, limit=8)
    notebook_entries = [_document_source(row, "notebook_entry") for row in documents if row.get("provider") != "literature"]
    literature_matches = [_document_source(row, "literature") for row in documents if row.get("provider") == "literature"]

    scored_experiments = []
    for experiment in store.list_experiments():
        score = _text_score(_experiment_text(experiment), terms)
        if score > 0:
            scored_experiments.append((score, experiment))
    scored_experiments.sort(key=lambda item: item[0], reverse=True)
    matched_experiments = [
        _experiment_source(experiment, score)
        for score, experiment in scored_experiments[:8]
    ]

    assets = []
    graphpad_statistics = []
    microscopy_assets = []
    for asset in store.list_assets():
        score = _text_score(_asset_text(asset), terms)
        if score <= 0:
            continue
        source = _asset_source(asset, score)
        assets.append(source)
        if source["kind"] == "graphpad_statistics":
            graphpad_statistics.append(source)
        if source["kind"] == "microscopy_asset":
            microscopy_assets.append(source)

    timeline_events = []
    for source in matched_experiments:
        for reference in [source.get("id"), source.get("experiment_id")]:
            if reference:
                timeline_events.extend(_timeline_events_for_reference(store, str(reference)))
    for source in assets:
        reference = source.get("experiment_id")
        if reference:
            timeline_events.extend(_timeline_events_for_reference(store, str(reference)))

    comparison = None
    if len(scored_experiments) >= 2:
        selected = [experiment for _, experiment in scored_experiments[:3]]
        try:
            comparison = compare_experiments(selected, settings=get_settings(), use_ai=False).__dict__
        except ValueError:
            comparison = None

    return {
        "terms": terms,
        "notebook_entries": notebook_entries,
        "experiments": matched_experiments,
        "graphpad_statistics": graphpad_statistics,
        "microscopy_assets": microscopy_assets,
        "literature_matches": literature_matches,
        "experiment_comparison": comparison,
        "timeline_events": timeline_events[:12],
        "sources": (matched_experiments + notebook_entries + literature_matches + graphpad_statistics + microscopy_assets)[:20],
    }


def _statistics_observations(stat_sources: list[dict[str, Any]]) -> list[str]:
    """Turn parsed GraphPad statistics into readable observations."""

    observations = []
    for source in stat_sources[:4]:
        stats = source.get("statistics") or {}
        variables = ", ".join(str(value) for value in stats.get("variables", []) if value)
        groups = ", ".join(str(value) for value in stats.get("group_names", []) if value)
        p_values = ", ".join(str(value) for value in stats.get("p_values", []) if value is not None)
        tests = ", ".join(str(value) for value in stats.get("statistical_tests", []) if value)
        pieces = [str(source.get("filename") or source.get("title") or "GraphPad statistics")]
        if variables:
            pieces.append(f"variables: {variables}")
        if groups:
            pieces.append(f"groups: {groups}")
        if p_values:
            pieces.append(f"p-values: {p_values}")
        if tests:
            pieces.append(f"test: {tests}")
        observations.append("; ".join(pieces))
    return observations


def _build_reasoning(question: str, evidence: dict[str, Any]) -> dict[str, Any]:
    """Create deterministic scientific reasoning from collected evidence."""

    experiments = evidence["experiments"]
    stats = evidence["graphpad_statistics"]
    images = evidence["microscopy_assets"]
    literature = evidence["literature_matches"]
    notebook_entries = evidence["notebook_entries"]
    timeline_events = evidence["timeline_events"]

    observations: list[str] = []
    for experiment in experiments[:4]:
        label = experiment.get("experiment_id") or experiment.get("title") or experiment.get("id")
        snippet = experiment.get("snippet") or "Structured experiment metadata matched the question."
        observations.append(f"{label}: {snippet}")
    observations.extend(_statistics_observations(stats))
    for image in images[:3]:
        markers = ", ".join(image.get("markers") or [])
        observations.append(
            f"Microscopy asset {image.get('filename')} links to {image.get('experiment_id') or 'an unresolved experiment'}"
            f" with markers {markers or 'not detected'} and timepoint {image.get('timepoint') or 'not detected'}."
        )

    supporting = []
    supporting.extend(experiments[:5])
    supporting.extend(stats[:4])
    supporting.extend(images[:4])
    supporting.extend(notebook_entries[:4])
    supporting.extend(literature[:4])

    conflicting = []
    negative_terms = re.compile(r"\b(no|not|failed|reduced|background|cautious|unclear|inconsistent)\b", re.I)
    for source in supporting:
        text = " ".join(str(source.get(key) or "") for key in ["snippet", "title", "filename"])
        if negative_terms.search(text):
            conflicting.append(source)

    limitations = [
        "Reasoning uses local indexed documents, extracted experiment fields, asset metadata, and parsed statistics only.",
        "Microscopy evidence is filename metadata; no image pixels are analyzed yet.",
    ]
    if not literature:
        limitations.append("No matching literature context was found in the local paper library.")
    if not stats:
        limitations.append("No matching parsed GraphPad statistics were found.")
    if not experiments:
        limitations.append("No matching structured experiments were found.")

    if experiments and (stats or images or literature):
        confidence = "medium"
    elif experiments or notebook_entries:
        confidence = "low-medium"
    else:
        confidence = "low"

    followups = [
        "Repeat the key treatment with a predefined replicate count and matched vehicle control.",
        "Add quantitative marker readouts and link GraphPad statistics to the experiment record.",
        "Capture microscopy filenames with experiment ID, day, markers, and condition for automatic linkage.",
    ]
    if "sag" in question.lower():
        followups.insert(0, "Run a SAG dose/window comparison with DMSO and pathway-inhibitor controls.")

    return {
        "observations": observations or ["No strong local observations were retrieved for this question."],
        "supporting_evidence": supporting,
        "conflicting_evidence": conflicting,
        "limitations": limitations,
        "confidence": confidence,
        "recommended_next_experiments": followups[:4],
        "timeline_events": timeline_events,
        "experiment_comparison": evidence.get("experiment_comparison"),
    }


def _local_answer(question: str, reasoning: dict[str, Any]) -> str:
    """Generate a concise deterministic answer."""

    observations = reasoning.get("observations") or []
    confidence = reasoning.get("confidence") or "low"
    if observations and observations[0] != "No strong local observations were retrieved for this question.":
        return (
            f"Based on local ResearchOS evidence, the answer is cautiously {confidence} confidence. "
            f"The strongest observation is: {observations[0]}"
        )
    return (
        "ResearchOS does not yet have enough local evidence to answer this confidently. "
        "Load or sync more notebook entries, statistics, microscopy assets, and literature, then ask again."
    )


def _reasoning_prompt(question: str, evidence: dict[str, Any], reasoning: dict[str, Any]) -> str:
    """Build an AI prompt using the same local evidence package."""

    return (
        "Answer this scientific question using only the ResearchOS evidence package. "
        "Preserve uncertainty and do not invent missing data.\n\n"
        f"Question: {question}\n\n"
        f"Evidence package: {evidence}\n\n"
        f"Deterministic reasoning draft: {reasoning}"
    )


def reason_scientifically(
    question: str,
    settings: Settings | None = None,
    use_ai: bool = True,
) -> ScientificReasoningResult:
    """Reason over local ResearchOS evidence and optionally synthesize with AI."""

    resolved_settings = settings or get_settings()
    clean_question = question.strip()
    store = SQLiteStore(settings=resolved_settings)
    evidence = _collect_evidence(clean_question, store)
    reasoning = _build_reasoning(clean_question, evidence)
    answer = _local_answer(clean_question, reasoning)
    ai_used = False
    provider_name = "local-fallback"

    if use_ai:
        try:
            provider = get_ai_provider(settings=resolved_settings)
            answer = provider.chat(_reasoning_prompt(clean_question, evidence, reasoning))
            ai_used = True
            provider_name = provider.provider_name
        except AIProviderError as exc:
            reasoning["limitations"].append(f"AI synthesis was not used: {exc}")

    return ScientificReasoningResult(
        question=clean_question,
        answer=answer,
        reasoning=reasoning,
        sources=evidence["sources"],
        ai_used=ai_used,
        provider=provider_name,
    )

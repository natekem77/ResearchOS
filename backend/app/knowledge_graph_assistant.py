"""Knowledge Graph powered assistant for ResearchOS."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.ai_providers import AIProviderError, get_ai_provider
from app.config import Settings, get_settings
from app.global_knowledge_graph import KnowledgeGraphService


@dataclass(frozen=True)
class KnowledgeAssistantAnswer:
    """Structured answer grounded in the global Knowledge Graph."""

    question: str
    direct_answer: str
    knowledge_graph_summary: str
    experiments: list[dict[str, Any]]
    notebook_entries: list[dict[str, Any]]
    literature: list[dict[str, Any]]
    graphpad_statistics: list[dict[str, Any]]
    spreadsheets: list[dict[str, Any]]
    microscopy_images: list[dict[str, Any]]
    related_entities: list[dict[str, Any]]
    limitations: list[str]
    sources: list[dict[str, Any]]
    entity: str | None
    entity_type: str | None
    experiment: dict[str, Any] | None
    ai_synthesis: str | None
    ai_used: bool
    provider: str


QUESTION_STOPWORDS = {
    "about",
    "all",
    "data",
    "do",
    "does",
    "everything",
    "experiments",
    "for",
    "in",
    "involve",
    "involving",
    "know",
    "show",
    "the",
    "used",
    "what",
    "which",
    "with",
}


def answer_with_knowledge_graph(
    question: str,
    settings: Settings | None = None,
    use_ai: bool = True,
    service: KnowledgeGraphService | None = None,
) -> KnowledgeAssistantAnswer:
    """Answer a question using the Global Knowledge Graph as first evidence."""

    resolved_settings = settings or get_settings()
    graph_service = service or KnowledgeGraphService(settings=resolved_settings)
    clean_question = question.strip()
    graph_target = _select_graph_target(clean_question, graph_service)

    if graph_target["kind"] == "experiment":
        evidence = _experiment_evidence(str(graph_target["name"]), graph_service)
    elif graph_target["name"]:
        evidence = _entity_evidence(str(graph_target["name"]), graph_service)
    else:
        evidence = _search_evidence(clean_question, graph_service)

    direct_answer = _local_direct_answer(clean_question, evidence)
    limitations = _limitations(evidence)
    ai_synthesis: str | None = None
    ai_used = False
    provider_name = "local-fallback"

    if use_ai:
        try:
            provider = get_ai_provider(settings=resolved_settings)
            ai_synthesis = provider.chat(_knowledge_prompt(clean_question, evidence))
            direct_answer = ai_synthesis
            ai_used = True
            provider_name = provider.provider_name
        except AIProviderError as exc:
            limitations.append(f"AI synthesis was not used: {exc}")

    return KnowledgeAssistantAnswer(
        question=clean_question,
        direct_answer=direct_answer,
        knowledge_graph_summary=str(evidence.get("summary") or ""),
        experiments=evidence["experiments"],
        notebook_entries=evidence["notebook_entries"],
        literature=evidence["literature"],
        graphpad_statistics=evidence["graphpad_statistics"],
        spreadsheets=evidence["spreadsheets"],
        microscopy_images=evidence["microscopy_images"],
        related_entities=evidence["related_entities"],
        limitations=limitations,
        sources=evidence["sources"],
        entity=evidence.get("entity"),
        entity_type=evidence.get("entity_type"),
        experiment=evidence.get("experiment"),
        ai_synthesis=ai_synthesis,
        ai_used=ai_used,
        provider=provider_name,
    )


def _select_graph_target(question: str, service: KnowledgeGraphService) -> dict[str, str | None]:
    """Select the most likely graph entity or experiment from a question."""

    explicit_experiment = _experiment_reference(question)
    if explicit_experiment:
        if service.experiment_neighborhood(explicit_experiment):
            return {"kind": "experiment", "name": explicit_experiment}

    candidates = _candidate_terms(question)
    for candidate in candidates:
        if service.find_entity_case_insensitive(candidate):
            return {"kind": "entity", "name": candidate}
        if service.experiment_neighborhood(candidate):
            return {"kind": "experiment", "name": candidate}

    search_results = service.search(question, limit=1)
    if search_results:
        return {"kind": "entity", "name": str(search_results[0]["entity"])}
    return {"kind": None, "name": None}


def _experiment_reference(question: str) -> str | None:
    for pattern in [
        r"\bNK[_-]?Expt[_-]?\d+\b",
        r"\bEXP[_-]?\d+\b",
        r"\bexperiment:[A-Za-z0-9:_-]+\b",
    ]:
        match = re.search(pattern, question, flags=re.I)
        if match:
            value = match.group(0)
            if re.match(r"NK", value, flags=re.I):
                number = re.search(r"\d+", value)
                return f"NK_Expt_{number.group(0)}" if number else value
            if re.match(r"EXP", value, flags=re.I):
                number = re.search(r"\d+", value)
                return f"EXP_{number.group(0)}" if number else value
            return value
    return None


def _candidate_terms(question: str) -> list[str]:
    tokens = [
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+_.-]{1,}", question)
        if token.lower() not in QUESTION_STOPWORDS
    ]
    prioritized = sorted(
        set(tokens),
        key=lambda token: (
            not bool(re.search(r"[A-Z0-9]", token)),
            -len(token),
            token.lower(),
        ),
    )
    return prioritized


def _entity_evidence(entity_name: str, service: KnowledgeGraphService) -> dict[str, Any]:
    detail = service.entity_detail(entity_name)
    if detail is None:
        return _empty_evidence(summary=f"No Knowledge Graph entity found for {entity_name}.")
    graphpad_assets = detail.get("graphpad_assets") or []
    statistics = detail.get("statistics") or []
    return {
        "entity": detail.get("entity"),
        "entity_type": detail.get("entity_type"),
        "experiment": None,
        "summary": detail.get("summary") or "",
        "experiments": detail.get("experiments") or [],
        "notebook_entries": detail.get("notebook_entries") or [],
        "literature": detail.get("literature") or [],
        "graphpad_statistics": _dedupe_objects([*graphpad_assets, *statistics]),
        "spreadsheets": detail.get("spreadsheet_assets") or [],
        "microscopy_images": detail.get("microscopy_assets") or [],
        "related_entities": detail.get("related_entities") or [],
        "sources": _sources_from_detail(detail),
    }


def _experiment_evidence(experiment_id: str, service: KnowledgeGraphService) -> dict[str, Any]:
    neighborhood = service.experiment_neighborhood(experiment_id)
    if neighborhood is None:
        return _empty_evidence(summary=f"No Knowledge Graph experiment found for {experiment_id}.")
    experiment = neighborhood.get("experiment")
    entities = neighborhood.get("entities") or []
    return {
        "entity": None,
        "entity_type": None,
        "experiment": experiment,
        "summary": _experiment_summary_text(neighborhood),
        "experiments": [experiment] if isinstance(experiment, dict) else [],
        "notebook_entries": [neighborhood["notebook"]] if neighborhood.get("notebook") else [],
        "literature": neighborhood.get("literature") or [],
        "graphpad_statistics": _dedupe_objects([*(neighborhood.get("graphpad") or []), *(neighborhood.get("statistics") or [])]),
        "spreadsheets": neighborhood.get("spreadsheets") or [],
        "microscopy_images": neighborhood.get("images") or [],
        "related_entities": entities[:20],
        "sources": _sources_from_experiment_neighborhood(neighborhood),
    }


def _search_evidence(question: str, service: KnowledgeGraphService) -> dict[str, Any]:
    results = service.search(question, limit=8)
    if not results:
        return _empty_evidence(summary="No matching Knowledge Graph entities were found.")
    first = results[0]
    evidence = _entity_evidence(str(first["entity"]), service)
    evidence["summary"] = f"Best graph match: {first['entity']}. {evidence.get('summary') or ''}"
    return evidence


def _empty_evidence(summary: str) -> dict[str, Any]:
    return {
        "entity": None,
        "entity_type": None,
        "experiment": None,
        "summary": summary,
        "experiments": [],
        "notebook_entries": [],
        "literature": [],
        "graphpad_statistics": [],
        "spreadsheets": [],
        "microscopy_images": [],
        "related_entities": [],
        "sources": [],
    }


def _local_direct_answer(question: str, evidence: dict[str, Any]) -> str:
    subject = evidence.get("entity") or (evidence.get("experiment") or {}).get("experiment_id") or (evidence.get("experiment") or {}).get("id")
    if not subject:
        return str(evidence.get("summary") or "No graph evidence was found.")
    counts = {
        "experiments": len(evidence["experiments"]),
        "notebook entries": len(evidence["notebook_entries"]),
        "literature records": len(evidence["literature"]),
        "GraphPad/statistics records": len(evidence["graphpad_statistics"]),
        "spreadsheets": len(evidence["spreadsheets"]),
        "microscopy/images": len(evidence["microscopy_images"]),
    }
    populated = [f"{count} {label}" for label, count in counts.items() if count]
    if not populated:
        return f"The Knowledge Graph has an entity for {subject}, but no linked local evidence objects yet."
    related = evidence.get("related_entities") or []
    related_text = ""
    if related:
        names = [str(item.get("entity") or item.get("name")) for item in related[:6]]
        related_text = f" Related entities include {', '.join(name for name in names if name)}."
    return f"Knowledge Graph evidence for {subject}: {', '.join(populated)}.{related_text}"


def _limitations(evidence: dict[str, Any]) -> list[str]:
    limitations = [
        "The Knowledge Graph is built from local ResearchOS records and provider metadata only.",
        "Missing links usually mean the relevant note, paper, asset, or parser metadata has not been ingested yet.",
    ]
    if not evidence["literature"]:
        limitations.append("No linked literature records were found for this graph target.")
    if not evidence["graphpad_statistics"]:
        limitations.append("No linked GraphPad/statistical analysis records were found for this graph target.")
    return limitations


def _knowledge_prompt(question: str, evidence: dict[str, Any]) -> str:
    return (
        "Answer using only this ResearchOS Global Knowledge Graph evidence. "
        "Use concise sections and preserve uncertainty.\n\n"
        f"Question: {question}\n\n"
        f"Knowledge Graph evidence: {evidence}"
    )


def _sources_from_detail(detail: dict[str, Any]) -> list[dict[str, Any]]:
    sources = []
    for key in ["experiments", "notebook_entries", "literature", "microscopy_assets", "graphpad_assets", "spreadsheet_assets", "statistics"]:
        for item in detail.get(key) or []:
            if isinstance(item, dict):
                sources.append(item | {"source_section": key})
    return sources[:40]


def _sources_from_experiment_neighborhood(neighborhood: dict[str, Any]) -> list[dict[str, Any]]:
    sources = []
    for key in ["images", "graphpad", "statistics", "spreadsheets", "literature"]:
        for item in neighborhood.get(key) or []:
            if isinstance(item, dict):
                sources.append(item | {"source_section": key})
    if neighborhood.get("notebook"):
        sources.append(neighborhood["notebook"] | {"source_section": "notebook"})
    return sources[:40]


def _experiment_summary_text(neighborhood: dict[str, Any]) -> str:
    experiment = neighborhood.get("experiment") or {}
    label = experiment.get("experiment_id") or experiment.get("title") or experiment.get("id") or "Experiment"
    counts = {
        "images": len(neighborhood.get("images") or []),
        "GraphPad assets": len(neighborhood.get("graphpad") or []),
        "statistics records": len(neighborhood.get("statistics") or []),
        "spreadsheets": len(neighborhood.get("spreadsheets") or []),
        "literature records": len(neighborhood.get("literature") or []),
        "entities": len(neighborhood.get("entities") or []),
    }
    parts = [f"{count} {label_name}" for label_name, count in counts.items() if count]
    return f"{label} is connected to {', '.join(parts) if parts else 'no additional graph objects yet'}."


def _dedupe_objects(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output = []
    for item in items:
        key = str(item.get("asset_id") or item.get("id") or item.get("title") or item)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output

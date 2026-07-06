"""Scientific research assistant orchestration for ResearchOS."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.ai_providers import AIProviderError, get_ai_provider
from app.config import Settings, get_settings
from app.retinal_ontology import build_retinal_ontology
from app.storage import SQLiteStore
from app.vector_index import ChromaVectorIndex

STOPWORDS = {
    "about",
    "and",
    "are",
    "compare",
    "did",
    "for",
    "from",
    "how",
    "in",
    "notes",
    "of",
    "the",
    "used",
    "was",
    "were",
    "what",
    "when",
    "which",
    "with",
}


@dataclass(frozen=True)
class AssistantAnswer:
    """Structured answer returned by the ResearchOS assistant."""

    question: str
    direct_answer: str
    evidence_from_experiments: list[dict[str, Any]]
    source_document_citations: list[dict[str, Any]]
    extracted_facts: dict[str, list[str]]
    ai_synthesis: str | None
    limitations_uncertainties: list[str]
    sources: list[dict[str, Any]]
    ai_used: bool
    provider: str


def _terms(text: str) -> list[str]:
    """Return normalized query terms suitable for local matching."""

    return [
        term.lower()
        for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{1,}", text)
        if term.lower() not in STOPWORDS
    ]


def _search_documents(question: str, settings: Settings, limit: int = 6) -> list[dict[str, Any]]:
    """Retrieve source chunks with vector search and keyword fallback."""

    store = SQLiteStore(settings=settings)
    seen: set[str] = set()
    results: list[dict[str, Any]] = []

    keyword_query = " ".join(_terms(question)) or question
    for result in store.keyword_search(keyword_query, limit=limit):
        chunk_id = str(result.get("chunk_id") or "")
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            results.append(result)

    if results:
        return results[:limit]

    for result in ChromaVectorIndex(settings=settings).search(question, limit=limit):
        chunk_id = str(result.get("chunk_id") or "")
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            results.append(result)

    return results[:limit]


def _experiment_text(experiment: dict[str, Any]) -> str:
    """Flatten experiment fields for local relevance matching."""

    values: list[str] = []
    for value in experiment.values():
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value is not None:
            values.append(str(value))
    return " ".join(values).lower()


def _relevant_experiments(question: str, experiments: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Return experiments whose structured fields overlap with the question."""

    query_terms = _terms(question)
    scored: list[tuple[int, dict[str, Any]]] = []
    for experiment in experiments:
        text = _experiment_text(experiment)
        score = sum(text.count(term) for term in query_terms)
        if score > 0:
            scored.append((score, experiment))

    scored.sort(key=lambda item: (-item[0], item[1].get("date") or "", item[1].get("title") or ""))
    return [experiment for _, experiment in scored[:limit]]


def _entity_text(entity: dict[str, Any]) -> str:
    """Flatten ontology entity fields for local matching."""

    parts = [str(entity.get("name", "")), str(entity.get("type", ""))]
    for key in ["experiments", "documents", "protocols", "ai_summaries"]:
        for item in entity.get(key, []) or []:
            if isinstance(item, dict):
                parts.extend(str(value) for value in item.values() if value is not None)
    return " ".join(parts).lower()


def _relevant_entities(question: str, ontology: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Return ontology entities related to a natural-language question."""

    query_terms = _terms(question)
    relevant: dict[str, list[dict[str, Any]]] = {}
    for entity_type, entities in ontology.items():
        matches = []
        for entity in entities:
            text = _entity_text(entity)
            name = str(entity.get("name", "")).lower()
            if name and name in question.lower():
                matches.append(entity)
                continue
            if any(term in text for term in query_terms):
                matches.append(entity)
        if matches:
            relevant[entity_type] = matches[:5]
    return relevant


def _experiment_evidence(experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert experiments into compact evidence records."""

    evidence: list[dict[str, Any]] = []
    for experiment in experiments:
        evidence.append(
            {
                "id": experiment.get("id"),
                "experiment_id": experiment.get("experiment_id"),
                "title": experiment.get("title"),
                "date": experiment.get("date"),
                "provider": experiment.get("source_provider"),
                "compounds": experiment.get("compounds") or [],
                "markers": experiment.get("markers") or [],
                "time_points": experiment.get("time_points") or [],
                "notes": experiment.get("notes"),
                "conclusions": experiment.get("conclusions"),
            }
        )
    return evidence


def _source_citations(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build source citation objects from retrieved chunks."""

    citations: list[dict[str, Any]] = []
    for index, source in enumerate(sources, start=1):
        citations.append(
            {
                "citation": f"[{index}]",
                "document_id": source.get("document_id"),
                "chunk_id": source.get("chunk_id"),
                "title": source.get("title"),
                "provider": source.get("provider"),
                "snippet": source.get("snippet"),
                "score": source.get("score"),
            }
        )
    return citations


def _extracted_facts(
    experiments: list[dict[str, Any]],
    entities: dict[str, list[dict[str, Any]]],
) -> dict[str, list[str]]:
    """Collect structured facts from experiments and ontology matches."""

    facts: dict[str, set[str]] = {
        "experiment_ids": set(),
        "compounds": set(),
        "markers": set(),
        "cell_lines": set(),
        "organoid_batches": set(),
        "time_points": set(),
    }

    for experiment in experiments:
        for key, target in [
            ("experiment_id", "experiment_ids"),
            ("cell_line", "cell_lines"),
            ("organoid_batch", "organoid_batches"),
        ]:
            value = experiment.get(key)
            if value:
                facts[target].add(str(value))
        for key, target in [
            ("compounds", "compounds"),
            ("markers", "markers"),
            ("time_points", "time_points"),
        ]:
            facts[target].update(str(value) for value in experiment.get(key, []) if value)

    for entity_type, matched_entities in entities.items():
        target = {
            "compounds": "compounds",
            "markers": "markers",
            "cell-lines": "cell_lines",
            "organoid-batches": "organoid_batches",
        }.get(entity_type)
        if target:
            facts[target].update(str(entity.get("name")) for entity in matched_entities if entity.get("name"))

    return {key: sorted(values) for key, values in facts.items()}


def _local_direct_answer(question: str, evidence: list[dict[str, Any]], facts: dict[str, list[str]]) -> str:
    """Create a deterministic local answer when no AI provider is configured."""

    lower_question = question.lower()
    if not evidence:
        return (
            "I did not find matching structured experiments in the local ResearchOS data. "
            "Try loading demo notes or syncing a notebook, then ask again."
        )

    if "which" in lower_question and "experiment" in lower_question:
        names = [
            str(item.get("experiment_id") or item.get("title"))
            for item in evidence
            if item.get("experiment_id") or item.get("title")
        ]
        return "Relevant experiments: " + ", ".join(names) + "."

    if "compare" in lower_question:
        titles = [str(item.get("title")) for item in evidence if item.get("title")]
        return (
            "The relevant experiments differ by compounds, markers, and time points. "
            f"I found these records for comparison: {', '.join(titles)}."
        )

    compounds = facts.get("compounds", [])
    markers = facts.get("markers", [])
    pieces = [f"I found {len(evidence)} relevant experiment record(s)."]
    if compounds:
        pieces.append(f"Compounds mentioned: {', '.join(compounds)}.")
    if markers:
        pieces.append(f"Markers mentioned: {', '.join(markers)}.")
    return " ".join(pieces)


def _local_synthesis(
    evidence: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    facts: dict[str, list[str]],
) -> str:
    """Summarize retrieved evidence without calling an AI provider."""

    lines = []
    if evidence:
        lines.append("Experiment evidence:")
        for item in evidence:
            label = item.get("experiment_id") or item.get("title") or item.get("id")
            details = []
            if item.get("compounds"):
                details.append(f"compounds={', '.join(item['compounds'])}")
            if item.get("markers"):
                details.append(f"markers={', '.join(item['markers'])}")
            if item.get("time_points"):
                details.append(f"time_points={', '.join(item['time_points'])}")
            conclusion = item.get("conclusions")
            if conclusion:
                details.append(f"conclusion={conclusion}")
            lines.append(f"- {label}: {'; '.join(details) if details else 'structured metadata available'}")

    if citations:
        lines.append("Source snippets:")
        for citation in citations[:3]:
            lines.append(f"- {citation['citation']} {citation.get('title')}: {citation.get('snippet')}")

    if not lines:
        facts_text = ", ".join(f"{key}: {', '.join(values)}" for key, values in facts.items() if values)
        return facts_text or "No local evidence was retrieved."

    return "\n".join(lines)


def _assistant_prompt(
    question: str,
    evidence: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    facts: dict[str, list[str]],
    entities: dict[str, list[dict[str, Any]]],
) -> str:
    """Build a structured prompt for optional AI synthesis."""

    return (
        "Answer the scientific question using only the ResearchOS context below. "
        "Return a concise synthesis, cite source snippets as [1], [2], and state uncertainty.\n\n"
        f"Question: {question}\n\n"
        f"Structured experiment evidence:\n{evidence}\n\n"
        f"Source citations:\n{citations}\n\n"
        f"Extracted facts:\n{facts}\n\n"
        f"Ontology entities:\n{entities}"
    )


def ask_research_assistant(
    question: str,
    settings: Settings | None = None,
    use_ai: bool = True,
) -> AssistantAnswer:
    """Answer a scientific question with local context and optional AI synthesis."""

    resolved_settings = settings or get_settings()
    clean_question = question.strip()
    store = SQLiteStore(settings=resolved_settings)
    sources = _search_documents(clean_question, settings=resolved_settings)
    experiments = store.list_experiments()
    relevant_experiments = _relevant_experiments(clean_question, experiments)
    documents = [document.__dict__ for document in store.get_all_research_documents()]
    ontology = build_retinal_ontology(experiments=experiments, documents=documents)
    relevant_entities = _relevant_entities(clean_question, ontology)

    evidence = _experiment_evidence(relevant_experiments)
    citations = _source_citations(sources)
    facts = _extracted_facts(relevant_experiments, relevant_entities)
    local_answer = _local_direct_answer(clean_question, evidence, facts)
    local_synthesis = _local_synthesis(evidence, citations, facts)
    limitations = [
        "This answer is based only on documents currently ingested into local ResearchOS storage.",
        "Regex-based experiment extraction may miss fields that are phrased unusually.",
    ]

    ai_synthesis: str | None = None
    ai_used = False
    provider_name = "local-fallback"

    if use_ai:
        try:
            provider = get_ai_provider(settings=resolved_settings)
            ai_synthesis = provider.chat(_assistant_prompt(clean_question, evidence, citations, facts, relevant_entities))
            ai_used = True
            provider_name = provider.provider_name
        except AIProviderError as exc:
            limitations.append(f"AI synthesis was not used: {exc}")

    return AssistantAnswer(
        question=clean_question,
        direct_answer=ai_synthesis or local_answer,
        evidence_from_experiments=evidence,
        source_document_citations=citations,
        extracted_facts=facts,
        ai_synthesis=ai_synthesis or local_synthesis,
        limitations_uncertainties=limitations,
        sources=sources,
        ai_used=ai_used,
        provider=provider_name,
    )

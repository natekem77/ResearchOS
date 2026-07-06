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
    "experiment",
    "experiments",
    "for",
    "from",
    "how",
    "in",
    "notes",
    "of",
    "show",
    "shows",
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
    direct_matches: list[dict[str, Any]]
    related_context: list[dict[str, Any]]
    evidence_from_experiments: list[dict[str, Any]]
    source_document_citations: list[dict[str, Any]]
    literature_context: list[dict[str, Any]]
    extracted_facts: dict[str, list[str]]
    ai_synthesis: str | None
    limitations_uncertainties: list[str]
    sources: list[dict[str, Any]]
    ai_used: bool
    provider: str


@dataclass(frozen=True)
class QueryIntent:
    """Detected question intent used to keep assistant evidence relevant."""

    terms: list[str]
    explicit_entities: dict[str, list[str]]
    is_comparison: bool


@dataclass(frozen=True)
class ScoredExperiment:
    """Experiment plus relevance metadata."""

    experiment: dict[str, Any]
    score: float
    matched_entities: list[str]
    is_direct: bool


RELEVANCE_THRESHOLD = 1.0
SOURCE_RELEVANCE_THRESHOLD = 1.0


def _terms(text: str) -> list[str]:
    """Return normalized query terms suitable for local matching."""

    return [
        term.lower()
        for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{1,}", text)
        if term.lower() not in STOPWORDS
    ]


def _is_comparison_question(question: str) -> bool:
    """Return whether the user is asking to compare multiple contexts."""

    return bool(re.search(r"\b(compare|versus|vs\.?|difference|different|contrast)\b", question, re.I))


def _detect_explicit_entities(
    question: str,
    ontology: dict[str, list[dict[str, Any]]],
) -> dict[str, list[str]]:
    """Detect exact ontology entity names mentioned in a question."""

    lower_question = question.lower()
    explicit: dict[str, list[str]] = {}
    for entity_type in ["compounds", "markers", "cell-lines", "organoid-batches"]:
        matches = []
        for entity in ontology.get(entity_type, []):
            name = str(entity.get("name") or "").strip()
            if name and re.search(rf"(?<![A-Za-z0-9-]){re.escape(name.lower())}(?![A-Za-z0-9-])", lower_question):
                matches.append(name)
        if matches:
            explicit[entity_type] = sorted(set(matches))

    all_matches = [
        (entity_type, name)
        for entity_type, names in explicit.items()
        for name in names
    ]
    nested_names = {
        name
        for _, name in all_matches
        for _, other_name in all_matches
        if name != other_name and name.lower() in other_name.lower()
    }
    if not nested_names:
        return explicit

    filtered: dict[str, list[str]] = {}
    for entity_type, names in explicit.items():
        kept_names = [name for name in names if name not in nested_names]
        if kept_names:
            filtered[entity_type] = kept_names
    return filtered


def _query_intent(question: str, ontology: dict[str, list[dict[str, Any]]]) -> QueryIntent:
    """Build query intent from question terms and exact ontology entities."""

    return QueryIntent(
        terms=_terms(question),
        explicit_entities=_detect_explicit_entities(question, ontology),
        is_comparison=_is_comparison_question(question),
    )


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


def _source_passes_threshold(source: dict[str, Any]) -> bool:
    """Return whether a retrieved source is strong enough to cite."""

    source_type = source.get("source")
    score = source.get("score")
    if source_type == "keyword" and isinstance(score, int | float):
        return float(score) >= SOURCE_RELEVANCE_THRESHOLD
    return True


def _experiment_text(experiment: dict[str, Any]) -> str:
    """Flatten experiment fields for local relevance matching."""

    values: list[str] = []
    for value in experiment.values():
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value is not None:
            values.append(str(value))
    return " ".join(values).lower()


def _experiment_entity_values(experiment: dict[str, Any], entity_type: str) -> list[str]:
    """Return experiment values corresponding to an ontology entity type."""

    if entity_type == "compounds":
        return [str(value) for value in experiment.get("compounds", []) if value]
    if entity_type == "markers":
        return [str(value) for value in experiment.get("markers", []) if value]
    if entity_type == "cell-lines":
        return [str(experiment["cell_line"])] if experiment.get("cell_line") else []
    if entity_type == "organoid-batches":
        return [str(experiment["organoid_batch"])] if experiment.get("organoid_batch") else []
    return []


def _experiment_matches_entity(experiment: dict[str, Any], entity_type: str, entity_name: str) -> bool:
    """Return whether an experiment contains a specific entity."""

    return any(value.lower() == entity_name.lower() for value in _experiment_entity_values(experiment, entity_type))


def _score_experiments(
    intent: QueryIntent,
    experiments: list[dict[str, Any]],
    limit: int = 8,
) -> list[ScoredExperiment]:
    """Score experiments and mark direct entity matches separately."""

    scored: list[ScoredExperiment] = []
    explicit_entities = [
        (entity_type, entity_name)
        for entity_type, names in intent.explicit_entities.items()
        for entity_name in names
    ]
    for experiment in experiments:
        text = _experiment_text(experiment)
        term_score = sum(text.count(term) for term in intent.terms)
        matched_entities = [
            entity_name
            for entity_type, entity_name in explicit_entities
            if _experiment_matches_entity(experiment, entity_type, entity_name)
        ]

        if explicit_entities and intent.is_comparison:
            is_direct = bool(matched_entities)
        elif explicit_entities:
            is_direct = len(matched_entities) == len(explicit_entities)
        else:
            is_direct = term_score >= RELEVANCE_THRESHOLD

        score = float(term_score + (3 * len(matched_entities)))
        if explicit_entities and not intent.is_comparison and not is_direct:
            continue

        if is_direct or score >= RELEVANCE_THRESHOLD:
            scored.append(
                ScoredExperiment(
                    experiment=experiment,
                    score=score,
                    matched_entities=sorted(set(matched_entities)),
                    is_direct=is_direct,
                )
            )

    scored.sort(
        key=lambda item: (
            not item.is_direct,
            -item.score,
            item.experiment.get("date") or "",
            item.experiment.get("title") or "",
        )
    )
    return scored[:limit]


def _split_experiment_relevance(scored: list[ScoredExperiment]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split scored experiments into direct matches and related context."""

    direct = [item.experiment for item in scored if item.is_direct]
    related = [item.experiment for item in scored if not item.is_direct and item.score >= RELEVANCE_THRESHOLD]
    return direct, related


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


def _experiment_evidence(
    experiments: list[dict[str, Any]],
    relevance: str = "direct",
) -> list[dict[str, Any]]:
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
                "relevance": relevance,
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


def _literature_context(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return retrieved literature chunks separately from lab notebook evidence."""

    literature = []
    for source in sources:
        if source.get("provider") != "literature":
            continue
        literature.append(
            {
                "document_id": source.get("document_id"),
                "chunk_id": source.get("chunk_id"),
                "title": source.get("title"),
                "provider": "literature",
                "snippet": source.get("snippet"),
                "score": source.get("score"),
            }
        )
    return literature


def _filter_sources_for_experiments(
    sources: list[dict[str, Any]],
    direct_experiments: list[dict[str, Any]],
    related_experiments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prefer source chunks attached to direct matches, then related context."""

    sources = [source for source in sources if _source_passes_threshold(source)]
    direct_doc_ids = {str(experiment.get("source_document_id")) for experiment in direct_experiments}
    related_doc_ids = {str(experiment.get("source_document_id")) for experiment in related_experiments}

    if direct_doc_ids:
        direct_sources = [source for source in sources if str(source.get("document_id")) in direct_doc_ids]
        related_sources = [source for source in sources if str(source.get("document_id")) in related_doc_ids]
        return direct_sources + [source for source in related_sources if source not in direct_sources]

    if related_doc_ids:
        return [source for source in sources if str(source.get("document_id")) in related_doc_ids]

    return sources


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


def _local_direct_answer(
    question: str,
    direct_evidence: list[dict[str, Any]],
    related_evidence: list[dict[str, Any]],
    facts: dict[str, list[str]],
    intent: QueryIntent,
) -> str:
    """Create a deterministic local answer when no AI provider is configured."""

    lower_question = question.lower()
    if not direct_evidence and not related_evidence:
        return (
            "I did not find matching structured experiments in the local ResearchOS data. "
            "Try loading demo notes or syncing a notebook, then ask again."
        )

    evidence = direct_evidence or related_evidence
    entity_names = [
        name
        for names in intent.explicit_entities.values()
        for name in names
    ]
    entity_text = ", ".join(entity_names)

    if "which" in lower_question and "experiment" in lower_question:
        names = [
            str(item.get("experiment_id") or item.get("title"))
            for item in evidence
            if item.get("experiment_id") or item.get("title")
        ]
        scope = f" containing {entity_text}" if entity_text and direct_evidence else ""
        return f"I found {len(names)} experiment(s){scope}: {', '.join(names)}."

    if "compare" in lower_question:
        titles = [str(item.get("title")) for item in evidence if item.get("title")]
        return (
            f"I found {len(titles)} experiment record(s) for comparison: {', '.join(titles)}. "
            "Use the evidence section for compounds, markers, time points, and conclusions."
        )

    if re.search(r"\b(show|shows|suggest|suggests|result|results|finding|findings)\b", lower_question):
        summaries = []
        for item in evidence:
            label = str(item.get("experiment_id") or item.get("title"))
            summary = item.get("conclusions") or item.get("notes")
            if summary:
                summaries.append(f"{label}: {summary}")
        if summaries:
            scope = f" for {entity_text}" if entity_text and direct_evidence else ""
            return f"I found {len(summaries)} direct result(s){scope}. " + " ".join(summaries)

    compounds = facts.get("compounds", [])
    markers = facts.get("markers", [])
    qualifier = "directly matching" if direct_evidence else "related"
    pieces = [f"I found {len(evidence)} {qualifier} experiment record(s)."]
    if entity_text and direct_evidence:
        pieces.append(f"Direct match: {entity_text}.")
    if compounds:
        pieces.append(f"Compounds mentioned: {', '.join(compounds)}.")
    if markers:
        pieces.append(f"Markers mentioned: {', '.join(markers)}.")
    return " ".join(pieces)


def _local_synthesis(
    direct_evidence: list[dict[str, Any]],
    related_evidence: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    facts: dict[str, list[str]],
) -> str:
    """Summarize retrieved evidence without calling an AI provider."""

    lines = []
    if direct_evidence:
        lines.append("Direct experiment matches:")
        for item in direct_evidence:
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

    if related_evidence:
        lines.append("Related context:")
        for item in related_evidence:
            label = item.get("experiment_id") or item.get("title") or item.get("id")
            lines.append(f"- {label}: related but not a direct entity match")

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
    literature: list[dict[str, Any]],
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
        f"Literature context:\n{literature}\n\n"
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
    literature = _literature_context(sources)
    experiments = store.list_experiments()
    lab_experiments = [
        experiment for experiment in experiments if experiment.get("source_provider") != "literature"
    ]
    documents = [document.__dict__ for document in store.get_all_research_documents()]
    ontology = build_retinal_ontology(experiments=experiments, documents=documents)
    intent = _query_intent(clean_question, ontology)
    scored_experiments = _score_experiments(intent, lab_experiments)
    direct_experiments, related_experiments = _split_experiment_relevance(scored_experiments)
    relevant_entities = _relevant_entities(clean_question, ontology)
    lab_sources = [source for source in sources if source.get("provider") != "literature"]
    lab_sources = _filter_sources_for_experiments(lab_sources, direct_experiments, related_experiments)
    sources = lab_sources + literature

    direct_matches = _experiment_evidence(direct_experiments, relevance="direct")
    related_context = _experiment_evidence(related_experiments, relevance="related")
    evidence = direct_matches + related_context
    citations = _source_citations(sources)
    facts = _extracted_facts(direct_experiments or related_experiments, relevant_entities)
    local_answer = _local_direct_answer(clean_question, direct_matches, related_context, facts, intent)
    local_synthesis = _local_synthesis(direct_matches, related_context, citations, facts)
    limitations = [
        "This answer is based only on documents currently ingested into local ResearchOS storage.",
        "Regex-based experiment extraction may miss fields that are phrased unusually.",
    ]
    if related_context:
        limitations.append("Related context is separated from direct matches to avoid overstating relevance.")

    ai_synthesis: str | None = None
    ai_used = False
    provider_name = "local-fallback"

    if use_ai:
        try:
            provider = get_ai_provider(settings=resolved_settings)
            ai_synthesis = provider.chat(
                _assistant_prompt(clean_question, evidence, citations, literature, facts, relevant_entities)
            )
            ai_used = True
            provider_name = provider.provider_name
        except AIProviderError as exc:
            limitations.append(f"AI synthesis was not used: {exc}")

    return AssistantAnswer(
        question=clean_question,
        direct_answer=ai_synthesis or local_answer,
        direct_matches=direct_matches,
        related_context=related_context,
        evidence_from_experiments=evidence,
        source_document_citations=citations,
        literature_context=literature,
        extracted_facts=facts,
        ai_synthesis=ai_synthesis or local_synthesis,
        limitations_uncertainties=limitations,
        sources=sources,
        ai_used=ai_used,
        provider=provider_name,
    )

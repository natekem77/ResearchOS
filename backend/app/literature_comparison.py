"""Lab-versus-literature comparison service for ResearchOS."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.ai_providers import AIProviderError, get_ai_provider
from app.config import Settings, get_settings
from app.research_assistant import (
    _experiment_evidence,
    _query_intent,
    _score_experiments,
    _search_documents,
    _source_citations,
    _split_experiment_relevance,
)
from app.retinal_ontology import build_retinal_ontology
from app.storage import SQLiteStore


@dataclass(frozen=True)
class LiteratureComparisonAnswer:
    """Structured lab-literature comparison response."""

    question: str
    direct_answer: str
    matching_lab_experiments: list[dict[str, Any]]
    matching_literature_sources: list[dict[str, Any]]
    relevant_source_documents: list[dict[str, Any]]
    similarities: list[str]
    differences: list[str]
    protocol_treatment_differences: list[str]
    limitations: list[str]
    citations: list[dict[str, Any]]
    ai_synthesis: str | None
    ai_used: bool
    provider: str


COMPARISON_FIELDS = [
    "compounds",
    "markers",
    "cell_line",
    "organoid_batch",
    "treatments",
    "concentrations",
    "time_points",
    "imaging_methods",
    "sequencing",
]


def _normalize_terms(values: list[str]) -> set[str]:
    """Normalize extracted scientific terms for local comparison."""

    return {value.strip().lower() for value in values if value and value.strip()}


def _experiment_terms(experiments: list[dict[str, Any]], field: str) -> set[str]:
    """Collect values for one structured experiment field."""

    terms: set[str] = set()
    for experiment in experiments:
        value = experiment.get(field)
        if isinstance(value, list):
            terms.update(_normalize_terms([str(item) for item in value]))
        elif value:
            terms.add(str(value).strip().lower())
    return terms


def _literature_text(literature_sources: list[dict[str, Any]]) -> str:
    """Flatten retrieved literature snippets for term matching."""

    return " ".join(
        str(source.get("title") or "") + " " + str(source.get("snippet") or "")
        for source in literature_sources
    ).lower()


def _literature_mentions(terms: set[str], literature_text: str) -> set[str]:
    """Return experiment terms explicitly mentioned in retrieved literature."""

    mentioned = set()
    for term in terms:
        if re.search(rf"(?<![A-Za-z0-9-]){re.escape(term)}(?![A-Za-z0-9-])", literature_text, re.I):
            mentioned.add(term)
    return mentioned


def _readable_terms(terms: set[str]) -> str:
    """Format normalized terms for user-facing comparison text."""

    readable = []
    for term in sorted(terms):
        value = re.sub(r"\bd(\d{1,3})\b", r"D\1", term)
        value = re.sub(r"\bnm\b", "nM", value)
        value = value.upper() if re.fullmatch(r"[a-z0-9-]{2,6}", value) else value
        readable.append(value)
    return ", ".join(readable)


def _similarities(
    lab_experiments: list[dict[str, Any]],
    literature_sources: list[dict[str, Any]],
) -> list[str]:
    """Describe fields that overlap between lab experiments and literature."""

    text = _literature_text(literature_sources)
    matches = []
    for field in COMPARISON_FIELDS:
        terms = _experiment_terms(lab_experiments, field)
        shared = _literature_mentions(terms, text)
        if shared:
            matches.append(f"Both lab records and literature mention {field.replace('_', ' ')}: {_readable_terms(shared)}.")
    return matches


def _differences(
    lab_experiments: list[dict[str, Any]],
    literature_sources: list[dict[str, Any]],
) -> list[str]:
    """Describe lab fields not detected in retrieved literature snippets."""

    text = _literature_text(literature_sources)
    differences = []
    for field in COMPARISON_FIELDS:
        terms = _experiment_terms(lab_experiments, field)
        missing = terms - _literature_mentions(terms, text)
        if missing:
            differences.append(
                f"Lab records include {field.replace('_', ' ')} not detected in retrieved literature snippets: "
                f"{_readable_terms(missing)}."
            )
    return differences


def _protocol_treatment_differences(
    lab_experiments: list[dict[str, Any]],
    literature_sources: list[dict[str, Any]],
) -> list[str]:
    """Extract practical protocol or treatment differences when detectable."""

    text = _literature_text(literature_sources)
    notes = []
    for field in ["treatments", "concentrations", "time_points"]:
        lab_terms = _experiment_terms(lab_experiments, field)
        if not lab_terms:
            continue
        matched = _literature_mentions(lab_terms, text)
        missing = lab_terms - matched
        if matched:
            notes.append(f"Treatment/protocol overlap for {field.replace('_', ' ')}: {_readable_terms(matched)}.")
        if missing:
            notes.append(
                f"Lab-specific {field.replace('_', ' ')} not found in retrieved literature snippets: "
                f"{_readable_terms(missing)}."
            )

    if "control" in text or "vehicle" in text or "dmso" in text:
        notes.append("Retrieved literature mentions controls or vehicle conditions; compare this against lab controls before drawing conclusions.")
    if "timing" in text or "day" in text or re.search(r"\bd\d{1,3}\b", text, re.I):
        notes.append("Retrieved literature discusses timing; align differentiation days and exposure windows before treating results as directly comparable.")
    return notes


def _comparison_direct_answer(
    lab_experiments: list[dict[str, Any]],
    literature_sources: list[dict[str, Any]],
    similarities: list[str],
    differences: list[str],
) -> str:
    """Build a readable local fallback answer."""

    if not lab_experiments and not literature_sources:
        return "I did not find matching lab experiments or literature sources in local ResearchOS storage."
    if not lab_experiments:
        return "I found relevant literature, but no matching lab experiments. Load demo notes or sync notebooks before comparing."
    if not literature_sources:
        return "I found relevant lab experiments, but no matching literature sources. Ingest papers before comparing."

    pieces = [
        f"I found {len(lab_experiments)} matching lab experiment(s) and {len(literature_sources)} literature source(s)."
    ]
    if similarities:
        pieces.append(similarities[0])
    if differences:
        pieces.append(differences[0])
    return " ".join(pieces)


def _comparison_prompt(
    question: str,
    lab_experiments: list[dict[str, Any]],
    literature_sources: list[dict[str, Any]],
    similarities: list[str],
    differences: list[str],
    protocol_differences: list[str],
    citations: list[dict[str, Any]],
) -> str:
    """Build an optional AI synthesis prompt."""

    return (
        "Compare internal lab experiments against retrieved literature using only the context below. "
        "Be concise, separate alignment from differences, cite snippets as [1], [2], and state limitations.\n\n"
        f"Question: {question}\n\n"
        f"Lab experiments:\n{lab_experiments}\n\n"
        f"Literature sources:\n{literature_sources}\n\n"
        f"Similarities:\n{similarities}\n\n"
        f"Differences:\n{differences}\n\n"
        f"Protocol/treatment differences:\n{protocol_differences}\n\n"
        f"Citations:\n{citations}"
    )


def compare_lab_with_literature(
    question: str,
    settings: Settings | None = None,
    use_ai: bool = True,
) -> LiteratureComparisonAnswer:
    """Compare local lab experiments against ingested literature."""

    resolved_settings = settings or get_settings()
    clean_question = question.strip()
    store = SQLiteStore(settings=resolved_settings)

    sources = _search_documents(clean_question, settings=resolved_settings, limit=12)
    literature_sources = [
        source for source in sources if source.get("provider") == "literature"
    ]
    lab_sources = [
        source for source in sources if source.get("provider") != "literature"
    ]

    experiments = store.list_experiments()
    lab_experiments = [
        experiment for experiment in experiments if experiment.get("source_provider") != "literature"
    ]
    documents = [document.__dict__ for document in store.get_all_research_documents()]
    ontology = build_retinal_ontology(experiments=experiments, documents=documents)
    intent = _query_intent(clean_question, ontology)
    direct_experiments, related_experiments = _split_experiment_relevance(
        _score_experiments(intent, lab_experiments, limit=8)
    )
    selected_experiments = direct_experiments or related_experiments
    lab_evidence = _experiment_evidence(selected_experiments, relevance="direct" if direct_experiments else "related")

    relevant_source_documents = lab_sources[:6]
    citations = _source_citations(relevant_source_documents + literature_sources[:6])
    similarities = _similarities(selected_experiments, literature_sources)
    differences = _differences(selected_experiments, literature_sources)
    protocol_differences = _protocol_treatment_differences(selected_experiments, literature_sources)
    local_answer = _comparison_direct_answer(
        selected_experiments,
        literature_sources,
        similarities,
        differences,
    )
    limitations = [
        "Comparison is limited to locally ingested lab notes and papers.",
        "Literature metadata and PDF text extraction are lightweight and may miss details.",
        "Protocol differences are inferred from retrieved snippets and structured fields, not full manual review.",
    ]
    if not literature_sources:
        limitations.append("No relevant literature chunks were retrieved; run /ingest/papers after adding paper files.")
    if not selected_experiments:
        limitations.append("No matching lab experiments were retrieved from structured experiment records.")

    ai_synthesis: str | None = None
    ai_used = False
    provider_name = "local-fallback"
    if use_ai:
        try:
            provider = get_ai_provider(settings=resolved_settings)
            ai_synthesis = provider.chat(
                _comparison_prompt(
                    clean_question,
                    lab_evidence,
                    literature_sources,
                    similarities,
                    differences,
                    protocol_differences,
                    citations,
                )
            )
            ai_used = True
            provider_name = provider.provider_name
        except AIProviderError as exc:
            limitations.append(f"AI synthesis was not used: {exc}")

    return LiteratureComparisonAnswer(
        question=clean_question,
        direct_answer=ai_synthesis or local_answer,
        matching_lab_experiments=lab_evidence,
        matching_literature_sources=literature_sources,
        relevant_source_documents=relevant_source_documents,
        similarities=similarities,
        differences=differences,
        protocol_treatment_differences=protocol_differences,
        limitations=limitations,
        citations=citations,
        ai_synthesis=ai_synthesis,
        ai_used=ai_used,
        provider=provider_name,
    )

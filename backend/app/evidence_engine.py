"""Scientific evidence synthesis for ResearchOS.

The Evidence Engine is deterministic and provenance-first. It does not invent
observations; every statement is derived from existing ResearchOS records and
includes source references.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings, get_settings
from app.global_knowledge_graph import KnowledgeGraphService
from app.scientific_memory import ScientificMemoryService
from app.storage import SQLiteStore


@dataclass(frozen=True)
class EvidenceSource:
    """One provenance source for an evidence statement."""

    source_type: str
    source_id: str
    title: str | None = None
    provider: str | None = None
    snippet: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "title": self.title,
            "provider": self.provider,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class EvidenceStatement:
    """A sourced scientific statement."""

    statement: str
    evidence_type: str
    sources: list[EvidenceSource]
    strength: str = "moderate"

    def as_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "evidence_type": self.evidence_type,
            "strength": self.strength,
            "sources": [source.as_dict() for source in self.sources],
        }


@dataclass(frozen=True)
class EvidenceConflict:
    """Potential disagreement between evidence statements."""

    conflict: str
    supporting_sources: list[EvidenceSource] = field(default_factory=list)
    contradictory_sources: list[EvidenceSource] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "conflict": self.conflict,
            "supporting_sources": [source.as_dict() for source in self.supporting_sources],
            "contradictory_sources": [source.as_dict() for source in self.contradictory_sources],
        }


@dataclass(frozen=True)
class EvidenceSummary:
    """Full evidence query response."""

    question: str
    summary: str
    supporting_evidence: list[EvidenceStatement]
    contradictory_evidence: list[EvidenceStatement]
    missing_evidence: list[EvidenceStatement]
    related_experiments: list[dict[str, Any]]
    related_literature: list[dict[str, Any]]
    confidence: dict[str, Any]
    recommendations: list[str]
    provenance: list[dict[str, Any]]
    observed_evidence: list[EvidenceStatement]
    conflicts: list[EvidenceConflict]

    def as_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "summary": self.summary,
            "observed_evidence": [item.as_dict() for item in self.observed_evidence],
            "supporting_evidence": [item.as_dict() for item in self.supporting_evidence],
            "contradictory_evidence": [item.as_dict() for item in self.contradictory_evidence],
            "missing_evidence": [item.as_dict() for item in self.missing_evidence],
            "related_experiments": self.related_experiments,
            "related_literature": self.related_literature,
            "confidence": self.confidence,
            "recommendations": self.recommendations,
            "provenance": self.provenance,
            "conflicts": [item.as_dict() for item in self.conflicts],
        }


class EvidenceEngine:
    """Synthesize evidence across ResearchOS providers using graph traversal."""

    def __init__(
        self,
        settings: Settings | None = None,
        store: SQLiteStore | None = None,
        knowledge_graph: KnowledgeGraphService | None = None,
        workspace_id: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or SQLiteStore(settings=self.settings)
        self.workspace_id = workspace_id
        self.knowledge_graph = knowledge_graph or KnowledgeGraphService(
            settings=self.settings,
            store=self.store,
            workspace_id=workspace_id,
        )

    def query(self, question: str) -> EvidenceSummary:
        """Return a provenance-backed evidence synthesis for a question."""

        clean_question = question.strip()
        if not clean_question:
            raise ValueError("Evidence question must not be empty.")
        entity_details = self._entity_details(clean_question)
        experiments = _dedupe_dicts(
            [experiment for detail in entity_details for experiment in detail.get("experiments", [])],
            key="id",
        )
        literature = _dedupe_dicts(
            [item for detail in entity_details for item in detail.get("literature", [])],
            key="id",
        )
        statistics = _dedupe_dicts(
            [
                item
                for detail in entity_details
                for item in [*(detail.get("statistics", []) or []), *(detail.get("graphpad_assets", []) or []), *(detail.get("spreadsheet_assets", []) or [])]
            ],
            key="asset_id",
        )
        microscopy = _dedupe_dicts(
            [item for detail in entity_details for item in detail.get("microscopy_assets", [])],
            key="asset_id",
        )
        memory = self._memory_for_experiments(experiments)

        observed = self._observed_statements(experiments, statistics, microscopy)
        supporting = self._supporting_statements(entity_details, experiments, statistics, literature, memory)
        contradictory = self._contradictory_statements(experiments, statistics)
        missing = self._missing_statements(experiments, statistics, literature, microscopy)
        confidence = self._confidence(experiments, statistics, literature, supporting, contradictory, missing)
        recommendations = self._recommendations(missing, contradictory, confidence)
        provenance = _provenance_from_statements([*observed, *supporting, *contradictory, *missing])
        summary = self._summary(clean_question, entity_details, experiments, statistics, literature, confidence)

        return EvidenceSummary(
            question=clean_question,
            summary=summary,
            observed_evidence=observed,
            supporting_evidence=supporting,
            contradictory_evidence=contradictory,
            missing_evidence=missing,
            related_experiments=experiments[:12],
            related_literature=literature[:12],
            confidence=confidence,
            recommendations=recommendations,
            provenance=provenance,
            conflicts=[EvidenceConflict(item.statement, contradictory_sources=item.sources) for item in contradictory],
        )

    def _entity_details(self, question: str) -> list[dict[str, Any]]:
        results = self.knowledge_graph.search(question, limit=8)
        if not results:
            for token in _candidate_terms(question):
                results.extend(self.knowledge_graph.search(token, limit=4))
        details = []
        seen = set()
        for result in results:
            entity_name = str(result.get("entity") or "")
            if not entity_name or entity_name.lower() in seen:
                continue
            detail = self.knowledge_graph.entity_detail(entity_name)
            if detail is not None:
                details.append(detail)
                seen.add(entity_name.lower())
        return details[:8]

    def _observed_statements(
        self,
        experiments: list[dict[str, Any]],
        statistics: list[dict[str, Any]],
        microscopy: list[dict[str, Any]],
    ) -> list[EvidenceStatement]:
        statements: list[EvidenceStatement] = []
        for experiment in experiments[:8]:
            conclusion = str(experiment.get("conclusions") or "").strip()
            notes = str(experiment.get("notes") or "").strip()
            if conclusion:
                statements.append(
                    EvidenceStatement(
                        statement=f"{experiment.get('experiment_id') or experiment.get('title') or experiment.get('id')} reports: {conclusion}",
                        evidence_type="observed",
                        sources=[_source("experiment", experiment, snippet=conclusion)],
                        strength="moderate",
                    )
                )
            elif notes:
                statements.append(
                    EvidenceStatement(
                        statement=f"{experiment.get('experiment_id') or experiment.get('title') or experiment.get('id')} contains notebook observations but no extracted conclusion.",
                        evidence_type="observed",
                        sources=[_source("experiment", experiment, snippet=notes[:240])],
                        strength="weak",
                    )
                )
        for asset in statistics[:6]:
            interpretation = _statistics_interpretation(asset)
            if interpretation:
                statements.append(
                    EvidenceStatement(
                        statement=interpretation,
                        evidence_type="observed",
                        sources=[_source("statistics", asset, snippet=interpretation)],
                        strength="strong" if _asset_has_p_value(asset) else "moderate",
                    )
                )
        if microscopy and not statistics:
            statements.append(
                EvidenceStatement(
                    statement=f"{len(microscopy)} microscopy/image asset(s) are linked, but quantitative interpretation requires analysis records.",
                    evidence_type="observed",
                    sources=[_source("microscopy", asset) for asset in microscopy[:4]],
                    strength="weak",
                )
            )
        return statements

    def _supporting_statements(
        self,
        entity_details: list[dict[str, Any]],
        experiments: list[dict[str, Any]],
        statistics: list[dict[str, Any]],
        literature: list[dict[str, Any]],
        memory: list[dict[str, Any]],
    ) -> list[EvidenceStatement]:
        statements: list[EvidenceStatement] = []
        for detail in entity_details[:4]:
            statements.append(
                EvidenceStatement(
                    statement=str(detail.get("summary") or f"{detail.get('entity')} is present in ResearchOS records."),
                    evidence_type="supporting",
                    sources=[EvidenceSource("knowledge_graph", str(detail.get("entity")), title=str(detail.get("entity")), provider="knowledge_graph")],
                    strength="moderate",
                )
            )
        if experiments:
            statements.append(
                EvidenceStatement(
                    statement=f"{len(experiments)} related experiment(s) reference the queried entities.",
                    evidence_type="supporting",
                    sources=[_source("experiment", experiment) for experiment in experiments[:6]],
                    strength="moderate",
                )
            )
        if statistics:
            statements.append(
                EvidenceStatement(
                    statement=f"{len(statistics)} quantitative/statistics asset(s) are linked through the Knowledge Graph.",
                    evidence_type="supporting",
                    sources=[_source("statistics", asset) for asset in statistics[:6]],
                    strength="strong" if any(_asset_has_p_value(asset) for asset in statistics) else "moderate",
                )
            )
        if literature:
            statements.append(
                EvidenceStatement(
                    statement=f"{len(literature)} literature record(s) are linked through shared scientific entities.",
                    evidence_type="supporting",
                    sources=[_source("literature", item) for item in literature[:6]],
                    strength="moderate",
                )
            )
        if memory:
            statements.append(
                EvidenceStatement(
                    statement="Scientific Memory found related historical experiments for comparison.",
                    evidence_type="supporting",
                    sources=[
                        EvidenceSource(
                            "scientific_memory",
                            str(item.get("experiment", {}).get("id") or item.get("experiment_id") or "memory"),
                            title=str(item.get("experiment", {}).get("title") or item.get("experiment", {}).get("experiment_id") or "Scientific Memory"),
                            provider="scientific_memory",
                        )
                        for item in memory[:5]
                        if isinstance(item, dict)
                    ],
                    strength="moderate",
                )
            )
        return statements

    def _contradictory_statements(
        self,
        experiments: list[dict[str, Any]],
        statistics: list[dict[str, Any]],
    ) -> list[EvidenceStatement]:
        negative = []
        for experiment in experiments:
            text = " ".join(str(experiment.get(key) or "") for key in ["title", "notes", "conclusions"]).lower()
            if any(term in text for term in ["no improvement", "decreased", "failed", "not significant", "no effect", "worse"]):
                negative.append(
                    EvidenceStatement(
                        statement=f"{experiment.get('experiment_id') or experiment.get('title') or experiment.get('id')} may report a negative or non-supportive outcome.",
                        evidence_type="contradictory",
                        sources=[_source("experiment", experiment)],
                        strength="moderate",
                    )
                )
        for asset in statistics:
            if _asset_has_non_significant_p_value(asset):
                negative.append(
                    EvidenceStatement(
                        statement=f"{asset.get('title') or asset.get('filename') or asset.get('asset_id')} includes non-significant statistical evidence.",
                        evidence_type="contradictory",
                        sources=[_source("statistics", asset)],
                        strength="moderate",
                    )
                )
        return negative[:8]

    def _missing_statements(
        self,
        experiments: list[dict[str, Any]],
        statistics: list[dict[str, Any]],
        literature: list[dict[str, Any]],
        microscopy: list[dict[str, Any]],
    ) -> list[EvidenceStatement]:
        missing = []
        if not experiments:
            missing.append("No related experiments were found in the Knowledge Graph.")
        if experiments and not statistics:
            missing.append("Related experiments do not yet have parsed quantitative/statistical evidence.")
        if experiments and not microscopy:
            missing.append("No microscopy/image assets are linked to the related experiments or entities.")
        if not literature:
            missing.append("No related literature records are currently linked.")
        if experiments and not any(str(item.get("conclusions") or "").strip() for item in experiments):
            missing.append("Related experiments lack extracted conclusions.")
        return [
            EvidenceStatement(
                statement=item,
                evidence_type="missing",
                sources=[],
                strength="moderate",
            )
            for item in missing
        ]

    def _confidence(
        self,
        experiments: list[dict[str, Any]],
        statistics: list[dict[str, Any]],
        literature: list[dict[str, Any]],
        supporting: list[EvidenceStatement],
        contradictory: list[EvidenceStatement],
        missing: list[EvidenceStatement],
    ) -> dict[str, Any]:
        independent_datasets = len(experiments) + len(statistics) + len(literature)
        agreement = max(0, len(supporting) - len(contradictory))
        statistical_support = sum(1 for asset in statistics if _asset_has_p_value(asset))
        literature_agreement = len(literature)
        score = (
            min(len(experiments), 5) * 0.18
            + min(len(statistics), 4) * 0.16
            + min(statistical_support, 3) * 0.12
            + min(literature_agreement, 4) * 0.08
            + min(agreement, 5) * 0.08
            - min(len(contradictory), 4) * 0.12
            - min(len(missing), 5) * 0.05
        )
        score = max(0.0, min(1.0, round(score, 2)))
        if score >= 0.7:
            level = "moderate-high"
        elif score >= 0.45:
            level = "moderate"
        elif score >= 0.2:
            level = "low"
        else:
            level = "insufficient"
        return {
            "level": level,
            "score": score,
            "factors": {
                "experiment_count": len(experiments),
                "independent_dataset_count": independent_datasets,
                "supporting_statement_count": len(supporting),
                "contradictory_statement_count": len(contradictory),
                "missing_evidence_count": len(missing),
                "statistical_support_count": statistical_support,
                "literature_record_count": len(literature),
            },
            "method": "deterministic_coverage_agreement_score",
        }

    def _recommendations(
        self,
        missing: list[EvidenceStatement],
        contradictory: list[EvidenceStatement],
        confidence: dict[str, Any],
    ) -> list[str]:
        recommendations = []
        missing_text = " ".join(item.statement for item in missing).lower()
        if "statistical" in missing_text:
            recommendations.append("Add or import quantitative analysis before making a strong scientific claim.")
        if "microscopy" in missing_text:
            recommendations.append("Link representative microscopy/image assets to the relevant experiments.")
        if "literature" in missing_text:
            recommendations.append("Ingest or link literature records for external comparison.")
        if contradictory:
            recommendations.append("Review contradictory/non-supportive records before summarizing the conclusion.")
        if confidence.get("level") in {"insufficient", "low"}:
            recommendations.append("Treat this as a hypothesis until independent datasets and statistical support are available.")
        return recommendations or ["Evidence is present; review source provenance before using it in a claim."]

    def _summary(
        self,
        question: str,
        entity_details: list[dict[str, Any]],
        experiments: list[dict[str, Any]],
        statistics: list[dict[str, Any]],
        literature: list[dict[str, Any]],
        confidence: dict[str, Any],
    ) -> str:
        entities = ", ".join(str(detail.get("entity")) for detail in entity_details[:5])
        if not entity_details:
            return f"No Knowledge Graph entities were found for '{question}'. Evidence is insufficient."
        return (
            f"Evidence for '{question}' centers on {entities}. ResearchOS found "
            f"{len(experiments)} experiment(s), {len(statistics)} quantitative/statistics asset(s), "
            f"and {len(literature)} literature record(s). Confidence is {confidence['level']} "
            f"based on coverage, agreement, statistical support, and missing evidence."
        )

    def _memory_for_experiments(self, experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not experiments:
            return []
        memory = ScientificMemoryService(
            settings=self.settings,
            store=self.store,
            knowledge_graph=self.knowledge_graph,
            workspace_id=self.workspace_id,
        )
        results = []
        for experiment in experiments[:3]:
            try:
                results.extend(memory.find_similar_experiments(str(experiment.get("id")), limit=2))
            except Exception:
                continue
        return results


def _candidate_terms(question: str) -> list[str]:
    stopwords = {"does", "do", "what", "which", "show", "about", "early", "late", "the", "and", "or", "with", "without", "improve"}
    return [
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+_.-]{1,}", question)
        if token.lower() not in stopwords
    ]


def _source(source_type: str, payload: dict[str, Any], snippet: str | None = None) -> EvidenceSource:
    source_id = str(payload.get("id") or payload.get("asset_id") or payload.get("document_id") or payload.get("experiment_id") or "")
    return EvidenceSource(
        source_type=source_type,
        source_id=source_id,
        title=str(payload.get("title") or payload.get("filename") or payload.get("experiment_id") or source_id),
        provider=str(payload.get("provider") or payload.get("source_provider") or source_type),
        snippet=snippet,
    )


def _statistics_interpretation(asset: dict[str, Any]) -> str | None:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    statistics = metadata.get("statistics") if isinstance(metadata, dict) and isinstance(metadata.get("statistics"), dict) else None
    if not statistics:
        return None
    interpretations = statistics.get("interpretations") if isinstance(statistics.get("interpretations"), list) else []
    if interpretations:
        return str(interpretations[0])
    variables = ", ".join(str(item) for item in statistics.get("variables", [])[:4]) if isinstance(statistics.get("variables"), list) else ""
    p_values = _p_values(statistics)
    if p_values:
        return f"{asset.get('title') or asset.get('filename') or asset.get('asset_id')} reports statistics for {variables or 'measured variables'} with p-values {', '.join(map(str, p_values[:4]))}."
    return f"{asset.get('title') or asset.get('filename') or asset.get('asset_id')} contains parsed quantitative statistics for {variables or 'measured variables'}."


def _asset_has_p_value(asset: dict[str, Any]) -> bool:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    statistics = metadata.get("statistics") if isinstance(metadata, dict) and isinstance(metadata.get("statistics"), dict) else None
    return bool(statistics and _p_values(statistics))


def _asset_has_non_significant_p_value(asset: dict[str, Any]) -> bool:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    statistics = metadata.get("statistics") if isinstance(metadata, dict) and isinstance(metadata.get("statistics"), dict) else None
    return any(value >= 0.05 for value in _p_values(statistics or {}))


def _p_values(statistics: dict[str, Any]) -> list[float]:
    values = []
    raw_values = statistics.get("p_values")
    if isinstance(raw_values, list):
        values.extend(_float_or_none(value) for value in raw_values)
    rows = statistics.get("rows")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                for key in ["p_value", "p", "adjusted_p_value", "padj", "q_value", "fdr"]:
                    if key in row:
                        values.append(_float_or_none(row[key]))
    return [value for value in values if value is not None and 0 <= value <= 1]


def _float_or_none(value: object) -> float | None:
    try:
        return float(str(value).replace("<", "").strip())
    except (TypeError, ValueError):
        return None


def _dedupe_dicts(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_key = str(item.get(key) or item.get("id") or item.get("asset_id") or item.get("title") or item)
        if item_key in seen:
            continue
        seen.add(item_key)
        deduped.append(item)
    return deduped


def _provenance_from_statements(statements: list[EvidenceStatement]) -> list[dict[str, Any]]:
    seen = set()
    provenance = []
    for statement in statements:
        for source in statement.sources:
            key = (source.source_type, source.source_id)
            if key in seen:
                continue
            seen.add(key)
            provenance.append(source.as_dict())
    return provenance

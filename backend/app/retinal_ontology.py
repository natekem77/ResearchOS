"""Retinal organoid ontology and entity-linking helpers."""

from __future__ import annotations

import re
from typing import Any


KNOWN_COMPOUNDS = ["BMP4", "SAG", "DMSO", "CHIR99021", "IWR-1", "FGF2", "BDNF"]
KNOWN_MARKERS = ["SIX6", "BRN3B", "DAPI", "PAX6", "VSX2", "RAX", "OTX2", "CRX", "NRL"]
KNOWN_CELL_TYPES = [
    "retinal progenitor",
    "retinal ganglion cell",
    "photoreceptor",
    "amacrine cell",
    "bipolar cell",
    "Muller glia",
]
KNOWN_IMAGING = ["brightfield", "fluorescence", "confocal", "microscopy", "immunostaining"]
KNOWN_SEQUENCING = ["RNA-seq", "scRNA-seq", "single-cell RNA-seq", "ATAC-seq"]
KNOWN_FLOW = ["flow cytometry", "FACS"]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        normalized = re.sub(r"\s+", " ", value.strip(" .;:,"))
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            results.append(normalized)
    return results


def _contains_term(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.I))


def _entity_terms(text: str, known_terms: list[str]) -> list[str]:
    return [term for term in known_terms if _contains_term(text, term)]


def _document_text(document: dict[str, Any]) -> str:
    return " ".join(str(document.get(key) or "") for key in ["title", "content", "source_path"])


def build_retinal_ontology(
    experiments: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Build linked retinal organoid ontology entities from local ResearchOS data."""

    ontology: dict[str, dict[str, dict[str, Any]]] = {
        "experiment-ids": {},
        "cell-lines": {},
        "organoid-batches": {},
        "differentiation-days": {},
        "compounds": {},
        "concentrations": {},
        "treatment-windows": {},
        "markers": {},
        "cell-types": {},
        "imaging-modalities": {},
        "rna-seq": {},
        "flow-cytometry": {},
        "protocols": {},
    }

    def ensure(entity_type: str, name: str) -> dict[str, Any]:
        bucket = ontology[entity_type]
        key = name.lower()
        if key not in bucket:
            bucket[key] = {
                "type": entity_type,
                "name": name,
                "experiments": [],
                "documents": [],
                "protocols": [],
                "images": [],
                "ai_summaries": [],
            }
        return bucket[key]

    def link(entity_type: str, name: str, experiment: dict[str, Any] | None, document: dict[str, Any] | None) -> None:
        entity = ensure(entity_type, name)
        if experiment and all(item["id"] != experiment["id"] for item in entity["experiments"]):
            entity["experiments"].append(_experiment_summary(experiment))
            if experiment.get("conclusions"):
                entity["ai_summaries"].append(
                    {
                        "title": experiment["title"],
                        "summary": experiment["conclusions"],
                        "source": "extracted-conclusion",
                    }
                )
        if document and all(item["id"] != document["id"] for item in entity["documents"]):
            entity["documents"].append(_document_summary(document))
            if "protocol" in str(document.get("title", "")).lower():
                entity["protocols"].append(_document_summary(document))

    documents_by_id = {document["id"]: document for document in documents}

    for experiment in experiments:
        document = documents_by_id.get(experiment.get("source_document_id"))
        joined = " ".join(
            [
                str(experiment.get("title") or ""),
                str(experiment.get("notes") or ""),
                str(experiment.get("conclusions") or ""),
                _document_text(document or {}),
            ]
        )

        for name in [experiment.get("experiment_id")]:
            if name:
                link("experiment-ids", str(name), experiment, document)
        for name in [experiment.get("cell_line")]:
            if name:
                link("cell-lines", str(name), experiment, document)
        for name in [experiment.get("organoid_batch")]:
            if name:
                link("organoid-batches", str(name), experiment, document)

        for entity_type, values in [
            ("compounds", _unique((experiment.get("compounds") or []) + _entity_terms(joined, KNOWN_COMPOUNDS))),
            ("concentrations", experiment.get("concentrations") or []),
            ("treatment-windows", experiment.get("time_points") or []),
            ("markers", _unique((experiment.get("markers") or []) + _entity_terms(joined, KNOWN_MARKERS))),
            ("cell-types", _entity_terms(joined, KNOWN_CELL_TYPES)),
            ("imaging-modalities", _unique((experiment.get("imaging_methods") or []) + _entity_terms(joined, KNOWN_IMAGING))),
            ("rna-seq", _unique((experiment.get("sequencing") or []) + _entity_terms(joined, KNOWN_SEQUENCING))),
            ("flow-cytometry", _entity_terms(joined, KNOWN_FLOW)),
        ]:
            for name in values:
                link(entity_type, name, experiment, document)

        for day in re.findall(r"\bD(?:0|[1-9]\d?|1\d\d|200)\b", joined, flags=re.I):
            link("differentiation-days", day.upper(), experiment, document)

    for document in documents:
        text = _document_text(document)
        if "protocol" in text.lower():
            link("protocols", document["title"], None, document)
        for entity_type, terms in [
            ("compounds", KNOWN_COMPOUNDS),
            ("markers", KNOWN_MARKERS),
            ("cell-types", KNOWN_CELL_TYPES),
            ("imaging-modalities", KNOWN_IMAGING),
            ("rna-seq", KNOWN_SEQUENCING),
            ("flow-cytometry", KNOWN_FLOW),
        ]:
            for name in _entity_terms(text, terms):
                link(entity_type, name, None, document)
        for day in re.findall(r"\bD(?:0|[1-9]\d?|1\d\d|200)\b", text, flags=re.I):
            link("differentiation-days", day.upper(), None, document)

    return {
        entity_type: sorted(records.values(), key=lambda item: (-len(item["experiments"]), item["name"].lower()))
        for entity_type, records in ontology.items()
    }


def _experiment_summary(experiment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": experiment["id"],
        "experiment_id": experiment.get("experiment_id"),
        "title": experiment["title"],
        "date": experiment.get("date"),
        "provider": experiment.get("source_provider"),
    }


def _document_summary(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": document["id"],
        "title": document["title"],
        "provider": document.get("provider"),
        "source_path": document.get("source_path"),
        "source_url": document.get("source_url"),
    }

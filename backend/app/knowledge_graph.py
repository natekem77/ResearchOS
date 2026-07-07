"""Local knowledge graph assembly for ResearchOS.

The graph explorer is intentionally derived from the existing local SQLite
records. It does not create a new database or call cloud services; it links
documents, papers, experiments, and extracted entities at request time.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.retinal_ontology import KNOWN_COMPOUNDS, KNOWN_MARKERS
from app.storage import SQLiteStore

ENTITY_TYPE_ALIASES = {
    "compound": "compounds",
    "compounds": "compounds",
    "marker": "markers",
    "markers": "markers",
    "gene": "genes",
    "genes": "genes",
    "paper": "papers",
    "papers": "papers",
    "literature": "papers",
    "protocol": "protocols",
    "protocols": "protocols",
    "cell-line": "cell-lines",
    "cell-lines": "cell-lines",
    "cell_line": "cell-lines",
    "batch": "organoid-batches",
    "batches": "organoid-batches",
    "organoid-batch": "organoid-batches",
    "organoid-batches": "organoid-batches",
    "experiment": "experiments",
    "experiments": "experiments",
}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def _contains(text: str, term: str) -> bool:
    if not term:
        return False
    return bool(re.search(rf"(?<![A-Za-z0-9-]){re.escape(term)}(?![A-Za-z0-9-])", text, re.I))


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value or "").strip(" .;:,"))
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            results.append(cleaned)
    return results


def _metadata_terms(document: dict[str, Any], key: str) -> list[str]:
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    raw = str((metadata or {}).get(key) or "")
    return _unique([item.strip() for item in raw.split(",") if item.strip()])


def _document_text(document: dict[str, Any]) -> str:
    return " ".join(
        str(document.get(key) or "")
        for key in ["title", "content", "source_path", "source_url"]
    )


def _document_summary(document: dict[str, Any]) -> dict[str, object]:
    return {
        "id": document["id"],
        "title": document["title"],
        "provider": document.get("provider"),
        "source_path": document.get("source_path"),
        "source_url": document.get("source_url"),
        "updated_at": document.get("updated_at"),
    }


def _paper_summary(document: dict[str, Any]) -> dict[str, object]:
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    return _document_summary(document) | {
        "authors": (metadata or {}).get("authors") or None,
        "year": (metadata or {}).get("year") or None,
        "journal": (metadata or {}).get("journal") or None,
        "doi": (metadata or {}).get("doi") or None,
        "compounds": _metadata_terms(document, "compounds"),
        "markers": _metadata_terms(document, "markers"),
        "genes": _metadata_terms(document, "genes"),
    }


def _asset_markers(asset: dict[str, Any]) -> list[str]:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    raw_markers = metadata.get("markers") if isinstance(metadata, dict) else []
    if isinstance(raw_markers, list):
        return _unique([str(marker) for marker in raw_markers if str(marker).strip()])
    if isinstance(raw_markers, str):
        return _unique([marker.strip() for marker in raw_markers.split(",") if marker.strip()])
    return []


def _is_image_asset(asset: dict[str, Any]) -> bool:
    return str(asset.get("provider") or "") == "microscopy" or str(asset.get("asset_type") or "") in {
        "image",
        "microscopy",
    }


def _image_asset_summary(asset: dict[str, Any]) -> dict[str, object]:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    return {
        "asset_id": asset.get("asset_id"),
        "asset_type": asset.get("asset_type"),
        "title": asset.get("title"),
        "filename": asset.get("filename"),
        "provider": asset.get("provider"),
        "path": asset.get("path"),
        "experiment_id": asset.get("experiment_id"),
        "markers": _asset_markers(asset),
        "timepoint": metadata.get("timepoint") if isinstance(metadata, dict) else None,
        "updated_at": asset.get("updated_at"),
    }


def _experiment_summary(experiment: dict[str, Any]) -> dict[str, object]:
    return {
        "id": experiment["id"],
        "experiment_id": experiment.get("experiment_id"),
        "title": experiment.get("title"),
        "date": experiment.get("date"),
        "provider": experiment.get("source_provider"),
        "compounds": experiment.get("compounds") or [],
        "markers": experiment.get("markers") or [],
        "cell_line": experiment.get("cell_line"),
        "organoid_batch": experiment.get("organoid_batch"),
        "notes": experiment.get("notes"),
        "conclusions": experiment.get("conclusions"),
    }


def _extract_genes(text: str) -> list[str]:
    symbols = re.findall(r"\b[A-Z][A-Z0-9]{2,7}\b", text)
    excluded = {"PDF", "DOI", "RNA", "DNA", "API", "DMSO"}
    return _unique([symbol for symbol in symbols if symbol not in excluded])[:40]


def _all_terms(experiment: dict[str, Any] | None = None, document: dict[str, Any] | None = None) -> dict[str, list[str]]:
    text = _document_text(document or {})
    if experiment:
        text = " ".join(
            [
                text,
                str(experiment.get("title") or ""),
                str(experiment.get("notes") or ""),
                str(experiment.get("conclusions") or ""),
            ]
        )

    compounds = list(experiment.get("compounds") or []) if experiment else []
    markers = list(experiment.get("markers") or []) if experiment else []
    if document:
        compounds.extend(_metadata_terms(document, "compounds"))
        markers.extend(_metadata_terms(document, "markers"))

    compounds.extend([term for term in KNOWN_COMPOUNDS if _contains(text, term)])
    markers.extend([term for term in KNOWN_MARKERS if _contains(text, term)])

    return {
        "compounds": _unique(compounds),
        "markers": _unique(markers),
        "genes": _unique((_metadata_terms(document or {}, "genes") if document else []) + _extract_genes(text)),
        "cell_lines": _unique([str(experiment.get("cell_line") or "")] if experiment else []),
        "batches": _unique([str(experiment.get("organoid_batch") or "")] if experiment else []),
    }


def _citation(document: dict[str, Any], entity_name: str) -> dict[str, object]:
    text = re.sub(r"\s+", " ", str(document.get("content") or "")).strip()
    index = text.lower().find(entity_name.lower())
    if index >= 0:
        start = max(0, index - 120)
        end = min(len(text), index + 220)
        snippet = text[start:end].strip()
    else:
        snippet = text[:320]
    return _document_summary(document) | {"snippet": snippet}


def _timeline_item(kind: str, title: str, date: str | None, source_id: str) -> dict[str, object]:
    return {
        "kind": kind,
        "title": title,
        "date": date,
        "source_id": source_id,
    }


def _matches_entity(entity_type: str, entity_name: str, experiment: dict[str, Any] | None, document: dict[str, Any] | None) -> bool:
    key = _normalize(entity_name)
    terms = _all_terms(experiment=experiment, document=document)
    if entity_type == "compounds":
        return any(_normalize(term) == key for term in terms["compounds"])
    if entity_type == "markers":
        return any(_normalize(term) == key for term in terms["markers"])
    if entity_type == "genes":
        return any(_normalize(term) == key for term in terms["genes"])
    if entity_type == "cell-lines":
        return any(_normalize(term) == key for term in terms["cell_lines"])
    if entity_type == "organoid-batches":
        return any(_normalize(term) == key for term in terms["batches"])
    if entity_type == "experiments" and experiment:
        return key in {
            _normalize(str(experiment.get("id") or "")),
            _normalize(str(experiment.get("experiment_id") or "")),
            _normalize(str(experiment.get("title") or "")),
        }
    if entity_type in {"papers", "protocols"} and document:
        is_paper = document.get("provider") == "literature"
        is_protocol = "protocol" in _document_text(document).lower()
        if entity_type == "papers" and not is_paper:
            return False
        if entity_type == "protocols" and not is_protocol:
            return False
        return key in {
            _normalize(str(document.get("id") or "")),
            _normalize(str(document.get("title") or "")),
            _normalize(str(document.get("source_path") or "")),
        }
    return False


def _entity_overview(
    entity_type: str,
    entity_name: str,
    experiments: list[dict[str, object]],
    papers: list[dict[str, object]],
    protocols: list[dict[str, object]],
) -> str:
    label = entity_type.replace("-", " ")
    pieces = [
        f"{entity_name} is represented as a {label} entity in the local ResearchOS graph.",
        f"It is linked to {len(experiments)} experiment(s), {len(papers)} paper(s), and {len(protocols)} protocol document(s).",
    ]
    if experiments:
        pieces.append("The strongest lab evidence comes from direct structured experiment matches.")
    if papers:
        pieces.append("Literature links come from locally ingested paper metadata and extracted text.")
    return " ".join(pieces)


def _ai_summary(
    entity_name: str,
    experiments: list[dict[str, object]],
    papers: list[dict[str, object]],
    protocols: list[dict[str, object]],
) -> str:
    if not experiments and not papers and not protocols:
        return f"No local ResearchOS evidence is currently linked to {entity_name}."

    claims = []
    if experiments:
        titles = ", ".join(str(item.get("title") or item.get("experiment_id")) for item in experiments[:3])
        claims.append(f"Lab context: {titles}.")
    if papers:
        titles = ", ".join(str(item.get("title")) for item in papers[:3])
        claims.append(f"Literature context: {titles}.")
    if protocols:
        titles = ", ".join(str(item.get("title")) for item in protocols[:3])
        claims.append(f"Protocol context: {titles}.")
    return " ".join(claims)


def build_knowledge_graph_entity(store: SQLiteStore, entity_type: str, entity_name: str) -> dict[str, object]:
    """Return the local graph neighborhood for one entity."""

    normalized_type = ENTITY_TYPE_ALIASES.get(entity_type)
    if normalized_type is None:
        raise ValueError(f"Unsupported graph entity type: {entity_type}")

    documents = [document.__dict__ for document in store.get_all_research_documents()]
    documents_by_id = {document["id"]: document for document in documents}
    experiments = store.list_experiments()
    assets = store.list_assets()

    matched_experiments = []
    matched_documents = []
    for experiment in experiments:
        document = documents_by_id.get(experiment.get("source_document_id"))
        if _matches_entity(normalized_type, entity_name, experiment, document):
            matched_experiments.append(experiment)
            if document:
                matched_documents.append(document)

    for document in documents:
        if _matches_entity(normalized_type, entity_name, None, document) or (
            normalized_type not in {"experiments", "papers", "protocols"} and _contains(_document_text(document), entity_name)
        ):
            matched_documents.append(document)

    matched_documents = list({document["id"]: document for document in matched_documents}.values())
    related_papers = [_paper_summary(document) for document in matched_documents if document.get("provider") == "literature"]
    related_protocols = [
        _document_summary(document)
        for document in matched_documents
        if "protocol" in _document_text(document).lower()
    ]
    related_experiments = [_experiment_summary(experiment) for experiment in matched_experiments]
    related_images = []
    if normalized_type in {"markers", "genes"}:
        key_name = _normalize(entity_name)
        related_images = [
            _image_asset_summary(asset)
            for asset in assets
            if _is_image_asset(asset)
            and any(_normalize(marker) == key_name for marker in _asset_markers(asset))
        ]

    related_terms = {"compounds": [], "markers": [], "genes": [], "cell_lines": [], "batches": []}
    for experiment in matched_experiments:
        document = documents_by_id.get(experiment.get("source_document_id"))
        terms = _all_terms(experiment=experiment, document=document)
        for key, values in terms.items():
            related_terms[key].extend(values)
    for document in matched_documents:
        terms = _all_terms(document=document)
        for key, values in terms.items():
            related_terms[key].extend(values)

    related_terms = {key: _unique(values) for key, values in related_terms.items()}
    key_name = _normalize(entity_name)
    if normalized_type == "compounds":
        related_terms["compounds"] = [term for term in related_terms["compounds"] if _normalize(term) != key_name]
    if normalized_type in {"markers", "genes"}:
        related_terms["markers"] = [term for term in related_terms["markers"] if _normalize(term) != key_name]
        related_terms["genes"] = [term for term in related_terms["genes"] if _normalize(term) != key_name]

    timeline = []
    for experiment in matched_experiments:
        timeline.append(_timeline_item("experiment", str(experiment.get("title") or ""), experiment.get("date"), str(experiment.get("id"))))
    for document in matched_documents:
        timeline.append(
            _timeline_item(
                "paper" if document.get("provider") == "literature" else "document",
                str(document.get("title") or ""),
                document.get("updated_at") or document.get("created_at"),
                str(document.get("id")),
            )
        )
    for image in related_images:
        timeline.append(
            _timeline_item(
                "image",
                str(image.get("title") or image.get("filename") or "Microscopy image"),
                image.get("updated_at"),
                str(image.get("asset_id") or ""),
            )
        )
    timeline = sorted(timeline, key=lambda item: str(item.get("date") or ""), reverse=True)[:20]

    citations = [_citation(document, entity_name) for document in matched_documents[:12]]
    relationship_counts = {
        "experiments": len(related_experiments),
        "papers": len(related_papers),
        "protocols": len(related_protocols),
        "compounds": len(related_terms["compounds"]),
        "markers": len(related_terms["markers"]),
        "genes": len(related_terms["genes"]),
        "cell_lines": len(related_terms["cell_lines"]),
        "batches": len(related_terms["batches"]),
        "images": len(related_images),
        "citations": len(citations),
    }

    if not related_experiments and not related_papers and not related_protocols and not related_images and not citations:
        raise LookupError(f"Graph entity not found: {entity_type}/{entity_name}")

    return {
        "type": normalized_type,
        "name": entity_name,
        "overview": _entity_overview(normalized_type, entity_name, related_experiments, related_papers, related_protocols),
        "related_experiments": related_experiments,
        "related_papers": related_papers,
        "related_protocols": related_protocols,
        "related_compounds": related_terms["compounds"],
        "related_markers": related_terms["markers"],
        "related_cell_lines": related_terms["cell_lines"],
        "related_batches": related_terms["batches"],
        "related_genes": related_terms["genes"],
        "related_images": related_images,
        "timeline": timeline,
        "ai_summary": _ai_summary(entity_name, related_experiments, related_papers, related_protocols),
        "source_citations": citations,
        "relationship_counts": relationship_counts,
    }


def build_knowledge_graph_stats(store: SQLiteStore) -> dict[str, object]:
    """Return graph-level counts, relationship counts, and visualization data."""

    documents = [document.__dict__ for document in store.get_all_research_documents()]
    documents_by_id = {document["id"]: document for document in documents}
    experiments = store.list_experiments()
    nodes: dict[str, dict[str, object]] = {}
    links: list[dict[str, object]] = []
    relationship_counts: Counter[str] = Counter()

    def add_node(node_type: str, node_id: str, label: str) -> None:
        nodes.setdefault(node_id, {"id": node_id, "type": node_type, "label": label})

    def add_link(source: str, target: str, relationship: str) -> None:
        links.append({"source": source, "target": target, "relationship": relationship})
        relationship_counts[relationship] += 1

    for document in documents:
        doc_type = "paper" if document.get("provider") == "literature" else "document"
        if "protocol" in _document_text(document).lower():
            doc_type = "protocol"
        add_node(doc_type, str(document["id"]), str(document["title"]))
        terms = _all_terms(document=document)
        for node_type, values in [
            ("compound", terms["compounds"]),
            ("marker", terms["markers"]),
            ("gene", terms["genes"]),
        ]:
            for value in values:
                node_id = f"{node_type}:{_normalize(value)}"
                add_node(node_type, node_id, value)
                add_link(str(document["id"]), node_id, f"{doc_type}-{node_type}")

    for experiment in experiments:
        experiment_id = str(experiment["id"])
        add_node("experiment", experiment_id, str(experiment.get("experiment_id") or experiment.get("title") or experiment_id))
        source_document_id = str(experiment.get("source_document_id") or "")
        if source_document_id in documents_by_id:
            add_link(experiment_id, source_document_id, "experiment-source")

        terms = _all_terms(experiment=experiment, document=documents_by_id.get(source_document_id))
        for node_type, values in [
            ("compound", terms["compounds"]),
            ("marker", terms["markers"]),
            ("gene", terms["genes"]),
            ("cell-line", terms["cell_lines"]),
            ("organoid-batch", terms["batches"]),
        ]:
            for value in values:
                node_id = f"{node_type}:{_normalize(value)}"
                add_node(node_type, node_id, value)
                add_link(experiment_id, node_id, f"experiment-{node_type}")

    entity_counts = Counter(str(node["type"]) for node in nodes.values())
    return {
        "entity_counts": dict(sorted(entity_counts.items())),
        "relationship_counts": dict(sorted(relationship_counts.items())),
        "node_count": len(nodes),
        "edge_count": len(links),
        "nodes": list(nodes.values())[:160],
        "links": links[:260],
    }

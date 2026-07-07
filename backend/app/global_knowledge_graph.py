"""Provider-agnostic global knowledge graph for ResearchOS.

The graph is derived from existing SQLite records and provider metadata. It is
not a second database. Providers contribute entities by storing structured
metadata, especially ``metadata["entities"]`` dictionaries, and this service
builds relationships across documents, experiments, assets, statistics, and
pending notebook entries.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from app.config import Settings, get_settings
from app.statistics_engine import interpret_statistics_asset
from app.storage import SQLiteStore


ENTITY_FIELD_ALIASES = {
    "compound": "compound",
    "compounds": "compound",
    "drug": "compound",
    "drugs": "compound",
    "marker": "marker",
    "markers": "marker",
    "gene": "gene",
    "genes": "gene",
    "protein": "protein",
    "proteins": "protein",
    "antibody": "antibody",
    "antibodies": "antibody",
    "cell_line": "cell_line",
    "cell_lines": "cell_line",
    "patient": "patient",
    "patients": "patient",
    "patient_id": "patient",
    "patient_ids": "patient",
    "animal": "animal",
    "animals": "animal",
    "animal_id": "animal",
    "animal_ids": "animal",
    "sample": "sample",
    "samples": "sample",
    "sample_id": "sample",
    "sample_ids": "sample",
    "sample_batch": "sample_batch",
    "sample_batches": "sample_batch",
    "batch": "sample_batch",
    "batches": "sample_batch",
    "organoid_batch": "organoid_batch",
    "organoid_batches": "organoid_batch",
    "cell_population": "cell_population",
    "cell_populations": "cell_population",
    "cluster": "sequencing_cluster",
    "clusters": "sequencing_cluster",
    "sequencing_cluster": "sequencing_cluster",
    "sequencing_clusters": "sequencing_cluster",
    "treatment": "treatment",
    "treatments": "treatment",
    "unknown_scientific_term": "unknown_scientific_term",
    "unknown_scientific_terms": "unknown_scientific_term",
}
EXCLUDED_ENTITY_VALUES = {"", "none", "null", "n/a", "na", "unknown", "not available"}
EXCLUDED_METADATA_KEYS = {
    "abstract",
    "content",
    "created_at",
    "created_timestamp",
    "extension",
    "filename",
    "limitations",
    "metadata",
    "modified_timestamp",
    "notes",
    "parser",
    "path",
    "source_folder",
    "source_path",
    "source_url",
    "title",
    "updated_at",
}


@dataclass
class KnowledgeGraphRelationship:
    """A relationship between an entity and a ResearchOS object."""

    object_type: str
    object_id: str
    source: str
    relationship_type: str
    where: str
    title: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "object_type": self.object_type,
            "object_id": self.object_id,
            "source": self.source,
            "relationship_type": self.relationship_type,
            "where": self.where,
            "title": self.title,
        }


@dataclass
class KnowledgeGraphEntity:
    """One normalized scientific entity node."""

    canonical_key: str
    name: str
    entity_type: str
    variants: Counter[str] = field(default_factory=Counter)
    relationships: list[KnowledgeGraphRelationship] = field(default_factory=list)
    related: Counter[str] = field(default_factory=Counter)

    def add_variant(self, value: str) -> None:
        self.variants[value] += 1
        self.name = _best_display_name(self.variants)


@dataclass
class KnowledgeGraph:
    """In-memory graph snapshot built from the current local database."""

    entities: dict[str, KnowledgeGraphEntity] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    relationships: list[KnowledgeGraphRelationship] = field(default_factory=list)
    object_entities: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    experiments: dict[str, dict[str, Any]] = field(default_factory=dict)
    documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    assets: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending_entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    built_at: float = 0.0
    build_seconds: float = 0.0


class KnowledgeGraphService:
    """Build and query the global ResearchOS knowledge graph."""

    def __init__(self, settings: Settings | None = None, store: SQLiteStore | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or SQLiteStore(settings=self.settings)
        self._graph: KnowledgeGraph | None = None
        self._fingerprint: tuple[int, int] | None = None

    def build(self) -> KnowledgeGraph:
        """Build a fresh graph from provider metadata already stored in SQLite."""

        started = perf_counter()
        graph = KnowledgeGraph()
        documents = [document.__dict__ for document in self.store.get_all_research_documents()]
        experiments = self.store.list_experiments()
        assets = self.store.list_assets(query=None)
        pending_entries = [self.store.get_pending_entry(entry["id"]) for entry in self.store.list_pending_entries()]

        graph.documents = {str(document["id"]): document for document in documents}
        graph.experiments = {str(experiment["id"]): experiment for experiment in experiments}
        graph.assets = {str(asset["asset_id"]): asset for asset in assets}
        graph.pending_entries = {str(entry["id"]): entry for entry in pending_entries if entry}

        self._register_aliases(graph, documents, assets, pending_entries)

        for document in documents:
            object_type = "literature" if document.get("provider") == "literature" else "notebook_entry"
            entities = _entities_from_document(document)
            self._add_object_entities(graph, object_type, str(document["id"]), document, entities, "document metadata")

        for experiment in experiments:
            entities = _entities_from_experiment(experiment)
            self._add_object_entities(
                graph,
                "experiment",
                str(experiment["id"]),
                experiment,
                entities,
                "experiment extraction",
            )
            source_document_id = str(experiment.get("source_document_id") or "")
            if source_document_id in graph.documents:
                experiment_entity_keys = graph.object_entities.get(f"experiment:{experiment['id']}", set())
                graph.object_entities[f"notebook_entry:{source_document_id}"].update(experiment_entity_keys)
                source_document = graph.documents[source_document_id]
                for entity_key in experiment_entity_keys:
                    entity = graph.entities.get(entity_key)
                    if entity is None:
                        continue
                    relationship = KnowledgeGraphRelationship(
                        object_type="notebook_entry",
                        object_id=source_document_id,
                        source=str(source_document.get("provider") or "document"),
                        relationship_type=f"source_document_for_{entity.entity_type}",
                        where="experiment source document",
                        title=str(source_document.get("title") or source_document_id),
                    )
                    entity.relationships.append(relationship)
                    graph.relationships.append(relationship)

        for asset in assets:
            entities = _entities_from_asset(asset)
            object_type = _asset_object_type(asset)
            self._add_object_entities(
                graph,
                object_type,
                str(asset["asset_id"]),
                asset,
                entities,
                "asset metadata",
            )
            if _asset_has_statistics(asset):
                statistics_entities = _entities_from_statistics(asset, self.settings)
                self._add_object_entities(
                    graph,
                    object_type,
                    str(asset["asset_id"]),
                    asset,
                    statistics_entities,
                    "statistics metadata",
                )
                self._add_object_entities(
                    graph,
                    "statistical_analysis",
                    str(asset["asset_id"]),
                    asset,
                    statistics_entities,
                    "statistics metadata",
                )

        for entry in pending_entries:
            if not entry:
                continue
            entities = _entities_from_pending_entry(entry)
            self._add_object_entities(
                graph,
                "notebook_entry",
                str(entry["id"]),
                entry,
                entities,
                "pending entry metadata",
            )

        self._calculate_co_occurrence(graph)
        graph.build_seconds = perf_counter() - started
        graph.built_at = perf_counter()
        return graph

    def refresh(self) -> KnowledgeGraph:
        """Force a rebuild and update the cache fingerprint."""

        self._graph = self.build()
        self._fingerprint = self._current_fingerprint()
        return self._graph

    def get_graph(self) -> KnowledgeGraph:
        """Return cached graph, rebuilding when the SQLite database changes."""

        fingerprint = self._current_fingerprint()
        if self._graph is None or self._fingerprint != fingerprint:
            self._graph = self.build()
            self._fingerprint = fingerprint
        return self._graph

    def find_entity(self, name: str) -> dict[str, Any] | None:
        """Return an entity by normalized name or alias."""

        graph = self.get_graph()
        key = self._canonical_key(graph, name)
        entity = graph.entities.get(key)
        return self._entity_payload(entity, graph) if entity else None

    def find_entity_case_insensitive(self, name: str) -> dict[str, Any] | None:
        """Return an entity using case-insensitive matching."""

        return self.find_entity(name)

    def related_entities(self, name: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return ranked co-occurring entities."""

        graph = self.get_graph()
        key = self._canonical_key(graph, name)
        entity = graph.entities.get(key)
        if entity is None:
            return []
        return [
            {
                "entity": graph.entities[related_key].name,
                "entity_type": graph.entities[related_key].entity_type,
                "count": count,
            }
            for related_key, count in entity.related.most_common(limit)
            if related_key in graph.entities
        ]

    def related_experiments(self, name: str) -> list[dict[str, Any]]:
        """Return experiments linked to an entity."""

        return self._objects_for_entity(name, {"experiment"})

    def related_documents(self, name: str) -> list[dict[str, Any]]:
        """Return notebook and literature documents linked to an entity."""

        return self._objects_for_entity(name, {"notebook_entry", "literature"})

    def related_assets(self, name: str) -> list[dict[str, Any]]:
        """Return assets linked to an entity."""

        return self._objects_for_entity(
            name,
            {"microscopy_asset", "graphpad_asset", "spreadsheet_asset", "asset", "statistical_analysis"},
        )

    def entity_statistics(self, name: str) -> dict[str, Any]:
        """Return relationship counts for an entity."""

        graph = self.get_graph()
        key = self._canonical_key(graph, name)
        entity = graph.entities.get(key)
        if entity is None:
            return {}
        counts = Counter(relationship.object_type for relationship in entity.relationships)
        return {
            "entity": entity.name,
            "entity_type": entity.entity_type,
            "relationship_counts": dict(sorted(counts.items())),
            "related_entity_count": len(entity.related),
            "total_references": len(entity.relationships),
        }

    def entity_detail(self, name: str) -> dict[str, Any] | None:
        """Return the API detail payload for one entity."""

        graph = self.get_graph()
        key = self._canonical_key(graph, name)
        entity = graph.entities.get(key)
        if entity is None:
            return None
        relationship_counts = Counter(relationship.object_type for relationship in entity.relationships)
        experiments = self._objects_for_entity(entity.name, {"experiment"})
        notebook_entries = self._objects_for_entity(entity.name, {"notebook_entry"})
        literature = self._objects_for_entity(entity.name, {"literature"})
        microscopy_assets = self._objects_for_entity(entity.name, {"microscopy_asset"})
        graphpad_assets = self._objects_for_entity(entity.name, {"graphpad_asset"})
        spreadsheet_assets = self._objects_for_entity(entity.name, {"spreadsheet_asset"})
        statistics = self._objects_for_entity(entity.name, {"statistical_analysis"})
        return {
            "entity": entity.name,
            "entity_type": entity.entity_type,
            "experiments": experiments,
            "notebook_entries": notebook_entries,
            "literature": literature,
            "microscopy_assets": microscopy_assets,
            "graphpad_assets": graphpad_assets,
            "spreadsheet_assets": spreadsheet_assets,
            "statistics": statistics,
            "related_entities": self.related_entities(entity.name, limit=20),
            "relationships": [relationship.as_dict() for relationship in entity.relationships[:200]],
            "relationship_counts": dict(sorted(relationship_counts.items())),
            "summary": _entity_summary(entity.name, entity.entity_type, relationship_counts, entity.related, graph),
        }

    def search(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        """Search graph entities with fast case-insensitive partial matching."""

        graph = self.get_graph()
        needle = _normalize_text(query)
        compact_needle = _alias_key(query)
        if not needle:
            return []
        results = []
        for entity in graph.entities.values():
            name = _normalize_text(entity.name)
            compact = _alias_key(entity.name)
            if needle == name or compact_needle == compact:
                score = 1000 + len(entity.relationships)
            elif name.startswith(needle) or compact.startswith(compact_needle):
                score = 500 + len(entity.relationships)
            elif needle in name or compact_needle in compact:
                score = 100 + len(entity.relationships)
            else:
                continue
            results.append(self._entity_payload(entity, graph) | {"score": score})
        results.sort(key=lambda item: (-int(item["score"]), str(item["entity"]).lower()))
        return results[:limit]

    def summary(self) -> dict[str, Any]:
        """Return graph-level statistics for the API."""

        graph = self.get_graph()
        type_counts = Counter(entity.entity_type for entity in graph.entities.values())
        top_entities = sorted(
            graph.entities.values(),
            key=lambda entity: (-len(entity.relationships), entity.name.lower()),
        )[:20]
        return {
            "entity_count": len(graph.entities),
            "relationship_count": len(graph.relationships),
            "experiment_count": len(graph.experiments),
            "document_count": len(graph.documents),
            "asset_count": len(graph.assets),
            "top_entities": [
                {
                    "entity": entity.name,
                    "entity_type": entity.entity_type,
                    "reference_count": len(entity.relationships),
                }
                for entity in top_entities
            ],
            "entity_types": dict(sorted(type_counts.items())),
            "cache": {
                "cached": self._graph is not None,
                "fingerprint": list(self._fingerprint or self._current_fingerprint()),
                "build_seconds": round(graph.build_seconds, 4),
            },
        }

    def entities_by_type(self, entity_type: str) -> list[dict[str, Any]]:
        """Return every entity for a normalized type."""

        graph = self.get_graph()
        normalized_type = _canonical_entity_type(entity_type)
        entities = [
            self._entity_payload(entity, graph)
            for entity in graph.entities.values()
            if entity.entity_type == normalized_type
        ]
        entities.sort(key=lambda item: (-int(item["reference_count"]), str(item["entity"]).lower()))
        return entities

    def experiment_neighborhood(self, experiment_id: str) -> dict[str, Any] | None:
        """Return every object connected to one experiment."""

        graph = self.get_graph()
        experiment = graph.experiments.get(experiment_id)
        if experiment is None:
            experiment = next(
                (
                    item
                    for item in graph.experiments.values()
                    if str(item.get("experiment_id") or "").lower() == experiment_id.lower()
                ),
                None,
            )
        if experiment is None:
            return None

        experiment_key = f"experiment:{experiment['id']}"
        entity_keys = graph.object_entities.get(experiment_key, set())
        source_document_id = str(experiment.get("source_document_id") or "")
        linked_assets = [
            asset
            for asset in graph.assets.values()
            if _same_reference(str(asset.get("experiment_id") or ""), str(experiment.get("id") or ""))
            or _same_reference(str(asset.get("experiment_id") or ""), str(experiment.get("experiment_id") or ""))
        ]
        statistics_assets = [asset for asset in linked_assets if _asset_has_statistics(asset)]
        source_document = graph.documents.get(source_document_id)
        related_literature = self._literature_for_entities(graph, entity_keys)
        entities = [self._entity_payload(graph.entities[key], graph) for key in entity_keys if key in graph.entities]
        entities.sort(key=lambda item: (str(item["entity_type"]), str(item["entity"]).lower()))
        return {
            "experiment": _experiment_summary(experiment),
            "notebook": _document_summary(source_document) if source_document else None,
            "images": [_asset_summary(asset) for asset in linked_assets if _asset_object_type(asset) == "microscopy_asset"],
            "graphpad": [_asset_summary(asset) for asset in linked_assets if _asset_object_type(asset) == "graphpad_asset"],
            "statistics": [_asset_summary(asset) for asset in statistics_assets],
            "spreadsheets": [_asset_summary(asset) for asset in linked_assets if _asset_object_type(asset) == "spreadsheet_asset"],
            "literature": [_document_summary(document) for document in related_literature],
            "entities": entities,
            "compounds": [item["entity"] for item in entities if item["entity_type"] == "compound"],
            "markers": [item["entity"] for item in entities if item["entity_type"] == "marker"],
            "genes": [item["entity"] for item in entities if item["entity_type"] == "gene"],
            "proteins": [item["entity"] for item in entities if item["entity_type"] == "protein"],
        }

    def _add_object_entities(
        self,
        graph: KnowledgeGraph,
        object_type: str,
        object_id: str,
        payload: dict[str, Any],
        entities: dict[str, list[str]],
        where: str,
    ) -> None:
        title = str(payload.get("title") or payload.get("filename") or payload.get("experiment_id") or object_id)
        source = str(payload.get("provider") or payload.get("source_provider") or object_type)
        object_key = f"{object_type}:{object_id}"
        for entity_type, values in entities.items():
            normalized_type = _canonical_entity_type(entity_type)
            for value in values:
                cleaned = _clean_entity_value(value)
                if cleaned is None:
                    continue
                key = self._canonical_key(graph, cleaned)
                entity = graph.entities.get(key)
                if entity is None:
                    entity = KnowledgeGraphEntity(
                        canonical_key=key,
                        name=cleaned,
                        entity_type=normalized_type,
                    )
                    graph.entities[key] = entity
                elif _type_priority(normalized_type) > _type_priority(entity.entity_type):
                    entity.entity_type = normalized_type
                entity.add_variant(cleaned)
                relationship = KnowledgeGraphRelationship(
                    object_type=object_type,
                    object_id=object_id,
                    source=source,
                    relationship_type=f"references_{normalized_type}",
                    where=where,
                    title=title,
                )
                entity.relationships.append(relationship)
                graph.relationships.append(relationship)
                graph.object_entities[object_key].add(key)

    def _calculate_co_occurrence(self, graph: KnowledgeGraph) -> None:
        for entity_keys in graph.object_entities.values():
            keys = sorted(entity_keys)
            for key in keys:
                for related_key in keys:
                    if related_key != key:
                        graph.entities[key].related[related_key] += 1

    def _objects_for_entity(self, name: str, object_types: set[str]) -> list[dict[str, Any]]:
        graph = self.get_graph()
        key = self._canonical_key(graph, name)
        entity = graph.entities.get(key)
        if entity is None:
            return []
        records = []
        seen: set[tuple[str, str]] = set()
        for relationship in entity.relationships:
            if relationship.object_type not in object_types:
                continue
            dedupe_key = (relationship.object_type, relationship.object_id)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            records.append(self._relationship_object_payload(graph, relationship))
        return records

    def _relationship_object_payload(
        self,
        graph: KnowledgeGraph,
        relationship: KnowledgeGraphRelationship,
    ) -> dict[str, Any]:
        if relationship.object_type == "experiment":
            return _experiment_summary(graph.experiments.get(relationship.object_id, {}))
        if relationship.object_type in {"notebook_entry", "literature"}:
            document = graph.documents.get(relationship.object_id) or graph.pending_entries.get(relationship.object_id, {})
            return _document_summary(document)
        asset = graph.assets.get(relationship.object_id, {})
        return _asset_summary(asset)

    def _entity_payload(self, entity: KnowledgeGraphEntity | None, graph: KnowledgeGraph) -> dict[str, Any]:
        if entity is None:
            return {}
        counts = Counter(relationship.object_type for relationship in entity.relationships)
        return {
            "entity": entity.name,
            "entity_type": entity.entity_type,
            "reference_count": len(entity.relationships),
            "relationship_counts": dict(sorted(counts.items())),
            "aliases": sorted(value for value in entity.variants if value != entity.name),
            "related_entities": self.related_entities(entity.name, limit=12),
        }

    def _canonical_key(self, graph: KnowledgeGraph, value: str) -> str:
        key = _alias_key(value)
        return graph.aliases.get(key, key)

    def _current_fingerprint(self) -> tuple[int, int]:
        path = Path(self.store.path)
        try:
            stat = path.stat()
        except OSError:
            return (0, 0)
        return (stat.st_mtime_ns, stat.st_size)

    def _register_aliases(
        self,
        graph: KnowledgeGraph,
        documents: list[dict[str, Any]],
        assets: list[dict[str, Any]],
        pending_entries: list[dict[str, Any] | None],
    ) -> None:
        for payload in [*documents, *assets, *(entry for entry in pending_entries if entry)]:
            metadata = _metadata(payload)
            for canonical, alias in _aliases_from_metadata(metadata):
                canonical_key = _alias_key(canonical)
                graph.aliases[_alias_key(alias)] = canonical_key
                graph.aliases[canonical_key] = canonical_key

    def _literature_for_entities(self, graph: KnowledgeGraph, entity_keys: set[str]) -> list[dict[str, Any]]:
        literature = []
        for document in graph.documents.values():
            if document.get("provider") != "literature":
                continue
            keys = graph.object_entities.get(f"literature:{document['id']}", set()) or graph.object_entities.get(
                f"notebook_entry:{document['id']}",
                set(),
            )
            if entity_keys.intersection(keys):
                literature.append(document)
        return literature[:20]


def _entities_from_experiment(experiment: dict[str, Any]) -> dict[str, list[str]]:
    entities: dict[str, list[str]] = defaultdict(list)
    for field_name in [
        "compounds",
        "treatments",
        "markers",
        "antibodies",
        "sequencing",
    ]:
        entities[_canonical_entity_type(field_name)].extend(_as_list(experiment.get(field_name)))
    if experiment.get("cell_line"):
        entities["cell_line"].append(str(experiment["cell_line"]))
    if experiment.get("organoid_batch"):
        entities["organoid_batch"].append(str(experiment["organoid_batch"]))
    entities["sample"].extend(_generic_scientific_terms(str(experiment.get("experiment_id") or "")))
    return _dedupe_entities(entities)


def _entities_from_document(document: dict[str, Any]) -> dict[str, list[str]]:
    metadata = _metadata(document)
    entities = _entities_from_metadata(metadata)
    if document.get("provider") != "literature":
        entities.setdefault("unknown_scientific_term", []).extend(_generic_scientific_terms(str(document.get("title") or "")))
    return _dedupe_entities(entities)


def _entities_from_asset(asset: dict[str, Any]) -> dict[str, list[str]]:
    metadata = _metadata(asset)
    entities = _entities_from_metadata(metadata)
    experiment_id = asset.get("experiment_id") or metadata.get("experiment_id")
    if experiment_id:
        entities.setdefault("sample", []).extend(_generic_scientific_terms(str(experiment_id)))
    if asset.get("filename"):
        entities.setdefault("unknown_scientific_term", []).extend(_generic_scientific_terms(str(asset["filename"])))
    return _dedupe_entities(entities)


def _entities_from_statistics(asset: dict[str, Any], settings: Settings | None = None) -> dict[str, list[str]]:
    metadata = _metadata(asset)
    statistics = metadata.get("statistics") if isinstance(metadata.get("statistics"), dict) else {}
    entities: dict[str, list[str]] = defaultdict(list)
    for key in ["variables", "markers", "genes", "proteins", "group_names", "comparison_labels", "statistical_tests"]:
        entity_type = "treatment" if key in {"group_names", "comparison_labels"} else _canonical_entity_type(key)
        entities[entity_type].extend(_as_list(statistics.get(key)))
    interpreted = interpret_statistics_asset(str(asset.get("asset_id") or ""), settings=settings)
    if interpreted:
        for result in interpreted.get("results", []):
            entities["unknown_scientific_term"].extend(_as_list(result.get("variable")))
            entities["treatment"].extend(_as_list(result.get("groups_compared")))
    return _dedupe_entities(entities)


def _entities_from_pending_entry(entry: dict[str, Any]) -> dict[str, list[str]]:
    structured = entry.get("structured") if isinstance(entry.get("structured"), dict) else {}
    entities = _entities_from_metadata(structured)
    entities.setdefault("sample", []).extend(_generic_scientific_terms(str(entry.get("experiment_id") or "")))
    return _dedupe_entities(entities)


def _entities_from_metadata(metadata: dict[str, Any]) -> dict[str, list[str]]:
    entities: dict[str, list[str]] = defaultdict(list)
    nested = metadata.get("entities")
    if isinstance(nested, dict):
        for entity_type, values in nested.items():
            entities[_canonical_entity_type(str(entity_type))].extend(_as_list(values))

    for key, value in metadata.items():
        normalized_key = _normalize_key(str(key))
        if normalized_key in EXCLUDED_METADATA_KEYS or normalized_key == "entities":
            continue
        if normalized_key in ENTITY_FIELD_ALIASES:
            entities[ENTITY_FIELD_ALIASES[normalized_key]].extend(_as_list(value))
        elif normalized_key.startswith("entity_"):
            entities[_canonical_entity_type(normalized_key.removeprefix("entity_"))].extend(_as_list(value))
        elif normalized_key.endswith("_entities"):
            entities[_canonical_entity_type(normalized_key.removesuffix("_entities"))].extend(_as_list(value))
    return _dedupe_entities(entities)


def _aliases_from_metadata(metadata: dict[str, Any]) -> list[tuple[str, str]]:
    raw_aliases = metadata.get("aliases") or metadata.get("entity_aliases")
    pairs: list[tuple[str, str]] = []
    if isinstance(raw_aliases, dict):
        for canonical, aliases in raw_aliases.items():
            for alias in _as_list(aliases):
                pairs.append((str(canonical), str(alias)))
    elif isinstance(raw_aliases, list):
        for item in raw_aliases:
            if isinstance(item, dict):
                canonical = item.get("canonical") or item.get("name")
                for alias in _as_list(item.get("aliases")):
                    if canonical:
                        pairs.append((str(canonical), str(alias)))
    return pairs


def _asset_object_type(asset: dict[str, Any]) -> str:
    provider = str(asset.get("provider") or "").lower()
    asset_type = str(asset.get("asset_type") or "").lower()
    if provider == "microscopy" or asset_type in {"image", "microscopy"}:
        return "microscopy_asset"
    if provider == "graphpad" or asset_type == "graphpad":
        return "graphpad_asset"
    if provider == "spreadsheet" or asset_type == "spreadsheet":
        return "spreadsheet_asset"
    if provider == "literature" or asset_type in {"literature", "pdf"}:
        return "literature"
    return "asset"


def _asset_has_statistics(asset: dict[str, Any]) -> bool:
    metadata = _metadata(asset)
    return isinstance(metadata.get("statistics"), dict)


def _metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [str(item) for item in value.values() if str(item).strip()]
    return [item.strip() for item in re.split(r"[,;]", str(value)) if item.strip()]


def _dedupe_entities(entities: dict[str, list[str]]) -> dict[str, list[str]]:
    cleaned: dict[str, list[str]] = {}
    for entity_type, values in entities.items():
        seen: set[str] = set()
        output = []
        for value in values:
            clean = _clean_entity_value(value)
            if clean is None:
                continue
            key = _alias_key(clean)
            if key not in seen:
                seen.add(key)
                output.append(clean)
        if output:
            cleaned[_canonical_entity_type(entity_type)] = output
    return cleaned


def _clean_entity_value(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").strip(" \t\r\n,;:."))
    if not text or text.lower() in EXCLUDED_ENTITY_VALUES:
        return None
    if len(text) > 120:
        return None
    return text


def _canonical_entity_type(value: str) -> str:
    key = _normalize_key(value)
    return ENTITY_FIELD_ALIASES.get(key, key or "unknown_scientific_term")


def _type_priority(entity_type: str) -> int:
    priorities = {
        "compound": 100,
        "marker": 95,
        "gene": 90,
        "protein": 90,
        "antibody": 85,
        "cell_line": 80,
        "organoid_batch": 75,
        "sample_batch": 72,
        "sample": 70,
        "treatment": 65,
        "cell_population": 60,
        "sequencing_cluster": 55,
        "patient": 50,
        "animal": 50,
        "unknown_scientific_term": 0,
    }
    return priorities.get(entity_type, 20)


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def _alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _best_display_name(variants: Counter[str]) -> str:
    return sorted(variants, key=lambda value: (-variants[value], len(value), value.lower()))[0]


def _generic_scientific_terms(text: str) -> list[str]:
    terms = re.findall(r"\b[A-Za-z]{1,8}[_-]?(?:Expt|EXP)[_-]?\d+\b|\b[A-Z][A-Z0-9]{2,12}\b", text)
    excluded = {"PDF", "CSV", "TSV", "XLSX", "DNA", "RNA", "API", "HTTP", "HTTPS"}
    return [term for term in terms if term.upper() not in excluded]


def _same_reference(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return _alias_key(left) == _alias_key(right)


def _document_summary(document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not document:
        return None
    return {
        "id": document.get("id"),
        "title": document.get("title"),
        "provider": document.get("provider"),
        "source_path": document.get("source_path"),
        "source_url": document.get("source_url"),
        "updated_at": document.get("updated_at"),
    }


def _experiment_summary(experiment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": experiment.get("id"),
        "experiment_id": experiment.get("experiment_id"),
        "title": experiment.get("title"),
        "date": experiment.get("date"),
        "source_provider": experiment.get("source_provider"),
        "cell_line": experiment.get("cell_line"),
        "organoid_batch": experiment.get("organoid_batch"),
        "compounds": experiment.get("compounds") or [],
        "markers": experiment.get("markers") or [],
    }


def _asset_summary(asset: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(asset)
    return {
        "asset_id": asset.get("asset_id"),
        "asset_type": asset.get("asset_type"),
        "title": asset.get("title"),
        "filename": asset.get("filename"),
        "provider": asset.get("provider"),
        "path": asset.get("path"),
        "experiment_id": asset.get("experiment_id"),
        "metadata": metadata,
    }


def _entity_summary(
    name: str,
    entity_type: str,
    relationship_counts: Counter[str],
    related: Counter[str],
    graph: KnowledgeGraph,
) -> str:
    pieces = [
        f"{name} is indexed as {entity_type}.",
        f"Referenced by {sum(relationship_counts.values())} local object(s).",
    ]
    for label, object_type in [
        ("experiments", "experiment"),
        ("notebook entries", "notebook_entry"),
        ("literature records", "literature"),
        ("microscopy assets", "microscopy_asset"),
        ("GraphPad assets", "graphpad_asset"),
        ("spreadsheets", "spreadsheet_asset"),
        ("statistical analyses", "statistical_analysis"),
    ]:
        count = relationship_counts.get(object_type, 0)
        if count:
            pieces.append(f"{count} {label}.")
    if related:
        names = [
            graph.entities[key].name
            for key, _ in related.most_common(6)
            if key in graph.entities
        ]
        if names:
            pieces.append(f"Most related entities: {', '.join(names)}.")
    return " ".join(pieces)

"""Universal provider-agnostic search for ResearchOS."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.config import Settings, get_settings
from app.global_knowledge_graph import KnowledgeGraphService
from app.storage import SQLiteStore


GROUPS = (
    "experiments",
    "notebook_entries",
    "entities",
    "images",
    "graphpad",
    "spreadsheets",
    "statistics",
    "literature",
    "timeline",
    "commands",
)


@dataclass
class SearchItem:
    """Internal flat search index item."""

    group: str
    id: str
    title: str
    subtitle: str
    text: str
    href: str
    provider: str
    metadata: dict[str, Any]
    updated_at: str | None = None


class UniversalSearchService:
    """Build and query a cached global ResearchOS search index."""

    def __init__(
        self,
        settings: Settings | None = None,
        store: SQLiteStore | None = None,
        knowledge_graph: KnowledgeGraphService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or SQLiteStore(settings=self.settings)
        self.knowledge_graph = knowledge_graph or KnowledgeGraphService(settings=self.settings, store=self.store)
        self._items: list[SearchItem] | None = None
        self._fingerprint: tuple[int, int, int, int] | None = None

    def refresh(self) -> None:
        """Force the next search to rebuild its local index."""

        self._items = None
        self._fingerprint = None
        self.knowledge_graph.refresh()

    def search(self, query: str, limit_per_group: int = 8) -> dict[str, Any]:
        """Search all indexed ResearchOS objects and return grouped results."""

        parsed = _parse_query(query)
        grouped: dict[str, list[dict[str, Any]]] = {group: [] for group in GROUPS}
        if not parsed["raw"]:
            return {
                "query": query,
                "total_results": 0,
                "grouped_results": grouped,
                "suggested_queries": _default_suggestions(),
                "related_entities": [],
            }

        scored: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in self._index():
            score = _score_item(item, parsed)
            if score <= 0:
                continue
            scored[item.group].append(_result_payload(item, score))

        for group in GROUPS:
            results = sorted(
                scored.get(group, []),
                key=lambda result: (-float(result["score"]), str(result["title"]).lower()),
            )[:limit_per_group]
            grouped[group] = results

        related_entities = self._related_entities(parsed)
        suggestions = _suggested_queries(parsed, grouped, related_entities)
        return {
            "query": query,
            "total_results": sum(len(results) for results in grouped.values()),
            "grouped_results": grouped,
            "suggested_queries": suggestions,
            "related_entities": related_entities,
        }

    def _index(self) -> list[SearchItem]:
        fingerprint = self._current_fingerprint()
        if self._items is not None and self._fingerprint == fingerprint:
            return self._items

        items: list[SearchItem] = []
        documents = [document.__dict__ for document in self.store.get_all_research_documents()]
        experiments = self.store.list_experiments()
        assets = self.store.list_assets(query=None)

        for experiment in experiments:
            items.append(_experiment_item(experiment))
            items.extend(_timeline_items_for_experiment(experiment, assets))

        for document in documents:
            group = "literature" if document.get("provider") == "literature" else "notebook_entries"
            items.append(_document_item(document, group))

        for entity in self.knowledge_graph.search("", limit=0):
            # KnowledgeGraphService returns empty for blank query; entity items
            # are built below from the cached graph for full index coverage.
            del entity
        graph = self.knowledge_graph.get_graph()
        for entity in graph.entities.values():
            items.append(
                SearchItem(
                    group="entities",
                    id=entity.name,
                    title=entity.name,
                    subtitle=f"{entity.entity_type} · {len(entity.relationships)} references",
                    text=" ".join([entity.name, entity.entity_type, *entity.variants.keys()]),
                    href=f"#/graph/{_graph_route_type(entity.entity_type)}/{entity.name}",
                    provider="knowledgegraph",
                    metadata={
                        "entity": entity.name,
                        "entity_type": entity.entity_type,
                        "reference_count": len(entity.relationships),
                    },
                )
            )

        experiment_context = _experiment_context_by_reference(experiments)
        for asset in assets:
            items.append(_asset_item(asset, experiment_context))

        items.extend(_command_items())
        self._items = items
        self._fingerprint = fingerprint
        return items

    def _current_fingerprint(self) -> tuple[int, int, int, int]:
        documents = self.store.list_documents()
        experiments = self.store.list_experiments()
        assets = self.store.list_assets(query=None)
        entries = self.store.list_pending_entries()
        return (len(documents), len(experiments), len(assets), len(entries))

    def _related_entities(self, parsed: dict[str, Any]) -> list[dict[str, Any]]:
        related: dict[str, dict[str, Any]] = {}
        for token in parsed["terms"] + parsed["phrases"]:
            for entity in self.knowledge_graph.search(token, limit=5):
                related[str(entity["entity"]).lower()] = entity
                for linked in self.knowledge_graph.related_entities(str(entity["entity"]), limit=5):
                    related[str(linked["entity"]).lower()] = linked
        return sorted(
            related.values(),
            key=lambda item: (-int(item.get("reference_count", item.get("score", 0)) or 0), str(item.get("entity", "")).lower()),
        )[:12]


def _parse_query(query: str) -> dict[str, Any]:
    raw = query.strip()
    phrases = [match.strip() for match in re.findall(r'"([^"]+)"', raw) if match.strip()]
    without_phrases = re.sub(r'"[^"]+"', " ", raw)
    terms = [term.lower() for term in re.findall(r"[\w.+-]+", without_phrases) if term.strip()]
    return {
        "raw": raw,
        "terms": terms,
        "phrases": [phrase.lower() for phrase in phrases],
        "all": [*terms, *[phrase.lower() for phrase in phrases]],
    }


def _score_item(item: SearchItem, parsed: dict[str, Any]) -> float:
    haystack = _normalize(" ".join([item.title, item.subtitle, item.text, item.provider]))
    title = _normalize(item.title)
    score = 0.0
    for phrase in parsed["phrases"]:
        normalized = _normalize(phrase)
        if normalized in title:
            score += 120
        elif normalized in haystack:
            score += 80
        elif _fuzzy_match(normalized, title):
            score += 35
    for term in parsed["terms"]:
        normalized = _normalize(term)
        if normalized == title:
            score += 160
        elif title.startswith(normalized):
            score += 110
        elif normalized in title:
            score += 80
        elif normalized in haystack:
            score += 45
        elif _fuzzy_match(normalized, title):
            score += 22
    if score <= 0:
        return 0
    score += {
        "entities": 18,
        "experiments": 16,
        "statistics": 12,
        "notebook_entries": 10,
        "literature": 9,
        "timeline": 8,
        "images": 7,
        "graphpad": 7,
        "spreadsheets": 7,
        "commands": 4,
    }.get(item.group, 0)
    score += float(item.metadata.get("confidence", 0) or 0)
    return round(score, 3)


def _experiment_item(experiment: dict[str, Any]) -> SearchItem:
    terms = [
        experiment.get("id"),
        experiment.get("experiment_id"),
        experiment.get("title"),
        experiment.get("date"),
        experiment.get("researcher"),
        experiment.get("cell_line"),
        experiment.get("organoid_batch"),
        experiment.get("notes"),
        experiment.get("conclusions"),
        *_list(experiment.get("compounds")),
        *_list(experiment.get("treatments")),
        *_list(experiment.get("markers")),
        *_list(experiment.get("time_points")),
    ]
    experiment_id = str(experiment.get("id") or "")
    human_id = str(experiment.get("experiment_id") or experiment_id)
    return SearchItem(
        group="experiments",
        id=experiment_id,
        title=str(experiment.get("title") or human_id),
        subtitle=f"{human_id} · {experiment.get('source_provider') or 'experiment'}",
        text=" ".join(str(term) for term in terms if term),
        href=f"#/experiments/{experiment_id}/workspace",
        provider=str(experiment.get("source_provider") or "experiment"),
        metadata={"experiment_id": human_id, "confidence": 8},
        updated_at=str(experiment.get("extracted_at") or ""),
    )


def _document_item(document: dict[str, Any], group: str) -> SearchItem:
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    return SearchItem(
        group=group,
        id=str(document.get("id") or ""),
        title=str(document.get("title") or document.get("id") or "Untitled document"),
        subtitle=str(document.get("provider") or group),
        text=" ".join(
            str(value)
            for value in [
                document.get("title"),
                document.get("content"),
                document.get("source_path"),
                document.get("source_url"),
                metadata,
            ]
            if value
        ),
        href="#/literature" if group == "literature" else "#/documents",
        provider=str(document.get("provider") or group),
        metadata={"source_id": document.get("source_id"), "confidence": 4},
        updated_at=str(document.get("updated_at") or document.get("ingested_at") or ""),
    )


def _asset_item(asset: dict[str, Any], experiment_context: dict[str, str] | None = None) -> SearchItem:
    group = _asset_group(asset)
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    linked_context = ""
    if experiment_context:
        linked_context = experiment_context.get(str(asset.get("experiment_id") or ""), "")
    text = " ".join(
        str(value)
        for value in [
            asset.get("asset_id"),
            asset.get("asset_type"),
            asset.get("experiment_id"),
            asset.get("title"),
            asset.get("filename"),
            asset.get("provider"),
            asset.get("path"),
            metadata,
            linked_context,
        ]
        if value
    )
    return SearchItem(
        group=group,
        id=str(asset.get("asset_id") or ""),
        title=str(asset.get("title") or asset.get("filename") or asset.get("asset_id")),
        subtitle=f"{asset.get('provider') or 'asset'} · {asset.get('experiment_id') or 'unlinked'}",
        text=text,
        href=f"#/assets/{asset.get('asset_id')}",
        provider=str(asset.get("provider") or "asset"),
        metadata={"asset_type": asset.get("asset_type"), "experiment_id": asset.get("experiment_id"), "confidence": 5},
        updated_at=str(asset.get("updated_at") or asset.get("created_at") or ""),
    )


def _timeline_items_for_experiment(experiment: dict[str, Any], assets: list[dict[str, Any]]) -> list[SearchItem]:
    references = {str(experiment.get("id") or ""), str(experiment.get("experiment_id") or "")}
    output = [
        SearchItem(
            group="timeline",
            id=f"timeline:{experiment.get('id')}:extracted",
            title=f"Extracted experiment: {experiment.get('title') or experiment.get('experiment_id') or experiment.get('id')}",
            subtitle=str(experiment.get("date") or experiment.get("extracted_at") or "timeline"),
            text=" ".join(str(value) for value in [experiment.get("title"), experiment.get("experiment_id"), experiment.get("date"), experiment.get("notes"), experiment.get("conclusions")] if value),
            href=f"#/experiments/{experiment.get('id')}/workspace",
            provider=str(experiment.get("source_provider") or "experiment"),
            metadata={"event_type": "extracted_experiment", "confidence": 3},
            updated_at=str(experiment.get("extracted_at") or ""),
        )
    ]
    for asset in assets:
        if str(asset.get("experiment_id") or "") not in references:
            continue
        output.append(
            SearchItem(
                group="timeline",
                id=f"timeline:{asset.get('asset_id')}",
                title=f"{asset.get('title') or asset.get('filename') or asset.get('asset_id')}",
                subtitle=f"{asset.get('provider') or 'asset'} · {asset.get('updated_at') or asset.get('created_at') or ''}",
                text=" ".join(str(value) for value in [asset.get("title"), asset.get("filename"), asset.get("path"), asset.get("metadata")] if value),
                href=f"#/experiments/{experiment.get('id')}/workspace",
                provider=str(asset.get("provider") or "asset"),
                metadata={"event_type": "asset", "asset_id": asset.get("asset_id"), "confidence": 3},
                updated_at=str(asset.get("updated_at") or asset.get("created_at") or ""),
            )
        )
    return output


def _asset_group(asset: dict[str, Any]) -> str:
    provider = str(asset.get("provider") or "").lower()
    asset_type = str(asset.get("asset_type") or "").lower()
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    if metadata.get("statistics"):
        return "statistics"
    if provider == "graphpad" or asset_type == "graphpad":
        return "graphpad"
    if provider == "microscopy" or asset_type in {"image", "microscopy"}:
        return "images"
    if asset_type in {"spreadsheet", "csv"}:
        return "spreadsheets"
    if asset_type in {"literature", "pdf"}:
        return "literature"
    return "notebook_entries" if asset_type == "notebook" else "spreadsheets"


def _command_items() -> list[SearchItem]:
    commands = [
        ("Load demo notes", "Run demo reset and reingest sample notes", "#/dashboard"),
        ("New Experiment", "Draft a structured lab notebook entry", "#/new-experiment"),
        ("Ask ResearchOS", "Open AI Chat and Knowledge Graph assistant", "#/chat"),
        ("Graph Explorer", "Explore connected scientific entities", "#/graph"),
        ("Settings", "Provider, deployment, and OneNote readiness", "#/settings"),
    ]
    return [
        SearchItem("commands", title.lower().replace(" ", "-"), title, subtitle, title + " " + subtitle, href, "researchos", {"confidence": 2})
        for title, subtitle, href in commands
    ]


def _graph_route_type(entity_type: str) -> str:
    return {
        "compound": "compounds",
        "marker": "markers",
        "gene": "genes",
        "protein": "proteins",
        "paper": "papers",
        "protocol": "protocols",
        "experiment": "experiments",
        "cell_line": "cell-lines",
        "organoid_batch": "organoid-batches",
    }.get(entity_type, f"{entity_type}s")


def _experiment_context_by_reference(experiments: list[dict[str, Any]]) -> dict[str, str]:
    output: dict[str, str] = {}
    for experiment in experiments:
        context = " ".join(
            str(value)
            for value in [
                experiment.get("id"),
                experiment.get("experiment_id"),
                experiment.get("title"),
                experiment.get("notes"),
                experiment.get("conclusions"),
                *_list(experiment.get("compounds")),
                *_list(experiment.get("markers")),
                *_list(experiment.get("time_points")),
            ]
            if value
        )
        for reference in [experiment.get("id"), experiment.get("experiment_id")]:
            if reference:
                output[str(reference)] = context
    return output


def _result_payload(item: SearchItem, score: float) -> dict[str, Any]:
    return {
        "id": item.id,
        "type": item.group,
        "title": item.title,
        "subtitle": item.subtitle,
        "provider": item.provider,
        "href": item.href,
        "score": score,
        "updated_at": item.updated_at,
        "metadata": item.metadata,
    }


def _suggested_queries(parsed: dict[str, Any], grouped: dict[str, list[dict[str, Any]]], related_entities: list[dict[str, Any]]) -> list[str]:
    suggestions = []
    for entity in related_entities[:4]:
        name = entity.get("entity")
        if name:
            suggestions.append(f"What do we know about {name}?")
    if grouped.get("experiments"):
        suggestions.append(f"Show experiment workspace for {grouped['experiments'][0]['title']}")
    if parsed["raw"]:
        suggestions.append(f"Compare {parsed['raw']} with literature")
    return _unique(suggestions)[:6] or _default_suggestions()


def _default_suggestions() -> list[str]:
    return [
        "Which experiments used SAG?",
        "Show everything involving SIX6",
        "Compare our SAG experiments with the literature",
    ]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _fuzzy_match(needle: str, haystack: str) -> bool:
    if len(needle) < 3:
        return False
    words = re.findall(r"[\w.+-]+", haystack)
    return any(SequenceMatcher(None, needle, word).ratio() >= 0.78 for word in words)


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []


def _unique(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output

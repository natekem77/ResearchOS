"""Unified experiment workspace assembly for ResearchOS."""

from __future__ import annotations

from typing import Any

from app.ai_providers import AIProviderError, get_ai_provider
from app.config import Settings, get_settings
from app.global_knowledge_graph import KnowledgeGraphService
from app.graphpad_provider import compact_graphpad_statistics_summary
from app.spreadsheet_provider import compact_spreadsheet_summary
from app.statistics_engine import interpret_statistics_asset
from app.storage import SQLiteStore


def build_experiment_workspace(
    experiment_id: str,
    timeline: dict[str, Any],
    settings: Settings | None = None,
    use_ai: bool = True,
    knowledge_graph: KnowledgeGraphService | None = None,
) -> dict[str, Any] | None:
    """Build the central workspace for one experiment from existing providers."""

    resolved_settings = settings or get_settings()
    store = SQLiteStore(settings=resolved_settings)
    service = knowledge_graph or KnowledgeGraphService(settings=resolved_settings, store=store)
    neighborhood = service.experiment_neighborhood(experiment_id)
    if neighborhood is None:
        experiment = store.find_experiment_by_reference(experiment_id)
        if experiment is not None:
            neighborhood = service.experiment_neighborhood(str(experiment["id"]))
        else:
            linked_assets = store.list_assets(experiment_id=experiment_id)
            if linked_assets:
                neighborhood = _asset_only_neighborhood(experiment_id, linked_assets)
    if neighborhood is None:
        return None

    experiment = neighborhood.get("experiment") or {}
    notebook_entries = [neighborhood["notebook"]] if neighborhood.get("notebook") else []
    microscopy = neighborhood.get("images") or []
    graphpad = neighborhood.get("graphpad") or []
    spreadsheets = [_spreadsheet_workspace_summary(asset, resolved_settings) for asset in neighborhood.get("spreadsheets") or []]
    statistics_assets = _dedupe_assets([*(neighborhood.get("statistics") or []), *graphpad])
    statistics = [_statistics_workspace_summary(asset, resolved_settings) for asset in statistics_assets]
    literature = neighborhood.get("literature") or []
    entities = neighborhood.get("entities") or []
    related_entities = _related_entities(entities)
    related_experiments = _related_experiments(service, related_entities, str(experiment.get("id") or experiment_id))
    provenance = _provenance(experiment, notebook_entries, timeline, microscopy, graphpad, spreadsheets, statistics, literature, entities)
    conclusions = _workspace_conclusions(experiment, statistics, literature)
    limitations = _workspace_limitations(neighborhood, statistics, literature)
    ai_summary = _workspace_summary(experiment, neighborhood, statistics, literature, limitations, resolved_settings, use_ai)

    compounds = _entity_names(entities, "compound", experiment.get("compounds") or [])
    markers = _entity_names(entities, "marker", experiment.get("markers") or [])
    genes = _entity_names(entities, "gene", [])
    proteins = _entity_names(entities, "protein", [])
    organoid_batches = _entity_names(entities, "organoid_batch", [experiment.get("organoid_batch")] if experiment.get("organoid_batch") else [])

    return {
        "experiment": experiment,
        "notebook_entries": notebook_entries,
        "timeline": timeline,
        "microscopy": microscopy,
        "graphpad": graphpad,
        "spreadsheets": spreadsheets,
        "statistics": statistics,
        "literature": literature,
        "compounds": compounds,
        "markers": markers,
        "genes": genes,
        "proteins": proteins,
        "organoid_batches": organoid_batches,
        "related_experiments": related_experiments,
        "related_entities": related_entities,
        "conclusions": conclusions,
        "limitations": limitations,
        "provenance": provenance,
        "sections": {
            "overview": _overview_section(experiment, compounds, markers, organoid_batches),
            "timeline": timeline.get("events") or [],
            "experimental_setup": _experimental_setup(experiment),
            "treatments": experiment.get("treatments") or [],
            "readouts": {
                "markers": markers,
                "antibodies": experiment.get("antibodies") or [],
                "imaging_methods": experiment.get("imaging_methods") or [],
                "sequencing": experiment.get("sequencing") or [],
            },
            "microscopy": microscopy,
            "graphpad_analyses": graphpad,
            "spreadsheets": spreadsheets,
            "statistics": statistics,
            "literature": literature,
            "connected_experiments": related_experiments,
            "related_entities": related_entities,
            "files": _workspace_files(microscopy, graphpad, spreadsheets),
            "ai_summary": ai_summary,
            "limitations": limitations,
            "provenance": provenance,
        },
        "ai_summary": ai_summary,
    }


def _asset_only_neighborhood(experiment_id: str, linked_assets: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a workspace neighborhood for human IDs that only have assets."""

    return {
        "experiment": {
            "id": experiment_id,
            "experiment_id": experiment_id,
            "title": f"Workspace for {experiment_id}",
            "source_provider": "asset_graph",
        },
        "notebook": None,
        "images": [asset for asset in linked_assets if _workspace_asset_kind(asset) == "image"],
        "graphpad": [asset for asset in linked_assets if _workspace_asset_kind(asset) == "graphpad"],
        "statistics": [asset for asset in linked_assets if _workspace_asset_has_statistics(asset)],
        "spreadsheets": [asset for asset in linked_assets if _workspace_asset_kind(asset) == "spreadsheet"],
        "literature": [],
        "entities": _asset_only_entities(linked_assets),
    }


def _workspace_asset_kind(asset: dict[str, Any]) -> str:
    """Classify assets for workspace sections without provider-specific calls."""

    provider = str(asset.get("provider") or "").lower()
    asset_type = str(asset.get("asset_type") or "").lower()
    if provider == "microscopy" or asset_type in {"image", "microscopy"}:
        return "image"
    if provider == "graphpad" or asset_type == "graphpad":
        return "graphpad"
    if asset_type in {"spreadsheet", "csv"}:
        return "spreadsheet"
    return "asset"


def _workspace_asset_has_statistics(asset: dict[str, Any]) -> bool:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    return bool(isinstance(metadata, dict) and metadata.get("statistics"))


def _asset_only_entities(linked_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Surface provider-emitted entities for asset-only human-ID workspaces."""

    values: dict[tuple[str, str], int] = {}
    for asset in linked_assets:
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        if not isinstance(metadata, dict):
            continue
        entities = metadata.get("entities") if isinstance(metadata.get("entities"), dict) else {}
        for entity_type, raw_values in entities.items():
            if isinstance(raw_values, str):
                iterable = [raw_values]
            elif isinstance(raw_values, list):
                iterable = raw_values
            else:
                continue
            for raw_value in iterable:
                name = str(raw_value).strip()
                if not name:
                    continue
                key = (str(entity_type).strip().rstrip("s") or "unknown_scientific_term", name)
                values[key] = values.get(key, 0) + 1
        for marker in metadata.get("markers", []) if isinstance(metadata.get("markers"), list) else []:
            name = str(marker).strip()
            if name:
                key = ("marker", name)
                values[key] = values.get(key, 0) + 1

    return [
        {
            "entity": name,
            "entity_type": entity_type,
            "reference_count": count,
            "relationship_counts": {"asset": count},
        }
        for (entity_type, name), count in sorted(values.items(), key=lambda item: (item[0][0], item[0][1].lower()))
    ]


def _spreadsheet_workspace_summary(asset: dict[str, Any], settings: Settings) -> dict[str, Any]:
    compact = compact_spreadsheet_summary(str(asset.get("asset_id") or ""), settings=settings)
    return {**asset, "compact_summary": compact} if compact else asset


def _statistics_workspace_summary(asset: dict[str, Any], settings: Settings) -> dict[str, Any]:
    compact = compact_graphpad_statistics_summary(str(asset.get("asset_id") or ""), settings=settings)
    interpretation = interpret_statistics_asset(str(asset.get("asset_id") or ""), settings=settings)
    return {
        **asset,
        "compact_summary": compact,
        "interpretation": interpretation,
    }


def _dedupe_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for asset in assets:
        key = str(asset.get("asset_id") or asset)
        if key in seen:
            continue
        seen.add(key)
        output.append(asset)
    return output


def _entity_names(entities: list[dict[str, Any]], entity_type: str, fallback: list[Any]) -> list[str]:
    values = [str(entity.get("entity")) for entity in entities if entity.get("entity_type") == entity_type and entity.get("entity")]
    values.extend(str(value) for value in fallback if value)
    return sorted(set(values), key=str.lower)


def _related_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for entity in entities:
        output.append(
            {
                "entity": entity.get("entity"),
                "entity_type": entity.get("entity_type"),
                "reference_count": entity.get("reference_count"),
                "relationship_counts": entity.get("relationship_counts") or {},
            }
        )
    return sorted(output, key=lambda item: (str(item.get("entity_type")), str(item.get("entity")).lower()))


def _related_experiments(service: KnowledgeGraphService, related_entities: list[dict[str, Any]], current_id: str) -> list[dict[str, Any]]:
    seen = {current_id}
    related = []
    for entity in related_entities[:12]:
        name = str(entity.get("entity") or "")
        if not name:
            continue
        for experiment in service.related_experiments(name):
            experiment_id = str(experiment.get("id") or "")
            if experiment_id and experiment_id not in seen:
                seen.add(experiment_id)
                related.append(experiment)
    return related[:12]


def _provenance(
    experiment: dict[str, Any],
    notebook_entries: list[dict[str, Any]],
    timeline: dict[str, Any],
    microscopy: list[dict[str, Any]],
    graphpad: list[dict[str, Any]],
    spreadsheets: list[dict[str, Any]],
    statistics: list[dict[str, Any]],
    literature: list[dict[str, Any]],
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records = [
        _prov("experiment", "experiment_extraction", experiment.get("source_provider"), document=experiment.get("source_document_id"), timestamp=experiment.get("date")),
    ]
    records.extend(_prov("notebook_entry", "document", item.get("provider"), document=item.get("id"), timestamp=item.get("updated_at")) for item in notebook_entries)
    records.extend(_prov("timeline", "timeline", event.get("source"), asset=(event.get("linked_asset_ids") or [None])[0], document=(event.get("linked_document_ids") or [None])[0], timestamp=event.get("timestamp")) for event in timeline.get("events") or [])
    records.extend(_prov("microscopy", "asset", item.get("provider"), asset=item.get("asset_id"), timestamp=item.get("updated_at")) for item in microscopy)
    records.extend(_prov("graphpad", "asset", item.get("provider"), asset=item.get("asset_id"), timestamp=item.get("updated_at")) for item in graphpad)
    records.extend(_prov("spreadsheet", "asset", item.get("provider"), asset=item.get("asset_id"), timestamp=item.get("updated_at")) for item in spreadsheets)
    records.extend(_prov("statistics", "statistics_interpreter", item.get("provider"), asset=item.get("asset_id"), timestamp=item.get("updated_at")) for item in statistics)
    records.extend(_prov("literature", "document", item.get("provider"), document=item.get("id"), timestamp=item.get("updated_at")) for item in literature)
    records.extend(_prov("entity", "knowledge_graph", "knowledgegraph", document=item.get("entity"), timestamp=None) for item in entities)
    return [record for record in records if record]


def _prov(fact: str, source: str, provider: Any, document: Any = None, asset: Any = None, timestamp: Any = None) -> dict[str, Any]:
    return {
        "fact": fact,
        "source": source,
        "provider": provider,
        "document": document,
        "asset": asset,
        "timestamp": timestamp,
    }


def _workspace_conclusions(experiment: dict[str, Any], statistics: list[dict[str, Any]], literature: list[dict[str, Any]]) -> dict[str, list[str]]:
    observed = []
    if experiment.get("conclusions"):
        observed.append(str(experiment["conclusions"]))
    for stat in statistics:
        interpretation = stat.get("interpretation") if isinstance(stat.get("interpretation"), dict) else {}
        for result in interpretation.get("results", [])[:3] if isinstance(interpretation, dict) else []:
            if result.get("interpretation"):
                observed.append(str(result["interpretation"]))
    return {
        "observed": observed or ["No explicit observed conclusion has been extracted yet."],
        "inferred": ["Workspace links are inferred from experiment IDs, Knowledge Graph entities, and provider metadata."],
        "referenced_from_literature": [str(item.get("title")) for item in literature[:5] if item.get("title")],
    }


def _workspace_limitations(neighborhood: dict[str, Any], statistics: list[dict[str, Any]], literature: list[dict[str, Any]]) -> list[str]:
    limitations = ["Workspace is assembled from local ResearchOS records and provider metadata."]
    if not neighborhood.get("notebook"):
        limitations.append("No source notebook entry is linked to this experiment.")
    if not statistics:
        limitations.append("No parsed statistics are linked to this experiment.")
    if not literature:
        limitations.append("No literature references are linked through shared Knowledge Graph entities.")
    return limitations


def _workspace_summary(
    experiment: dict[str, Any],
    neighborhood: dict[str, Any],
    statistics: list[dict[str, Any]],
    literature: list[dict[str, Any]],
    limitations: list[str],
    settings: Settings,
    use_ai: bool,
) -> dict[str, Any]:
    local = {
        "observed": _workspace_conclusions(experiment, statistics, literature)["observed"],
        "inferred": [
            f"{len(neighborhood.get('entities') or [])} Knowledge Graph entities connect this experiment to local records.",
            f"{len(neighborhood.get('images') or [])} microscopy/image asset(s), {len(neighborhood.get('spreadsheets') or [])} spreadsheet(s), and {len(statistics)} statistics record(s) are linked.",
        ],
        "referenced_from_literature": [str(item.get("title")) for item in literature[:5] if item.get("title")],
    }
    if not use_ai:
        return {"provider": "local-fallback", "text": _summary_text(experiment, local), **local}
    try:
        provider = get_ai_provider(settings=settings)
        prompt = (
            "Summarize this ResearchOS experiment workspace. Never invent data. "
            "Separate Observed, Inferred, and Referenced from literature.\n\n"
            f"Experiment: {experiment}\nStatistics: {statistics}\nLiterature: {literature}\nLimitations: {limitations}"
        )
        return {"provider": provider.provider_name, "text": provider.chat(prompt), **local}
    except AIProviderError as exc:
        return {"provider": "local-fallback", "text": _summary_text(experiment, local), "ai_error": str(exc), **local}


def _summary_text(experiment: dict[str, Any], summary: dict[str, list[str]]) -> str:
    label = experiment.get("experiment_id") or experiment.get("title") or experiment.get("id") or "This experiment"
    return (
        f"{label}: Observed: {' '.join(summary['observed'])} "
        f"Inferred: {' '.join(summary['inferred'])} "
        f"Referenced from literature: {', '.join(summary['referenced_from_literature']) or 'none linked'}."
    )


def _overview_section(experiment: dict[str, Any], compounds: list[str], markers: list[str], organoid_batches: list[str]) -> dict[str, Any]:
    return {
        "title": experiment.get("title"),
        "experiment_id": experiment.get("experiment_id") or experiment.get("id"),
        "date": experiment.get("date"),
        "researcher": experiment.get("researcher"),
        "compounds": compounds,
        "markers": markers,
        "organoid_batches": organoid_batches,
    }


def _experimental_setup(experiment: dict[str, Any]) -> dict[str, Any]:
    return {
        "cell_line": experiment.get("cell_line"),
        "organoid_batch": experiment.get("organoid_batch"),
        "concentrations": experiment.get("concentrations") or [],
        "time_points": experiment.get("time_points") or [],
    }


def _workspace_files(microscopy: list[dict[str, Any]], graphpad: list[dict[str, Any]], spreadsheets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"asset_id": item.get("asset_id"), "title": item.get("title"), "filename": item.get("filename"), "provider": item.get("provider"), "path": item.get("path")}
        for item in [*microscopy, *graphpad, *spreadsheets]
    ]

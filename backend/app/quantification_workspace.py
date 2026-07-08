"""Quantification Workspace assembly for ResearchOS experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings, get_settings
from app.evidence_engine import EvidenceEngine
from app.global_knowledge_graph import KnowledgeGraphService
from app.graphpad_provider import compact_graphpad_statistics_summary
from app.research_copilot import ResearchCopilotService
from app.spreadsheet_provider import compact_spreadsheet_summary
from app.statistics_engine import interpret_statistics_asset
from app.storage import SQLiteStore
from app.workflow_engine import WorkflowEngine


@dataclass
class QuantificationWorkspaceService:
    """Build the quantitative-analysis workspace for one experiment.

    This service creates workflow infrastructure only. It does not perform AI
    image analysis, segmentation, cell counting, or microscopy quantification.
    """

    settings: Settings | None = None
    store: SQLiteStore | None = None
    knowledge_graph: KnowledgeGraphService | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.store = self.store or SQLiteStore(settings=self.settings)
        self.knowledge_graph = self.knowledge_graph or KnowledgeGraphService(settings=self.settings, store=self.store)

    def build(self, experiment_id: str, use_ai: bool = False) -> dict[str, Any] | None:
        """Return the complete quantification workspace for an experiment."""

        experiment = self.store.find_experiment_by_reference(experiment_id)
        if experiment is None:
            assets = self.store.list_assets(experiment_id=experiment_id)
            if not assets:
                return None
            experiment = {
                "id": experiment_id,
                "experiment_id": experiment_id,
                "title": f"Quantification workspace for {experiment_id}",
                "source_provider": "asset_graph",
                "compounds": [],
                "markers": [],
            }
        else:
            assets = self.store.list_assets_for_experiment(experiment)

        notebook = self._notebook(experiment)
        raw_images = [self._raw_image(asset, experiment) for asset in assets if _is_image_asset(asset)]
        processed_images = self._processed_image_placeholders(experiment, assets)
        quantification_tables = [self._quant_table(asset) for asset in assets if _is_spreadsheet_asset(asset)]
        graphpad_assets = [self._graphpad_asset(asset) for asset in assets if _is_graphpad_asset(asset)]
        statistical_analysis = self._statistical_analysis(assets)
        representative_figures = self._representative_figures_placeholder(experiment)
        knowledge_graph = self._knowledge_graph(experiment)
        evidence = self._evidence(experiment)
        workflow = self._workflow(experiment)
        sessions = self._sessions(experiment)
        timeline_events = self._timeline_events(experiment, raw_images, quantification_tables, graphpad_assets, statistical_analysis, sessions, notebook)
        copilot = self._copilot(experiment, raw_images, quantification_tables, graphpad_assets, statistical_analysis, evidence, use_ai)
        missing = self._missing_analysis(raw_images, quantification_tables, statistical_analysis)
        future_modules = [
            "ImageJ/Fiji outputs",
            "CellProfiler segmentation",
            "QuPath projects",
            "Napari annotations",
            "cell counting",
            "organoid segmentation",
            "marker intensity",
            "morphology analysis",
            "lamination scoring",
            "automatic GraphPad generation",
            "automatic figure generation",
        ]
        provenance = _provenance(experiment, raw_images, quantification_tables, graphpad_assets, statistical_analysis, notebook)

        return {
            "experiment": experiment,
            "workspace_type": "quantification",
            "overview": {
                "title": f"Quantification Workspace: {_experiment_label(experiment)}",
                "raw_image_count": len(raw_images),
                "processed_image_count": len(processed_images),
                "quantification_table_count": len(quantification_tables),
                "graphpad_asset_count": len(graphpad_assets),
                "statistical_result_count": len(statistical_analysis),
                "missing_analysis": missing,
            },
            "raw_images": raw_images,
            "processed_images": processed_images,
            "quantification_tables": quantification_tables,
            "statistical_analysis": statistical_analysis,
            "graphpad_assets": graphpad_assets,
            "representative_figures": representative_figures,
            "notebook": notebook,
            "sessions": sessions,
            "knowledge_graph": knowledge_graph,
            "evidence": evidence,
            "workflow": workflow,
            "timeline_events": timeline_events,
            "research_copilot": copilot,
            "future_modules": future_modules,
            "provenance": provenance,
            "limitations": [
                "No AI image analysis, segmentation, or automated quantification is implemented in this milestone.",
                "Processed images and representative figures are placeholders for future provider outputs.",
                "Statistical interpretations depend on imported GraphPad/spreadsheet metadata and should be checked against source files.",
            ],
            "sections": {
                "raw_images": raw_images,
                "processed_images": processed_images,
                "quantification_tables": quantification_tables,
                "statistical_analysis": statistical_analysis,
                "representative_figures": representative_figures,
                "research_copilot": copilot,
                "timeline": timeline_events,
                "knowledge_graph": knowledge_graph,
                "evidence": evidence,
                "workflow": workflow,
            },
        }

    def _notebook(self, experiment: dict[str, Any]) -> dict[str, Any] | None:
        source_document_id = str(experiment.get("source_document_id") or "")
        if not source_document_id:
            return None
        document = self.store.get_document(source_document_id)
        if document is None:
            return None
        return {
            "document_id": document.get("id"),
            "title": document.get("title"),
            "provider": document.get("provider"),
            "updated_at": document.get("updated_at") or document.get("ingested_at"),
            "provenance": [_prov("source_notebook", "sqlite", "documents", document_id=document.get("id"))],
        }

    def _raw_image(self, asset: dict[str, Any], experiment: dict[str, Any]) -> dict[str, Any]:
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        markers = _as_list(metadata.get("markers"))
        channels = _as_list(metadata.get("channels")) or markers
        return {
            "asset_id": asset.get("asset_id"),
            "title": asset.get("title"),
            "filename": asset.get("filename"),
            "provider": asset.get("provider"),
            "path": asset.get("path"),
            "experiment_id": asset.get("experiment_id") or experiment.get("experiment_id") or experiment.get("id"),
            "markers": markers,
            "channels": channels,
            "timepoint": metadata.get("timepoint"),
            "acquisition": {
                "source_folder": metadata.get("source_folder"),
                "extension": metadata.get("extension"),
                "parser": metadata.get("parser"),
                "acquired_at": metadata.get("acquired_at") or asset.get("created_at"),
            },
            "metadata": metadata,
            "provenance": [_prov("raw_image", "sqlite", "assets", asset_id=asset.get("asset_id"), source_provider=asset.get("provider"))],
        }

    def _processed_image_placeholders(self, experiment: dict[str, Any], assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        processed = [asset for asset in assets if str(asset.get("asset_type") or "").lower() in {"mask", "segmentation", "processed_image", "figure"}]
        if processed:
            return [
                {
                    "asset_id": asset.get("asset_id"),
                    "title": asset.get("title"),
                    "filename": asset.get("filename"),
                    "provider": asset.get("provider"),
                    "path": asset.get("path"),
                    "status": "imported",
                    "provenance": [_prov("processed_image", "sqlite", "assets", asset_id=asset.get("asset_id"))],
                }
                for asset in processed
            ]
        return [
            {
                "title": "Processed image outputs",
                "status": "placeholder",
                "summary": "Future ImageJ, Fiji, CellProfiler, segmentation, mask, and representative-image outputs will appear here.",
                "provenance": [_prov("processed_image_placeholder", "ResearchOS", "quantification_workspace", experiment_id=experiment.get("id"))],
            }
        ]

    def _quant_table(self, asset: dict[str, Any]) -> dict[str, Any]:
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        compact = compact_spreadsheet_summary(str(asset.get("asset_id")), settings=self.settings) if asset.get("asset_id") else None
        tables = metadata.get("detected_tables") if isinstance(metadata.get("detected_tables"), list) else []
        return {
            "asset_id": asset.get("asset_id"),
            "title": asset.get("title"),
            "filename": asset.get("filename"),
            "provider": asset.get("provider"),
            "path": asset.get("path"),
            "experiment_id": asset.get("experiment_id"),
            "variables": _variables_from_tables(tables, compact),
            "groups": _groups_from_compact(compact),
            "replicates": _replicates_from_compact(compact),
            "measurements": (compact or {}).get("key_numeric_measurements", []),
            "summary_statistics": compact or {},
            "provenance": [_prov("quantification_table", "sqlite", "assets", asset_id=asset.get("asset_id"))],
        }

    def _graphpad_asset(self, asset: dict[str, Any]) -> dict[str, Any]:
        compact = compact_graphpad_statistics_summary(str(asset.get("asset_id")), settings=self.settings) if asset.get("asset_id") else None
        return {
            "asset_id": asset.get("asset_id"),
            "title": asset.get("title"),
            "filename": asset.get("filename"),
            "provider": asset.get("provider"),
            "path": asset.get("path"),
            "experiment_id": asset.get("experiment_id"),
            "summary": compact or {},
            "provenance": [_prov("graphpad_analysis", "sqlite", "assets", asset_id=asset.get("asset_id"))],
        }

    def _statistical_analysis(self, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        for asset in assets:
            if not _asset_has_statistics(asset) and not _is_spreadsheet_asset(asset):
                continue
            interpreted = interpret_statistics_asset(str(asset.get("asset_id")), settings=self.settings) if asset.get("asset_id") else None
            compact = None
            if _is_graphpad_asset(asset):
                compact = compact_graphpad_statistics_summary(str(asset.get("asset_id")), settings=self.settings)
            elif _is_spreadsheet_asset(asset):
                compact = compact_spreadsheet_summary(str(asset.get("asset_id")), settings=self.settings)
            items.append(
                {
                    "asset_id": asset.get("asset_id"),
                    "title": asset.get("title"),
                    "provider": asset.get("provider"),
                    "experiment_id": asset.get("experiment_id"),
                    "interpretation": interpreted or {},
                    "compact_summary": compact or {},
                    "significance": _significance(interpreted),
                    "effect_size": None,
                    "confidence_interval": None,
                    "evidence_summary": (interpreted or {}).get("summary"),
                    "provenance": [_prov("statistical_analysis", "sqlite", "assets", asset_id=asset.get("asset_id"))],
                }
            )
        return items

    def _representative_figures_placeholder(self, experiment: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "title": "Representative figures",
                "status": "placeholder",
                "summary": "Future publication figures, annotated microscopy, and figure panels will appear here.",
                "provenance": [_prov("representative_figures_placeholder", "ResearchOS", "quantification_workspace", experiment_id=experiment.get("id"))],
            }
        ]

    def _knowledge_graph(self, experiment: dict[str, Any]) -> dict[str, Any]:
        neighborhood = self.knowledge_graph.experiment_neighborhood(str(experiment.get("id") or experiment.get("experiment_id") or ""))
        if neighborhood is None and experiment.get("experiment_id"):
            neighborhood = self.knowledge_graph.experiment_neighborhood(str(experiment.get("experiment_id")))
        if neighborhood is None:
            return {"entities": [], "markers": [], "compounds": [], "protocols": [], "statistics": [], "provenance": []}
        return {
            "entities": neighborhood.get("entities") or [],
            "markers": neighborhood.get("markers") or [],
            "compounds": neighborhood.get("compounds") or [],
            "genes": neighborhood.get("genes") or [],
            "proteins": neighborhood.get("proteins") or [],
            "statistics": neighborhood.get("statistics") or [],
            "resources": neighborhood.get("resources") or [],
            "provenance": [_prov("knowledge_graph_neighborhood", "knowledge_graph", "dynamic_graph", experiment_id=experiment.get("id"))],
        }

    def _evidence(self, experiment: dict[str, Any]) -> dict[str, Any]:
        terms = [
            str(experiment.get("experiment_id") or experiment.get("id") or ""),
            *[str(item) for item in experiment.get("markers", []) if item],
            *[str(item) for item in experiment.get("compounds", []) if item],
        ]
        question = "What quantitative evidence exists for " + " ".join(term for term in terms if term)
        try:
            return EvidenceEngine(settings=self.settings, store=self.store, knowledge_graph=self.knowledge_graph).query(question).as_dict()
        except ValueError:
            return {"question": question, "summary": "No evidence question could be built.", "provenance": []}

    def _workflow(self, experiment: dict[str, Any]) -> dict[str, Any]:
        if not experiment.get("id") or str(experiment.get("source_provider")) == "asset_graph":
            return {"current_stage": "Quantification", "recommended_next_actions": ["Link quantification assets to an extracted experiment."]}
        return WorkflowEngine(self.store).workflow_for_experiment(experiment)

    def _sessions(self, experiment: dict[str, Any]) -> list[dict[str, Any]]:
        references = {str(experiment.get("id") or ""), str(experiment.get("experiment_id") or "")}
        return [
            session
            for session in self.store.list_sessions(workspace_id=str(experiment.get("workspace_id") or "") or None)
            if str(session.get("experiment_id") or "") in references
        ]

    def _timeline_events(
        self,
        experiment: dict[str, Any],
        raw_images: list[dict[str, Any]],
        quantification_tables: list[dict[str, Any]],
        graphpad_assets: list[dict[str, Any]],
        statistical_analysis: list[dict[str, Any]],
        sessions: list[dict[str, Any]],
        notebook: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if notebook:
            events.append(_timeline_event(notebook.get("updated_at"), "notebook_entry", str(notebook.get("title") or "Notebook entry"), "Notebook source linked to quantification workspace.", "notebook", [], [str(notebook.get("document_id"))]))
        for image in raw_images:
            events.append(_timeline_event(image.get("acquisition", {}).get("acquired_at"), "images_imported", str(image.get("filename") or image.get("title")), "Raw microscopy/image asset linked for quantification.", "microscopy", [str(image.get("asset_id"))], []))
        for table in quantification_tables:
            events.append(_timeline_event(None, "spreadsheet_imported", str(table.get("filename") or table.get("title")), "Quantification table available for summary statistics.", "spreadsheet", [str(table.get("asset_id"))], []))
        for graphpad in graphpad_assets:
            events.append(_timeline_event(None, "graphpad_imported", str(graphpad.get("filename") or graphpad.get("title")), "GraphPad analysis asset linked to experiment.", "graphpad", [str(graphpad.get("asset_id"))], []))
        for stats in statistical_analysis:
            events.append(_timeline_event(None, "statistics_completed", str(stats.get("title") or stats.get("asset_id")), str(stats.get("evidence_summary") or "Statistical interpretation available."), "statistics", [str(stats.get("asset_id"))], []))
        for session in sessions:
            events.append(_timeline_event(session.get("updated_at") or session.get("start_time"), "session_context", str(session.get("session_id")), "Experiment session connected to quantification context.", "sessions", [], []))
        events.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        return events

    def _copilot(
        self,
        experiment: dict[str, Any],
        raw_images: list[dict[str, Any]],
        quantification_tables: list[dict[str, Any]],
        graphpad_assets: list[dict[str, Any]],
        statistical_analysis: list[dict[str, Any]],
        evidence: dict[str, Any],
        use_ai: bool,
    ) -> dict[str, Any]:
        missing = self._missing_analysis(raw_images, quantification_tables, statistical_analysis)
        local_sections = {
            "current_quantitative_evidence": [
                {
                    "category": "observed",
                    "text": f"{len(raw_images)} raw image(s), {len(quantification_tables)} quantification table(s), {len(graphpad_assets)} GraphPad asset(s), and {len(statistical_analysis)} statistical analysis item(s) are linked.",
                    "provenance": [_prov("quantification_counts", "ResearchOS", "quantification_workspace", experiment_id=experiment.get("id"))],
                }
            ],
            "missing_analyses": [
                {
                    "category": "inferred",
                    "text": item,
                    "provenance": [_prov("missing_quantification_step", "ResearchOS", "quantification_workspace", experiment_id=experiment.get("id"))],
                }
                for item in missing
            ],
            "potential_concerns": [
                {
                    "category": "inferred",
                    "text": "Quantification evidence should be checked against source image/table/statistics files before publication use.",
                    "provenance": [_prov("quantification_limitations", "ResearchOS", "quantification_workspace", experiment_id=experiment.get("id"))],
                }
            ],
            "recommended_next_steps": [
                {
                    "category": "suggested",
                    "text": missing[0] if missing else "Review statistical interpretations and select representative figures.",
                    "provenance": [_prov("quantification_next_step", "ResearchOS", "quantification_workspace", experiment_id=experiment.get("id"))],
                }
            ],
            "evidence_summary": evidence,
        }
        if not use_ai:
            return {"provider": "local-fallback", "sections": local_sections}
        workspace = {
            "experiment": experiment,
            "microscopy": raw_images,
            "spreadsheets": quantification_tables,
            "graphpad": graphpad_assets,
            "statistics": statistical_analysis,
            "evidence": evidence,
            "limitations": missing,
        }
        return ResearchCopilotService(settings=self.settings).build(workspace, use_ai=True)

    def _missing_analysis(
        self,
        raw_images: list[dict[str, Any]],
        quantification_tables: list[dict[str, Any]],
        statistical_analysis: list[dict[str, Any]],
    ) -> list[str]:
        missing = []
        if raw_images and not quantification_tables:
            missing.append("Raw images are linked but no quantification table is available.")
        if quantification_tables and not statistical_analysis:
            missing.append("Quantification tables are available but no statistical interpretation is linked.")
        if not raw_images:
            missing.append("No raw microscopy/image assets are linked to this experiment.")
        if not statistical_analysis:
            missing.append("No parsed statistical analysis is linked to this experiment.")
        return missing


def _is_image_asset(asset: dict[str, Any]) -> bool:
    return str(asset.get("provider") or "").lower() == "microscopy" or str(asset.get("asset_type") or "").lower() in {"image", "microscopy"}


def _is_graphpad_asset(asset: dict[str, Any]) -> bool:
    return str(asset.get("provider") or "").lower() == "graphpad" or str(asset.get("asset_type") or "").lower() == "graphpad"


def _is_spreadsheet_asset(asset: dict[str, Any]) -> bool:
    return str(asset.get("provider") or "").lower() == "spreadsheet" or str(asset.get("asset_type") or "").lower() in {"spreadsheet", "csv"}


def _asset_has_statistics(asset: dict[str, Any]) -> bool:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    return bool(metadata.get("statistics"))


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _variables_from_tables(tables: list[Any], compact: dict[str, Any] | None) -> list[str]:
    variables = [str(item.get("measurement")) for item in (compact or {}).get("key_numeric_measurements", []) if isinstance(item, dict) and item.get("measurement")]
    for table in tables:
        if isinstance(table, dict):
            variables.extend(str(key) for key in (table.get("numeric_summaries") or {}).keys())
    return sorted(set(variables))[:40]


def _groups_from_compact(compact: dict[str, Any] | None) -> list[str]:
    groups = compact.get("detected_treatments_groups", []) if isinstance(compact, dict) else []
    return [str(item) for item in groups if str(item).strip()]


def _replicates_from_compact(compact: dict[str, Any] | None) -> dict[str, Any]:
    return compact.get("n_per_group", {}) if isinstance(compact, dict) else {}


def _significance(interpreted: dict[str, Any] | None) -> list[dict[str, Any]]:
    results = interpreted.get("results", []) if isinstance(interpreted, dict) else []
    return [
        {
            "variable": result.get("variable"),
            "groups_compared": result.get("groups_compared"),
            "p_value": result.get("p_value"),
            "adjusted_p_value": result.get("adjusted_p_value"),
            "significance": result.get("significance"),
            "interpretation": result.get("interpretation"),
        }
        for result in results
        if isinstance(result, dict)
    ]


def _timeline_event(timestamp: Any, event_type: str, title: str, description: str, source: str, linked_asset_ids: list[str], linked_document_ids: list[str]) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "event_type": event_type,
        "title": title,
        "description": description,
        "source": source,
        "linked_asset_ids": [item for item in linked_asset_ids if item and item != "None"],
        "linked_document_ids": [item for item in linked_document_ids if item and item != "None"],
    }


def _experiment_label(experiment: dict[str, Any]) -> str:
    return str(experiment.get("experiment_id") or experiment.get("title") or experiment.get("id") or "Experiment")


def _provenance(
    experiment: dict[str, Any],
    raw_images: list[dict[str, Any]],
    quantification_tables: list[dict[str, Any]],
    graphpad_assets: list[dict[str, Any]],
    statistical_analysis: list[dict[str, Any]],
    notebook: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    records = [_prov("experiment", "sqlite", "experiments", experiment_id=experiment.get("id"))]
    if notebook:
        records.extend(notebook.get("provenance") or [])
    for collection, fact in [(raw_images, "raw_image"), (quantification_tables, "quantification_table"), (graphpad_assets, "graphpad_analysis"), (statistical_analysis, "statistical_analysis")]:
        for item in collection[:20]:
            records.append(_prov(fact, "sqlite", "assets", asset_id=item.get("asset_id")))
    return records


def _prov(fact: str, source: str, provider: str, **extra: Any) -> dict[str, Any]:
    return {"fact": fact, "source": source, "provider": provider, **{key: value for key, value in extra.items() if value is not None}}

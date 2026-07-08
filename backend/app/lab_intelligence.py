"""Laboratory Intelligence feed for proactive, provenance-backed alerts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config import Settings, get_settings
from app.global_knowledge_graph import KnowledgeGraphService
from app.lab_workspaces import current_workspace
from app.scientific_memory import ScientificMemoryService
from app.statistics_engine import interpret_statistics_asset
from app.storage import SQLiteStore
from app.workflow_engine import WorkflowEngine

PRIORITY_SCORES = {"critical": 90, "high": 70, "medium": 50, "low": 30}


@dataclass
class LaboratoryIntelligenceService:
    """Build a deterministic laboratory attention feed from existing evidence.

    The service does not create scientific observations. It only surfaces
    observed records and conservative gaps inferred from existing ResearchOS
    metadata, and every item carries provenance back to its source records.
    """

    settings: Settings | None = None
    store: SQLiteStore | None = None
    knowledge_graph: KnowledgeGraphService | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.store = self.store or SQLiteStore(settings=self.settings)
        self.knowledge_graph = self.knowledge_graph or KnowledgeGraphService(settings=self.settings, store=self.store)

    def refresh(self) -> None:
        """Compatibility hook for the event bus automation refresh path."""

        if hasattr(self.knowledge_graph, "refresh"):
            self.knowledge_graph.refresh()

    def build_feed(
        self,
        item_type: str | None = None,
        include_dismissed: bool = False,
        pinned_first: bool = True,
        limit: int = 50,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Return a sorted, filterable Laboratory Intelligence feed."""

        resolved_workspace = workspace_id or str(current_workspace(self.settings, self.store).get("workspace_id") or "")
        experiments = self.store.list_experiments(workspace_id=resolved_workspace)
        documents = self.store.list_documents(workspace_id=resolved_workspace)
        assets = self.store.list_assets(workspace_id=resolved_workspace)
        resources = self.store.list_resources(workspace_id=resolved_workspace)
        sessions = self.store.list_sessions(workspace_id=resolved_workspace)
        states = self.store.lab_intelligence_item_states()

        items: list[dict[str, Any]] = []
        items.extend(self._session_items(sessions))
        items.extend(self._experiment_items(experiments, assets))
        items.extend(self._workflow_items(experiments))
        items.extend(self._asset_items(assets))
        items.extend(self._literature_items(documents))
        items.extend(self._resource_items(resources))
        items.extend(self._knowledge_graph_items(resolved_workspace))
        items.extend(self._memory_items(experiments, resolved_workspace))
        items.extend(self._copilot_items(experiments, assets))

        filtered = []
        normalized_filter = _normalize(item_type or "")
        for item in _dedupe_items(items):
            state = states.get(str(item["item_id"]), {})
            item["dismissed"] = bool(state.get("dismissed", False))
            item["pinned"] = bool(state.get("pinned", False))
            if normalized_filter and _normalize(str(item.get("item_type") or "")) != normalized_filter:
                continue
            if item["dismissed"] and not include_dismissed:
                continue
            filtered.append(item)

        filtered.sort(
            key=lambda item: (
                bool(item.get("pinned")) if pinned_first else False,
                int(item.get("priority_score") or 0),
                str(item.get("timestamp") or ""),
            ),
            reverse=True,
        )
        visible = filtered[: max(1, limit)]
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "workspace_id": resolved_workspace,
            "total_items": len(filtered),
            "items": visible,
            "filters": self._filters(filtered),
            "priority_counts": self._priority_counts(filtered),
            "dismissed_count": sum(1 for state in states.values() if state.get("dismissed")),
            "pinned_count": sum(1 for item in filtered if item.get("pinned")),
            "principle": "Laboratory Intelligence only summarizes observed records or provenance-backed gaps.",
        }

    def set_item_state(
        self,
        item_id: str,
        dismissed: bool | None = None,
        pinned: bool | None = None,
    ) -> dict[str, Any]:
        """Persist dismiss/pin state and return the updated state."""

        return self.store.set_lab_intelligence_item_state(item_id, dismissed=dismissed, pinned=pinned)

    def _session_items(self, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        for session in sessions:
            if session.get("status") != "active":
                continue
            experiment_id = str(session.get("experiment_id") or "unlinked experiment")
            items.append(
                _feed_item(
                    "Experiment Reminder",
                    f"Active session for {experiment_id}",
                    "A laboratory session is currently active. Finish the session when bench work is complete so the timeline stays accurate.",
                    "high",
                    session.get("updated_at") or session.get("start_time"),
                    related_experiments=[experiment_id] if session.get("experiment_id") else [],
                    suggested_action="Open Bench Mode or end the session after recording final observations.",
                    provenance=[_prov("active_session", "sqlite", "experiment_sessions", session_id=session.get("session_id"))],
                    route="/mobile/sessions/active",
                )
            )
        return items

    def _experiment_items(self, experiments: list[dict[str, Any]], assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        for experiment in experiments:
            label = _experiment_label(experiment)
            linked_assets = _assets_for_experiment(experiment, assets)
            statistics_assets = [asset for asset in linked_assets if _asset_has_statistics(asset)]
            notebook_missing = not experiment.get("source_document_id") or self.store.get_document(str(experiment.get("source_document_id"))) is None
            if notebook_missing:
                items.append(
                    _feed_item(
                        "Missing Notebook",
                        f"{label} has no source notebook entry",
                        "This experiment record is missing a traceable source document in the local database.",
                        "high",
                        experiment.get("extracted_at") or experiment.get("date"),
                        related_experiments=[str(experiment.get("id"))],
                        suggested_action="Attach or ingest the notebook entry before relying on this experiment as evidence.",
                        provenance=[_prov("experiment", "sqlite", "experiments", experiment_id=experiment.get("id"))],
                        route=f"/mobile/experiments/{experiment.get('id')}/workspace",
                    )
                )
            if not statistics_assets and (experiment.get("markers") or experiment.get("compounds")):
                items.append(
                    _feed_item(
                        "Missing Analysis",
                        f"{label} has no linked parsed statistics",
                        "ResearchOS found experimental entities but no linked GraphPad, spreadsheet, or statistics asset.",
                        "medium",
                        experiment.get("extracted_at") or experiment.get("date"),
                        related_experiments=[str(experiment.get("id"))],
                        suggested_action="Register or scan the quantitative analysis files for this experiment.",
                        provenance=[_prov("experiment", "sqlite", "experiments", experiment_id=experiment.get("id"))],
                        route=f"/mobile/experiments/{experiment.get('id')}/workspace",
                    )
                )
            if not experiment.get("conclusions"):
                items.append(
                    _feed_item(
                        "Experiment Reminder",
                        f"{label} is missing extracted conclusions",
                        "The experiment record has notes but no extracted conclusion field.",
                        "medium",
                        experiment.get("extracted_at") or experiment.get("date"),
                        related_experiments=[str(experiment.get("id"))],
                        suggested_action="Review the notebook entry and add or extract the conclusion.",
                        provenance=[_prov("experiment", "sqlite", "experiments", experiment_id=experiment.get("id"))],
                        route=f"/mobile/experiments/{experiment.get('id')}/workspace",
                    )
                )
        return items

    def _workflow_items(self, experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        engine = WorkflowEngine(self.store)
        items = []
        for experiment in experiments:
            workflow = engine.workflow_for_experiment(experiment)
            stage = str(workflow.get("current_stage") or "Planning")
            recommended = list(workflow.get("recommended_next_actions") or workflow.get("suggested_next_actions") or [])
            blocking = list(workflow.get("blocking_issues") or [])
            if not recommended and not blocking:
                continue
            details = blocking[:2] or recommended[:2]
            label = _experiment_label(experiment)
            items.append(
                _feed_item(
                    "Workflow Reminder",
                    f"{label}: {stage}",
                    "; ".join(str(item) for item in details),
                    "high" if blocking else "medium",
                    workflow.get("updated_at") or experiment.get("extracted_at") or experiment.get("date"),
                    related_experiments=[str(experiment.get("id"))],
                    suggested_action=str(details[0]) if details else "Review workflow stage.",
                    provenance=[
                        _prov(
                            "workflow_stage",
                            "sqlite",
                            "workflow_states",
                            workflow_id=workflow.get("workflow_id"),
                            experiment_id=experiment.get("id"),
                        )
                    ],
                    route=f"/mobile/experiments/{experiment.get('id')}/workspace",
                )
            )
        return items

    def _asset_items(self, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        for asset in assets:
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            provider = str(asset.get("provider") or "")
            asset_type = str(asset.get("asset_type") or "")
            if _asset_has_statistics(asset):
                summary = interpret_statistics_asset(str(asset.get("asset_id")), settings=self.settings)
                text = str((summary or {}).get("summary") or "Parsed statistical metadata is available.")
                priority = "high" if "significant" in text.lower() and "not statistically significant" not in text.lower() else "medium"
                items.append(
                    _feed_item(
                        "Statistical Finding",
                        str(asset.get("title") or asset.get("filename") or "Statistics asset"),
                        text,
                        priority,
                        asset.get("updated_at") or asset.get("created_at"),
                        related_experiments=[str(asset.get("experiment_id"))] if asset.get("experiment_id") else [],
                        suggested_action="Review the parsed statistical interpretation against the original file.",
                        provenance=[_prov("statistics_asset", "sqlite", "assets", asset_id=asset.get("asset_id"), source_provider=provider)],
                        route=f"#/assets/{asset.get('asset_id')}",
                    )
                )
            elif asset_type in {"spreadsheet", "csv"} or provider == "spreadsheet":
                items.append(
                    _feed_item(
                        "Missing Analysis",
                        str(asset.get("title") or asset.get("filename") or "Spreadsheet asset"),
                        "Spreadsheet is registered but no statistical result rows were detected.",
                        "medium",
                        asset.get("updated_at") or asset.get("created_at"),
                        related_experiments=[str(asset.get("experiment_id"))] if asset.get("experiment_id") else [],
                        suggested_action="Open the spreadsheet summary or add explicit p-value/statistics columns if available.",
                        provenance=[_prov("spreadsheet_asset", "sqlite", "assets", asset_id=asset.get("asset_id"), source_provider=provider)],
                        route=f"#/assets/{asset.get('asset_id')}",
                    )
                )
            elif provider == "graphpad":
                items.append(
                    _feed_item(
                        "Protocol Insight",
                        str(asset.get("title") or asset.get("filename") or "GraphPad asset"),
                        "GraphPad-associated file is registered and can be linked into experiment interpretation.",
                        "low",
                        asset.get("updated_at") or asset.get("created_at"),
                        related_experiments=[str(asset.get("experiment_id"))] if asset.get("experiment_id") else [],
                        suggested_action="Confirm the asset is linked to the correct experiment.",
                        provenance=[_prov("graphpad_asset", "sqlite", "assets", asset_id=asset.get("asset_id"), source_provider=provider)],
                        route=f"#/assets/{asset.get('asset_id')}",
                    )
                )
            elif provider == "microscopy" or asset_type in {"image", "microscopy"}:
                markers = metadata.get("markers") if isinstance(metadata.get("markers"), list) else []
                items.append(
                    _feed_item(
                        "Knowledge Graph Insight",
                        str(asset.get("title") or asset.get("filename") or "Microscopy asset"),
                        f"Microscopy/image asset indexed{f' with markers {', '.join(map(str, markers[:4]))}' if markers else ''}.",
                        "low",
                        asset.get("updated_at") or asset.get("created_at"),
                        related_experiments=[str(asset.get("experiment_id"))] if asset.get("experiment_id") else [],
                        suggested_action="Open the experiment workspace to review image context.",
                        provenance=[_prov("microscopy_asset", "sqlite", "assets", asset_id=asset.get("asset_id"), source_provider=provider)],
                        route=f"#/assets/{asset.get('asset_id')}",
                    )
                )
        return items

    def _literature_items(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        for document in documents:
            if document.get("provider") != "literature":
                continue
            items.append(
                _feed_item(
                    "New Literature",
                    str(document.get("title") or "Literature document"),
                    "Literature source is available for assistant and evidence synthesis.",
                    "medium",
                    document.get("updated_at") or document.get("created_at") or document.get("ingested_at"),
                    related_literature=[str(document.get("id"))],
                    suggested_action="Ask ResearchOS to compare this literature with matching lab experiments.",
                    provenance=[_prov("literature_document", "sqlite", "documents", document_id=document.get("id"))],
                    route="#/literature",
                )
            )
        return items

    def _resource_items(self, resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        for resource in resources:
            missing = [
                label
                for field, label in [
                    ("lot_number", "lot number"),
                    ("storage_location", "storage location"),
                    ("expiration", "expiration"),
                ]
                if not resource.get(field)
            ]
            if not missing:
                continue
            items.append(
                _feed_item(
                    "Resource Warning",
                    f"{resource.get('name')} is missing resource metadata",
                    f"Missing {', '.join(missing)}. This may make future troubleshooting harder.",
                    "medium",
                    resource.get("updated_at") or resource.get("created_at"),
                    related_resources=[str(resource.get("resource_id"))],
                    suggested_action="Update the resource record with vendor, lot, storage, and expiration details when available.",
                    provenance=[_prov("resource", "sqlite", "resources", resource_id=resource.get("resource_id"))],
                    route="#/resources",
                )
            )
        return items

    def _knowledge_graph_items(self, workspace_id: str) -> list[dict[str, Any]]:
        graph = KnowledgeGraphService(settings=self.settings, store=self.store, workspace_id=workspace_id)
        summary = graph.summary()
        top = list(summary.get("top_entities") or [])[:5]
        if not top:
            return []
        entity_names = [str(item.get("entity") or item.get("name") or "") for item in top if isinstance(item, dict)]
        return [
            _feed_item(
                "Knowledge Graph Insight",
                "Top connected entities updated",
                f"Current top entities: {', '.join(entity_names[:5])}.",
                "low",
                datetime.now().isoformat(timespec="seconds"),
                suggested_action="Open the Knowledge Graph to inspect related experiments, assets, and literature.",
                provenance=[_prov("knowledge_graph_summary", "knowledge_graph", "dynamic_graph", entity_count=summary.get("entity_count"))],
                route="#/graph",
            )
        ]

    def _memory_items(self, experiments: list[dict[str, Any]], workspace_id: str) -> list[dict[str, Any]]:
        if len(experiments) < 2:
            return []
        service = ScientificMemoryService(settings=self.settings, store=self.store, workspace_id=workspace_id)
        items = []
        for experiment in experiments[:5]:
            try:
                similar = service.find_similar_experiments(str(experiment.get("id")), limit=1)
            except LookupError:
                similar = []
            if not similar:
                continue
            closest = similar[0]
            closest_experiment = closest.get("experiment") if isinstance(closest.get("experiment"), dict) else {}
            if not closest_experiment:
                continue
            items.append(
                _feed_item(
                    "Similar Experiment",
                    f"{_experiment_label(experiment)} resembles {_experiment_label(closest_experiment)}",
                    f"Scientific Memory similarity score: {closest.get('similarity_score')}.",
                    "low",
                    experiment.get("extracted_at") or experiment.get("date"),
                    related_experiments=[str(experiment.get("id")), str(closest_experiment.get("id"))],
                    suggested_action="Compare the workspaces before planning follow-up experiments.",
                    provenance=[_prov("scientific_memory", "memory", "scientific_memory", experiment_id=experiment.get("id"))],
                    route=f"/mobile/experiments/{experiment.get('id')}/workspace",
                )
            )
        return items

    def _copilot_items(self, experiments: list[dict[str, Any]], assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        for experiment in experiments[:6]:
            linked_assets = _assets_for_experiment(experiment, assets)
            if experiment.get("conclusions") and linked_assets:
                continue
            gap = "statistics and conclusion" if not linked_assets and not experiment.get("conclusions") else "conclusion" if not experiment.get("conclusions") else "linked assets"
            items.append(
                _feed_item(
                    "Copilot Recommendation",
                    f"Review {_experiment_label(experiment)} before reuse",
                    f"Copilot context indicates this experiment is missing {gap}.",
                    "medium",
                    experiment.get("extracted_at") or experiment.get("date"),
                    related_experiments=[str(experiment.get("id"))],
                    suggested_action="Open the workspace and resolve missing evidence before using the experiment in synthesis.",
                    provenance=[_prov("copilot_gap_check", "ResearchOS", "experiments", experiment_id=experiment.get("id"))],
                    route=f"/mobile/experiments/{experiment.get('id')}/workspace",
                )
            )
        return items

    def _filters(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for item in items:
            item_type = str(item.get("item_type") or "Other")
            counts[item_type] = counts.get(item_type, 0) + 1
        return [{"item_type": key, "count": counts[key]} for key in sorted(counts)]

    def _priority_counts(self, items: list[dict[str, Any]]) -> dict[str, int]:
        counts = {key: 0 for key in PRIORITY_SCORES}
        for item in items:
            priority = str(item.get("priority") or "low")
            counts[priority] = counts.get(priority, 0) + 1
        return counts


def _feed_item(
    item_type: str,
    title: str,
    summary: str,
    priority: str,
    timestamp: Any,
    *,
    related_experiments: list[str] | None = None,
    related_resources: list[str] | None = None,
    related_literature: list[str] | None = None,
    suggested_action: str,
    provenance: list[dict[str, Any]],
    route: str | None = None,
) -> dict[str, Any]:
    priority_name = priority if priority in PRIORITY_SCORES else "low"
    payload = {
        "item_type": item_type,
        "title": title,
        "summary": summary,
        "priority": priority_name,
        "priority_score": PRIORITY_SCORES[priority_name],
        "timestamp": str(timestamp or datetime.now().isoformat(timespec="seconds")),
        "related_experiments": related_experiments or [],
        "related_resources": related_resources or [],
        "related_literature": related_literature or [],
        "suggested_action": suggested_action,
        "provenance": provenance,
        "route": route,
    }
    payload["item_id"] = "feed:" + hashlib.sha1(
        "|".join(
            [
                item_type,
                title,
                ",".join(payload["related_experiments"]),
                ",".join(payload["related_resources"]),
                ",".join(payload["related_literature"]),
            ]
        ).encode("utf-8")
    ).hexdigest()[:16]
    return payload


def _prov(fact: str, source: str, provider: str, **extra: Any) -> dict[str, Any]:
    return {"fact": fact, "source": source, "provider": provider, **{key: value for key, value in extra.items() if value is not None}}


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique = []
    for item in items:
        item_id = str(item.get("item_id") or "")
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        unique.append(item)
    return unique


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


def _experiment_label(experiment: dict[str, Any]) -> str:
    return str(experiment.get("experiment_id") or experiment.get("title") or experiment.get("id") or "Experiment")


def _assets_for_experiment(experiment: dict[str, Any], assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    references = {str(experiment.get("id") or ""), str(experiment.get("experiment_id") or "")}
    return [asset for asset in assets if str(asset.get("experiment_id") or "") in references]


def _asset_has_statistics(asset: dict[str, Any]) -> bool:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    return bool(isinstance(metadata, dict) and metadata.get("statistics"))

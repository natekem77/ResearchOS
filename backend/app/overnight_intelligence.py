"""Morning Brief generation for overnight laboratory intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from app.config import Settings, get_settings
from app.global_knowledge_graph import KnowledgeGraphService
from app.lab_intelligence import LaboratoryIntelligenceService
from app.lab_workspaces import current_workspace
from app.protocol_intelligence import ProtocolService
from app.scientific_memory import ScientificMemoryService
from app.storage import SQLiteStore
from app.workflow_engine import WorkflowEngine


@dataclass
class OvernightIntelligenceService:
    """Create a provenance-backed morning briefing for a time window."""

    settings: Settings | None = None
    store: SQLiteStore | None = None
    knowledge_graph: KnowledgeGraphService | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.store = self.store or SQLiteStore(settings=self.settings)
        self.knowledge_graph = self.knowledge_graph or KnowledgeGraphService(settings=self.settings, store=self.store)

    def refresh(self) -> None:
        """Compatibility hook for the automation engine."""

        if hasattr(self.knowledge_graph, "refresh"):
            self.knowledge_graph.refresh()

    def morning_brief(
        self,
        period: str = "today",
        workspace_id: str | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        """Return a deterministic Morning Brief for today, yesterday, or last week."""

        start, end, label = _period_bounds(period)
        resolved_workspace = workspace_id or str(current_workspace(self.settings, self.store).get("workspace_id") or "")
        experiments = self.store.list_experiments(workspace_id=resolved_workspace)
        documents = self.store.list_documents(workspace_id=resolved_workspace)
        assets = self.store.list_assets(workspace_id=resolved_workspace)
        resources = self.store.list_resources(workspace_id=resolved_workspace)
        sessions = self.store.list_sessions(workspace_id=resolved_workspace)
        workflows = WorkflowEngine(self.store).list_workflows(workspace_id=resolved_workspace)
        feed = LaboratoryIntelligenceService(
            settings=self.settings,
            store=self.store,
            knowledge_graph=self.knowledge_graph,
        ).build_feed(include_dismissed=False, limit=100, workspace_id=resolved_workspace)

        sections = {
            "new_experiments": self._new_experiments(experiments, start, end, limit),
            "updated_experiments": self._updated_experiments(experiments, start, end, limit),
            "completed_workflows": self._completed_workflows(workflows, start, end, limit),
            "missing_analyses": self._feed_section(feed, "Missing Analysis", start, end, limit),
            "new_literature": self._new_literature(documents, start, end, limit),
            "knowledge_graph_changes": self._knowledge_graph_changes(resolved_workspace, documents, experiments, assets, start, end),
            "protocol_updates": self._protocol_updates(start, end, limit),
            "resource_alerts": self._resource_alerts(resources, start, end, limit),
            "research_copilot_insights": self._feed_section(feed, "Copilot Recommendation", start, end, limit),
            "suggested_priorities": self._suggested_priorities(feed, start, end, limit),
        }
        total_items = sum(len(items) for items in sections.values())
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "period": period,
            "period_label": label,
            "window": {"start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds")},
            "workspace_id": resolved_workspace,
            "summary": self._summary(total_items, sections, label),
            "sections": sections,
            "section_counts": {name: len(items) for name, items in sections.items()},
            "total_items": total_items,
            "principle": "Morning Brief only summarizes observed changes and provenance-backed recommendations.",
            "future": [
                "Scheduled overnight jobs",
                "PubMed monitoring",
                "Automatic provider refresh",
            ],
        }

    def _new_experiments(self, experiments: list[dict[str, Any]], start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        return [
            _brief_item(
                title=str(experiment.get("experiment_id") or experiment.get("title") or experiment.get("id")),
                summary="Experiment record was created or extracted during this briefing window.",
                timestamp=_record_time(experiment, "extracted_at", "created_at", "date"),
                priority="medium",
                provenance=[_prov("experiment_extracted", "sqlite", "experiments", experiment_id=experiment.get("id"))],
                related_experiments=[str(experiment.get("id"))],
                route=f"/mobile/experiments/{experiment.get('id')}/workspace",
            )
            for experiment in experiments
            if _in_window(_record_time(experiment, "extracted_at", "created_at", "date"), start, end)
        ][:limit]

    def _updated_experiments(self, experiments: list[dict[str, Any]], start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        items = []
        for experiment in experiments:
            timestamp = _record_time(experiment, "updated_at", "extracted_at")
            if not _in_window(timestamp, start, end):
                continue
            if _record_time(experiment, "date") == timestamp:
                continue
            items.append(
                _brief_item(
                    title=str(experiment.get("experiment_id") or experiment.get("title") or experiment.get("id")),
                    summary="Experiment metadata changed during this briefing window.",
                    timestamp=timestamp,
                    priority="low",
                    provenance=[_prov("experiment_updated", "sqlite", "experiments", experiment_id=experiment.get("id"))],
                    related_experiments=[str(experiment.get("id"))],
                    route=f"/mobile/experiments/{experiment.get('id')}/workspace",
                )
            )
        return items[:limit]

    def _completed_workflows(self, workflows: list[dict[str, Any]], start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        completed = {"Submitted", "Published", "Archived"}
        items = []
        for workflow in workflows:
            history = workflow.get("history") if isinstance(workflow.get("history"), list) else []
            for event in history:
                if not isinstance(event, dict) or event.get("to_stage") not in completed:
                    continue
                timestamp = _parse_datetime(event.get("created_at"))
                if not _in_window(timestamp, start, end):
                    continue
                items.append(
                    _brief_item(
                        title=f"Workflow completed: {workflow.get('subject_id')}",
                        summary=f"Workflow transitioned to {event.get('to_stage')}.",
                        timestamp=timestamp,
                        priority="medium",
                        provenance=[_prov("workflow_transition", "sqlite", "workflow_history", workflow_id=workflow.get("workflow_id"))],
                        related_experiments=[str(workflow.get("subject_id"))],
                        route=f"#/workflows/{workflow.get('workflow_id')}",
                    )
                )
        return items[:limit]

    def _feed_section(self, feed: dict[str, Any], item_type: str, start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        items = []
        for item in feed.get("items") or []:
            if not isinstance(item, dict) or item.get("item_type") != item_type:
                continue
            timestamp = _parse_datetime(item.get("timestamp"))
            if not _in_window(timestamp, start, end):
                continue
            items.append(
                _brief_item(
                    title=str(item.get("title") or item_type),
                    summary=str(item.get("summary") or ""),
                    timestamp=timestamp,
                    priority=str(item.get("priority") or "low"),
                    provenance=list(item.get("provenance") or []),
                    related_experiments=list(item.get("related_experiments") or []),
                    related_resources=list(item.get("related_resources") or []),
                    related_literature=list(item.get("related_literature") or []),
                    suggested_action=str(item.get("suggested_action") or "Review source records."),
                    route=item.get("route"),
                )
            )
        return items[:limit]

    def _new_literature(self, documents: list[dict[str, Any]], start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        return [
            _brief_item(
                title=str(document.get("title") or document.get("id")),
                summary="Literature document was ingested during this briefing window.",
                timestamp=_record_time(document, "updated_at", "created_at", "ingested_at"),
                priority="medium",
                provenance=[_prov("literature_ingested", "sqlite", "documents", document_id=document.get("id"))],
                related_literature=[str(document.get("id"))],
                route="#/literature",
            )
            for document in documents
            if document.get("provider") == "literature"
            and _in_window(_record_time(document, "updated_at", "created_at", "ingested_at"), start, end)
        ][:limit]

    def _knowledge_graph_changes(
        self,
        workspace_id: str,
        documents: list[dict[str, Any]],
        experiments: list[dict[str, Any]],
        assets: list[dict[str, Any]],
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        changed_records = [
            record
            for record in [*documents, *experiments, *assets]
            if _in_window(_record_time(record, "updated_at", "created_at", "ingested_at", "extracted_at", "date"), start, end)
        ]
        if not changed_records:
            return []
        summary = KnowledgeGraphService(settings=self.settings, store=self.store, workspace_id=workspace_id).summary()
        top = ", ".join(str(item.get("entity") or item.get("name")) for item in list(summary.get("top_entities") or [])[:5] if isinstance(item, dict))
        return [
            _brief_item(
                title="Knowledge Graph updated",
                summary=f"{len(changed_records)} indexed record(s) changed. Top connected entities: {top or 'not available'}.",
                timestamp=datetime.now(),
                priority="low",
                provenance=[_prov("knowledge_graph_summary", "knowledge_graph", "dynamic_graph", entity_count=summary.get("entity_count"))],
                route="#/graph",
            )
        ]

    def _protocol_updates(self, start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        items = []
        for protocol in ProtocolService(settings=self.settings, store=self.store).list_protocols():
            timestamp = _record_time(protocol, "updated_at", "created_at")
            if not _in_window(timestamp, start, end):
                continue
            items.append(
                _brief_item(
                    title=str(protocol.get("title") or protocol.get("id")),
                    summary=f"Protocol version {protocol.get('version') or 'unknown'} was updated or detected.",
                    timestamp=timestamp,
                    priority="low",
                    provenance=[_prov("protocol", str(protocol.get("provider") or "sqlite"), "protocols", protocol_id=protocol.get("id"))],
                    route=f"#/protocols/{protocol.get('id')}",
                )
            )
        return items[:limit]

    def _resource_alerts(self, resources: list[dict[str, Any]], start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        items = []
        for resource in resources:
            timestamp = _record_time(resource, "updated_at", "created_at")
            if not _in_window(timestamp, start, end):
                continue
            missing = [
                label
                for field, label in [("lot_number", "lot number"), ("storage_location", "storage location"), ("expiration", "expiration")]
                if not resource.get(field)
            ]
            if not missing:
                continue
            items.append(
                _brief_item(
                    title=f"Resource metadata incomplete: {resource.get('name')}",
                    summary=f"Missing {', '.join(missing)}.",
                    timestamp=timestamp,
                    priority="medium",
                    provenance=[_prov("resource_alert", "sqlite", "resources", resource_id=resource.get("resource_id"))],
                    related_resources=[str(resource.get("resource_id"))],
                    route="#/resources",
                )
            )
        return items[:limit]

    def _suggested_priorities(self, feed: dict[str, Any], start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        priorities = []
        for item in feed.get("items") or []:
            if not isinstance(item, dict):
                continue
            timestamp = _parse_datetime(item.get("timestamp"))
            if not _in_window(timestamp, start, end):
                continue
            if item.get("priority") not in {"critical", "high", "medium"}:
                continue
            priorities.append(
                _brief_item(
                    title=str(item.get("title") or "Priority item"),
                    summary=str(item.get("suggested_action") or item.get("summary") or ""),
                    timestamp=timestamp,
                    priority=str(item.get("priority") or "medium"),
                    provenance=list(item.get("provenance") or []),
                    related_experiments=list(item.get("related_experiments") or []),
                    related_resources=list(item.get("related_resources") or []),
                    related_literature=list(item.get("related_literature") or []),
                    route=item.get("route"),
                )
            )
        return priorities[:limit]

    def _summary(self, total_items: int, sections: dict[str, list[dict[str, Any]]], label: str) -> str:
        if total_items == 0:
            return f"No observed ResearchOS changes were detected for {label}."
        parts = []
        for key, title in [
            ("new_experiments", "new experiment(s)"),
            ("missing_analyses", "missing analysis item(s)"),
            ("new_literature", "new literature item(s)"),
            ("resource_alerts", "resource alert(s)"),
            ("suggested_priorities", "suggested priority item(s)"),
        ]:
            count = len(sections.get(key) or [])
            if count:
                parts.append(f"{count} {title}")
        return f"Morning Brief for {label}: " + (", ".join(parts) if parts else f"{total_items} provenance-backed update(s).")


def _period_bounds(period: str) -> tuple[datetime, datetime, str]:
    # SQLite CURRENT_TIMESTAMP is UTC. Use UTC day bounds so freshly inserted
    # records are not missed in local time zones west of UTC.
    today = datetime.now(UTC).date()
    normalized = period.strip().lower().replace("-", "_")
    if normalized == "yesterday":
        target = today - timedelta(days=1)
        return datetime.combine(target, time.min), datetime.combine(target, time.max), "yesterday"
    if normalized in {"last_week", "week", "7_days"}:
        return datetime.combine(today - timedelta(days=7), time.min), datetime.combine(today, time.max), "the last week"
    return datetime.combine(today, time.min), datetime.combine(today, time.max), "today"


def _brief_item(
    title: str,
    summary: str,
    timestamp: datetime | None,
    priority: str,
    provenance: list[dict[str, Any]],
    *,
    related_experiments: list[str] | None = None,
    related_resources: list[str] | None = None,
    related_literature: list[str] | None = None,
    suggested_action: str | None = None,
    route: Any = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "summary": summary,
        "timestamp": (timestamp or datetime.now()).isoformat(timespec="seconds"),
        "priority": priority if priority in {"critical", "high", "medium", "low"} else "low",
        "related_experiments": related_experiments or [],
        "related_resources": related_resources or [],
        "related_literature": related_literature or [],
        "suggested_action": suggested_action or "Review the linked ResearchOS source records.",
        "provenance": provenance,
        "route": route,
    }


def _prov(fact: str, source: str, provider: str, **extra: Any) -> dict[str, Any]:
    return {"fact": fact, "source": source, "provider": provider, **{key: value for key, value in extra.items() if value is not None}}


def _record_time(record: dict[str, Any], *keys: str) -> datetime | None:
    for key in keys:
        parsed = _parse_datetime(record.get(key))
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in [text, text.replace("Z", "+00:00"), text.replace(" ", "T")]:
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=None)
        except ValueError:
            continue
    try:
        return datetime.combine(date.fromisoformat(text[:10]), time.min)
    except ValueError:
        return None


def _in_window(timestamp: datetime | None, start: datetime, end: datetime) -> bool:
    if timestamp is None:
        return False
    clean = timestamp.replace(tzinfo=None)
    return start <= clean <= end

"""Daily dashboard synthesis for ResearchOS."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from app.ai_providers import AIProvider, AIProviderError, get_ai_provider
from app.config import Settings, get_settings
from app.global_knowledge_graph import KnowledgeGraphService
from app.lab_workspaces import current_workspace
from app.research_copilot import ResearchCopilotService
from app.storage import SQLiteStore


@dataclass
class DashboardService:
    """Generate a cached local-first daily dashboard from ResearchOS records."""

    settings: Settings | None = None
    store: SQLiteStore | None = None
    knowledge_graph: KnowledgeGraphService | None = None
    ai_provider_factory: Callable[[Settings], AIProvider] = get_ai_provider

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.store = self.store or SQLiteStore(settings=self.settings)
        self.knowledge_graph = self.knowledge_graph or KnowledgeGraphService(settings=self.settings, store=self.store)
        self._cache_fingerprint: tuple[int, int, int, int, int] | None = None
        self._cache_payload: dict[str, Any] | None = None

    def refresh(self) -> None:
        """Invalidate the dashboard cache."""

        self._cache_fingerprint = None
        self._cache_payload = None

    def build(self, use_ai: bool = True) -> dict[str, Any]:
        """Build the daily dashboard from existing local evidence."""

        fingerprint = self._fingerprint()
        if self._cache_payload is not None and self._cache_fingerprint == fingerprint:
            cached = deepcopy(self._cache_payload)
            cached["cache"]["cached"] = True
            return cached

        documents = self.store.list_documents()
        experiments = self.store.list_experiments()
        assets = self.store.list_assets(query=None)
        pending_entries = self.store.list_pending_entries()
        papers = [document for document in documents if document.get("provider") == "literature"]
        graph_summary = self.knowledge_graph.summary()
        workspace = current_workspace(self.settings, self.store)
        sections = [
            self._overview(documents, experiments, assets, papers, pending_entries, graph_summary, workspace),
            self._workflow_stages(),
            self._experiments_requiring_attention(experiments, assets),
            self._recent_activity(documents, experiments, assets, pending_entries),
            self._todays_timeline(experiments, assets, documents),
            self._research_copilot_insights(experiments, assets, papers, use_ai),
            self._recent_imports(documents, assets),
            self._pending_analyses(experiments, assets),
            self._recent_literature(papers),
            self._pinned_experiments(experiments),
            self._pinned_papers(papers),
            self._recent_searches(),
            self._quick_actions(),
        ]
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "cache": {"fingerprint": fingerprint, "cached": False},
            "layout": {
                "supports_collapse": True,
                "supports_reorder": True,
                "mobile": {"columns": 1, "priority_sections": ["overview", "quick_actions", "experiments_requiring_attention"]},
            },
            "sections": sorted(sections, key=lambda section: int(section["order"])),
            "assistant_summary": self._assistant_summary(sections, use_ai),
            "workspace": workspace,
        }
        self._cache_fingerprint = fingerprint
        self._cache_payload = payload
        return payload

    def _fingerprint(self) -> tuple[int, int, int, int, int]:
        return (
            len(self.store.list_documents()),
            len(self.store.list_experiments()),
            len(self.store.list_assets(query=None)),
            len(self.store.list_pending_entries()),
            sum(self.store.workflow_stage_counts("experiment").values()),
        )

    def _workflow_stages(self) -> dict[str, Any]:
        counts = self.store.workflow_stage_counts("experiment")
        items = [
            _item(stage, f"{count} experiment(s)", "observed", _prov("experiment_workflow", "sqlite", stage=stage, count=count))
            for stage, count in sorted(counts.items())
        ]
        return _section("workflow_stages", "Experiments by workflow stage", 15, items or [_empty_item("No workflow records", "Extract experiments to populate workflow stages.")])

    def _overview(
        self,
        documents: list[dict[str, Any]],
        experiments: list[dict[str, Any]],
        assets: list[dict[str, Any]],
        papers: list[dict[str, Any]],
        pending_entries: list[dict[str, Any]],
        graph_summary: dict[str, Any],
        workspace: dict[str, Any],
    ) -> dict[str, Any]:
        counts = workspace.get("counts") if isinstance(workspace.get("counts"), dict) else {}
        return _section(
            "overview",
            "Overview",
            10,
            [
                _item("Workspace", str(workspace.get("name") or "ResearchOS workspace"), "observed", _prov("workspace", "sqlite", workspace_id=workspace.get("workspace_id"))),
                _item("Experiments indexed", str(len(experiments)), "observed", _prov("experiments", "sqlite", count=len(experiments))),
                _item("Documents indexed", str(len(documents)), "observed", _prov("documents", "sqlite", count=len(documents))),
                _item("Research assets", str(len(assets)), "observed", _prov("assets", "sqlite", count=len(assets))),
                _item("Papers", str(len(papers)), "observed", _prov("literature", "sqlite", count=len(papers))),
                _item("Knowledge Graph entities", str(graph_summary.get("entity_count", 0)), "observed", _prov("knowledge_graph", "knowledgegraph")),
                _item("Pending drafts", str(len(pending_entries)), "observed", _prov("pending_entries", "sqlite", count=len(pending_entries))),
                _item("Workspace records", f"{counts.get('documents', 0)} documents / {counts.get('assets', 0)} assets", "observed", _prov("workspace_counts", "sqlite", workspace_id=workspace.get("workspace_id"))),
            ],
        )

    def _experiments_requiring_attention(self, experiments: list[dict[str, Any]], assets: list[dict[str, Any]]) -> dict[str, Any]:
        items = []
        assets_by_reference = _assets_by_reference(assets)
        for experiment in experiments:
            gaps = []
            if not experiment.get("conclusions"):
                gaps.append("missing conclusion")
            if not experiment.get("markers"):
                gaps.append("missing markers")
            if not any(_asset_has_statistics(asset) for asset in assets_by_reference.get(str(experiment.get("experiment_id") or ""), []) + assets_by_reference.get(str(experiment.get("id") or ""), [])):
                gaps.append("no linked parsed statistics")
            if gaps:
                items.append(
                    _item(
                        str(experiment.get("experiment_id") or experiment.get("title") or experiment.get("id")),
                        f"Needs attention: {', '.join(gaps)}.",
                        "inferred",
                        _prov("experiment", "dashboard", experiment_id=experiment.get("id")),
                        href=f"#/experiments/{experiment.get('id')}/workspace",
                    )
                )
        if not items:
            items.append(_item("No experiment attention items", "No missing conclusions, marker metadata, or linked-statistics gaps were detected.", "inferred", _prov("experiments", "dashboard")))
        return _section("experiments_requiring_attention", "Experiments requiring attention", 20, items[:8])

    def _recent_activity(
        self,
        documents: list[dict[str, Any]],
        experiments: list[dict[str, Any]],
        assets: list[dict[str, Any]],
        pending_entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        activity = []
        activity.extend(_dated_item("Document indexed", document, document.get("title"), "document", "#/documents") for document in documents[:5])
        activity.extend(_dated_item("Experiment extracted", experiment, experiment.get("experiment_id") or experiment.get("title"), "experiment", f"#/experiments/{experiment.get('id')}/workspace") for experiment in experiments[:5])
        activity.extend(_dated_item("Asset registered", asset, asset.get("title") or asset.get("filename"), "asset", f"#/assets/{asset.get('asset_id')}") for asset in assets[:5])
        activity.extend(_dated_item("Draft updated", entry, entry.get("title"), "pending_entry", f"#/saved-drafts/{entry.get('id')}") for entry in pending_entries[:5])
        items = sorted([item for item in activity if item], key=lambda item: str(item["timestamp"] or ""), reverse=True)[:8]
        return _section("recent_activity", "Recent activity", 30, items or [_empty_item("No recent activity", "Load demo notes or register assets to populate activity.")])

    def _todays_timeline(
        self,
        experiments: list[dict[str, Any]],
        assets: list[dict[str, Any]],
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        today = datetime.now().date().isoformat()
        candidates = []
        candidates.extend(_dated_item("Experiment today", experiment, experiment.get("experiment_id") or experiment.get("title"), "experiment", f"#/experiments/{experiment.get('id')}/workspace") for experiment in experiments)
        candidates.extend(_dated_item("Asset today", asset, asset.get("title") or asset.get("filename"), "asset", f"#/assets/{asset.get('asset_id')}") for asset in assets)
        candidates.extend(_dated_item("Document today", document, document.get("title"), "document", "#/documents") for document in documents)
        items = [item for item in candidates if item and str(item.get("timestamp") or "").startswith(today)]
        return _section("todays_timeline", "Today's timeline", 40, items[:8] or [_empty_item("No events dated today", "No indexed records have today's date.")])

    def _research_copilot_insights(
        self,
        experiments: list[dict[str, Any]],
        assets: list[dict[str, Any]],
        papers: list[dict[str, Any]],
        use_ai: bool,
    ) -> dict[str, Any]:
        if not experiments:
            return _section("research_copilot_insights", "Research Copilot insights", 50, [_empty_item("No Copilot insights yet", "Ingest or extract experiments first.")])
        experiment = experiments[0]
        linked_assets = _assets_for_experiment(experiment, assets)
        workspace = {
            "experiment": experiment,
            "statistics": [asset for asset in linked_assets if _asset_has_statistics(asset)],
            "microscopy": [asset for asset in linked_assets if str(asset.get("provider")) == "microscopy" or str(asset.get("asset_type")) in {"image", "microscopy"}],
            "graphpad": [asset for asset in linked_assets if str(asset.get("provider")) == "graphpad"],
            "spreadsheets": [asset for asset in linked_assets if str(asset.get("asset_type")) == "spreadsheet"],
            "literature": papers[:3],
            "related_experiments": experiments[1:4],
            "compounds": experiment.get("compounds") or [],
            "markers": experiment.get("markers") or [],
            "limitations": ["Dashboard Copilot insight is assembled from existing local records."],
            "conclusions": {
                "observed": [experiment.get("conclusions")] if experiment.get("conclusions") else [],
                "inferred": ["Linked dashboard context is inferred from experiment IDs and provider metadata."],
                "referenced_from_literature": [paper.get("title") for paper in papers[:3] if paper.get("title")],
            },
            "provenance": [
                *_prov("experiment", "sqlite", experiment_id=experiment.get("id")),
                *[record for asset in linked_assets[:3] for record in _prov("asset", "sqlite", asset_id=asset.get("asset_id"))],
            ],
        }
        copilot = ResearchCopilotService(settings=self.settings, ai_provider_factory=self.ai_provider_factory).build(workspace, use_ai=use_ai)
        items = []
        for statement in copilot.get("sections", {}).get("key_findings", [])[:4]:
            items.append(_item(str(statement.get("category") or "insight"), str(statement.get("text") or ""), str(statement.get("category") or "inferred"), statement.get("provenance") or []))
        return _section("research_copilot_insights", "Research Copilot insights", 50, items or [_empty_item("No Copilot findings", "No extracted observations are available yet.")])

    def _recent_imports(self, documents: list[dict[str, Any]], assets: list[dict[str, Any]]) -> dict[str, Any]:
        imports = []
        imports.extend(_dated_item("Imported document", document, document.get("title"), "document", "#/documents") for document in documents[:6])
        imports.extend(_dated_item("Registered asset", asset, asset.get("title") or asset.get("filename"), "asset", f"#/assets/{asset.get('asset_id')}") for asset in assets[:6])
        items = sorted([item for item in imports if item], key=lambda item: str(item["timestamp"] or ""), reverse=True)[:8]
        return _section("recent_imports", "Recent imports", 60, items or [_empty_item("No imports yet", "Import notes, papers, spreadsheets, GraphPad, or images to populate this card.")])

    def _pending_analyses(self, experiments: list[dict[str, Any]], assets: list[dict[str, Any]]) -> dict[str, Any]:
        items = []
        for asset in assets:
            if str(asset.get("asset_type")) in {"spreadsheet", "csv"} and not _asset_has_statistics(asset):
                items.append(_item(str(asset.get("title") or asset.get("filename")), "Spreadsheet is registered but has no parsed statistics.", "inferred", _prov("asset", "sqlite", asset_id=asset.get("asset_id")), href=f"#/assets/{asset.get('asset_id')}"))
        for experiment in experiments:
            if not experiment.get("conclusions"):
                items.append(_item(str(experiment.get("experiment_id") or experiment.get("title")), "Experiment has no extracted conclusion.", "inferred", _prov("experiment", "sqlite", experiment_id=experiment.get("id")), href=f"#/experiments/{experiment.get('id')}/workspace"))
        return _section("pending_analyses", "Pending analyses", 70, items[:8] or [_empty_item("No pending analyses detected", "No obvious missing conclusions or unparsed quantitative assets were detected.")])

    def _recent_literature(self, papers: list[dict[str, Any]]) -> dict[str, Any]:
        items = [_dated_item("Literature", paper, paper.get("title"), "literature", "#/literature") for paper in papers[:6]]
        return _section("recent_literature", "Recent literature", 80, [item for item in items if item] or [_empty_item("No papers imported", "Import papers to add literature context.")])

    def _pinned_experiments(self, experiments: list[dict[str, Any]]) -> dict[str, Any]:
        pinned = [experiment for experiment in experiments if str(experiment.get("notes") or "").lower().find("pinned") >= 0]
        items = [_item(str(experiment.get("experiment_id") or experiment.get("title")), "Pinned experiment.", "observed", _prov("experiment", "sqlite", experiment_id=experiment.get("id")), href=f"#/experiments/{experiment.get('id')}/workspace") for experiment in pinned[:6]]
        return _section("pinned_experiments", "Pinned experiments", 90, items or [_empty_item("No pinned experiments", "Pinned experiment metadata has not been added yet.")])

    def _pinned_papers(self, papers: list[dict[str, Any]]) -> dict[str, Any]:
        pinned = [paper for paper in papers if "pinned" in json.dumps(paper).lower()]
        items = [_item(str(paper.get("title")), "Pinned paper.", "observed", _prov("literature", "sqlite", document_id=paper.get("id")), href="#/literature") for paper in pinned[:6]]
        return _section("pinned_papers", "Pinned papers", 100, items or [_empty_item("No pinned papers", "Pinned paper metadata has not been added yet.")])

    def _recent_searches(self) -> dict[str, Any]:
        return _section("recent_searches", "Recent searches", 110, [_empty_item("No recent searches stored", "Search history is not persisted yet.")])

    def _quick_actions(self) -> dict[str, Any]:
        return _section(
            "quick_actions",
            "Quick actions",
            120,
            [
                _item("New Experiment", "Draft a structured experiment entry.", "suggested", _prov("command", "dashboard"), href="#/new-experiment"),
                _item("Capture Note", "Use dictation or typed notes to generate a draft.", "suggested", _prov("command", "dashboard"), href="#/new-experiment"),
                _item("Import Files", "Scan GraphPad, spreadsheet, image, or paper folders.", "suggested", _prov("command", "dashboard"), href="#/assets"),
                _item("Search", "Open Universal Scientific Search.", "suggested", _prov("command", "dashboard"), href="#/search"),
                _item("Ask Research Copilot", "Ask the assistant using local evidence.", "suggested", _prov("command", "dashboard"), href="#/chat"),
            ],
        )

    def _assistant_summary(self, sections: list[dict[str, Any]], use_ai: bool) -> dict[str, Any]:
        local = "Daily dashboard generated from local ResearchOS records. Review attention items and pending analyses before making scientific claims."
        if not use_ai:
            return {"provider": "local-fallback", "text": local}
        try:
            provider = self.ai_provider_factory(self.settings)
            prompt = (
                "Summarize this ResearchOS daily dashboard using only the JSON below. "
                "Do not invent recommendations. Mention that recommendations are provenance-backed.\n\n"
                f"{json.dumps(sections, default=str)}"
            )
            return {"provider": provider.provider_name, "text": provider.chat(prompt)}
        except AIProviderError as exc:
            return {"provider": "local-fallback", "text": local, "ai_error": str(exc)}


def _section(section_id: str, title: str, order: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": section_id, "title": title, "order": order, "collapsible": True, "items": items}


def _item(title: str, summary: str, category: str, provenance: list[dict[str, Any]], href: str | None = None) -> dict[str, Any]:
    return {"title": title, "summary": summary, "category": category, "href": href, "provenance": provenance or _prov("dashboard", "dashboard")}


def _empty_item(title: str, summary: str) -> dict[str, Any]:
    return _item(title, summary, "inferred", _prov("dashboard", "dashboard"))


def _prov(fact: str, source: str, **extra: Any) -> list[dict[str, Any]]:
    return [{"fact": fact, "source": source, "provider": "ResearchOS", **{key: value for key, value in extra.items() if value is not None}}]


def _dated_item(prefix: str, record: dict[str, Any], title: Any, fact: str, href: str) -> dict[str, Any] | None:
    if not title:
        return None
    timestamp = record.get("updated_at") or record.get("created_at") or record.get("ingested_at") or record.get("date") or record.get("extracted_at")
    return _item(str(title), f"{prefix} · {timestamp or 'no timestamp'}", "observed", _prov(fact, "sqlite", id=record.get("id") or record.get("asset_id")), href=href) | {"timestamp": timestamp}


def _assets_by_reference(assets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for asset in assets:
        reference = str(asset.get("experiment_id") or "")
        if not reference:
            continue
        grouped.setdefault(reference, []).append(asset)
    return grouped


def _assets_for_experiment(experiment: dict[str, Any], assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    references = {str(experiment.get("id") or ""), str(experiment.get("experiment_id") or "")}
    return [asset for asset in assets if str(asset.get("experiment_id") or "") in references]


def _asset_has_statistics(asset: dict[str, Any]) -> bool:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    return bool(isinstance(metadata, dict) and metadata.get("statistics"))

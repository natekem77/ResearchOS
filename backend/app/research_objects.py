"""Universal ResearchOS object linking and reference resolution."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any

from app.authorization import AuthorizationService
from app.config import Settings, get_settings
from app.general_experiments import GeneralExperimentService
from app.global_knowledge_graph import KnowledgeGraphService
from app.lab_chat import ChatAuthorizationError, LabChatService
from app.protocol_hub import ProtocolHubService
from app.storage import SQLiteStore


OBJECT_TYPE_ICONS = {
    "Experiment": "science",
    "Protocol": "account_tree",
    "Protocol Version": "history",
    "Inventory Item": "inventory_2",
    "Compound": "medication",
    "Media": "local_drink",
    "Equipment": "precision_manufacturing",
    "Image": "image",
    "Spreadsheet": "table_chart",
    "GraphPad Analysis": "analytics",
    "Notebook": "edit_note",
    "Notebook Entry": "article",
    "Timeline Event": "timeline",
    "Condition": "schema",
    "Cohort": "groups",
    "Sample": "science",
    "Task": "check_circle",
    "Reminder": "notifications",
    "Conversation": "chat",
    "Chat Message": "forum",
    "Paper": "menu_book",
    "Researcher": "person",
    "Lab": "domain",
    "Publication": "description",
    "Resource": "category",
    "Experiment Design": "event_note",
    "Plate Layout": "grid_on",
    "Purchase": "receipt_long",
    "Vendor": "store",
    "Grant": "account_balance",
    "Custom": "hub",
}


@dataclass
class ResearchObject:
    """Display-ready universal object reference."""

    object_id: str
    object_type: str
    title: str
    subtitle: str = ""
    lab_id: str = "lab:demo"
    owner_user_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    icon: str = "hub"
    search_keywords: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    supported_actions: list[str] = field(default_factory=lambda: ["open", "preview", "copy_reference"])

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reference"] = f"[[{self.object_id}]]"
        return payload


class ObjectResolver:
    """Resolve user-facing reference text to visible ResearchOS objects."""

    def __init__(self, service: "ResearchObjectService") -> None:
        self.service = service

    def resolve(self, user_id: str, reference: str, lab_id: str = "lab:demo") -> dict[str, Any]:
        return self.service.resolve_reference(user_id, reference, lab_id=lab_id)


class ReferenceResolver:
    """Extract and persist object references from rich text, chat, or notes."""

    def __init__(self, service: "ResearchObjectService") -> None:
        self.service = service

    def extract(self, user_id: str, text: str, lab_id: str = "lab:demo") -> list[dict[str, Any]]:
        return self.service.extract_references_from_text(user_id, text, lab_id=lab_id)


class KnowledgeResolver:
    """Object-aware knowledge layer for future AI contexts."""

    def __init__(self, service: "ResearchObjectService") -> None:
        self.service = service

    def context_for_objects(self, user_id: str, object_ids: list[str], lab_id: str = "lab:demo") -> list[dict[str, Any]]:
        return [
            item
            for object_id in object_ids
            if (item := self.service.get_object(user_id, object_id, lab_id=lab_id)) is not None
        ]


class ResearchObjectService:
    """Build a live object index from existing ResearchOS provider metadata."""

    def __init__(self, settings: Settings | None = None, store: SQLiteStore | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or SQLiteStore(settings=self.settings)
        self.authz = AuthorizationService(settings=self.settings)
        self.general = GeneralExperimentService(settings=self.settings)
        self.chat = LabChatService(settings=self.settings)
        self.knowledge_graph = KnowledgeGraphService(settings=self.settings, store=self.store)
        self.protocol_hub = ProtocolHubService(settings=self.settings)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return self.store._connect()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_object_references (
                    reference_id TEXT PRIMARY KEY,
                    source_object_id TEXT NOT NULL,
                    source_object_type TEXT NOT NULL,
                    target_object_id TEXT NOT NULL,
                    target_object_type TEXT NOT NULL,
                    reference_text TEXT NOT NULL,
                    context TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_research_object_refs_source
                    ON research_object_references(source_object_id);
                CREATE INDEX IF NOT EXISTS idx_research_object_refs_target
                    ON research_object_references(target_object_id);
                """
            )

    def list_objects(self, user_id: str, lab_id: str = "lab:demo", object_type: str | None = None, limit: int = 250) -> list[dict[str, Any]]:
        objects = self._visible_objects(user_id, lab_id)
        if object_type:
            normalized = _normalize_type(object_type)
            objects = [item for item in objects if _normalize_type(item.object_type) == normalized]
        return [item.as_dict() for item in sorted(objects, key=lambda item: (item.object_type, item.title.lower()))[:limit]]

    def get_object(self, user_id: str, object_id: str, lab_id: str = "lab:demo") -> dict[str, Any] | None:
        for item in self._visible_objects(user_id, lab_id):
            if item.object_id == object_id:
                payload = item.as_dict()
                payload["backlink_count"] = len(self.backlinks(user_id, object_id, lab_id=lab_id))
                payload["references"] = self.references_from(user_id, object_id, lab_id=lab_id)
                return payload
        return None

    def search(self, user_id: str, query: str, lab_id: str = "lab:demo", limit: int = 12) -> list[dict[str, Any]]:
        parsed = _normalize(query)
        if not parsed:
            return []
        scored: list[tuple[float, ResearchObject]] = []
        for item in self._visible_objects(user_id, lab_id):
            score = _score_object(item, parsed)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1].title.lower()))
        return [obj.as_dict() | {"score": round(score, 3)} for score, obj in scored[:limit]]

    def autocomplete(self, user_id: str, query: str, lab_id: str = "lab:demo", limit: int = 8) -> list[dict[str, Any]]:
        clean = query.strip().lstrip("@").strip("[] ")
        results = self.search(user_id, clean, lab_id=lab_id, limit=limit)
        for result in results:
            result["recent_usage"] = len(self.backlinks(user_id, str(result["object_id"]), lab_id=lab_id))
            result["pinned"] = False
            result["favorited"] = False
        return results

    def resolve_reference(self, user_id: str, reference: str, lab_id: str = "lab:demo") -> dict[str, Any]:
        clean = _clean_reference(reference)
        if not clean:
            return {"reference": reference, "resolved": False, "object": None, "candidates": []}
        exact = self.get_object(user_id, clean, lab_id=lab_id)
        if exact:
            return {"reference": reference, "resolved": True, "object": exact, "candidates": [exact]}
        candidates = self.search(user_id, clean, lab_id=lab_id, limit=5)
        if candidates and float(candidates[0].get("score", 0) or 0) < 55:
            candidates = []
        return {"reference": reference, "resolved": bool(candidates), "object": candidates[0] if candidates else None, "candidates": candidates}

    def extract_references_from_text(self, user_id: str, text: str, lab_id: str = "lab:demo") -> list[dict[str, Any]]:
        seen: set[str] = set()
        references: list[dict[str, Any]] = []
        for raw in _reference_tokens(text):
            key = raw.lower()
            if key in seen:
                continue
            seen.add(key)
            resolved = self.resolve_reference(user_id, raw, lab_id=lab_id)
            references.append(resolved | {"context": _context_for_reference(text, raw)})
        return references

    def create_reference(
        self,
        user_id: str,
        source_object_id: str,
        source_object_type: str,
        target_object_id: str,
        reference_text: str | None = None,
        context: str | None = None,
        lab_id: str = "lab:demo",
    ) -> dict[str, Any]:
        source = self.get_object(user_id, source_object_id, lab_id=lab_id)
        target = self.get_object(user_id, target_object_id, lab_id=lab_id)
        if source is None or target is None:
            raise PermissionError("Source or target object is not visible.")
        reference_id = f"reference:{uuid.uuid4().hex[:16]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_object_references
                    (reference_id, source_object_id, source_object_type, target_object_id,
                     target_object_type, reference_text, context, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reference_id,
                    source_object_id,
                    source_object_type,
                    target_object_id,
                    str(target["object_type"]),
                    reference_text or str(target["title"]),
                    context,
                    user_id,
                ),
            )
            row = connection.execute("SELECT * FROM research_object_references WHERE reference_id = ?", (reference_id,)).fetchone()
        assert row is not None
        return _decode_row(row)

    def backlinks(self, user_id: str, object_id: str, lab_id: str = "lab:demo") -> list[dict[str, Any]]:
        visible = {item.object_id: item for item in self._visible_objects(user_id, lab_id)}
        if object_id not in visible:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM research_object_references WHERE target_object_id = ? ORDER BY created_at DESC",
                (object_id,),
            ).fetchall()
        backlinks = []
        for row in rows:
            record = _decode_row(row)
            source = visible.get(str(record["source_object_id"]))
            if source:
                backlinks.append(record | {"source": source.as_dict()})
        backlinks.extend(self._implicit_backlinks(user_id, object_id, visible, lab_id))
        return backlinks

    def references_from(self, user_id: str, object_id: str, lab_id: str = "lab:demo") -> list[dict[str, Any]]:
        visible = {item.object_id: item for item in self._visible_objects(user_id, lab_id)}
        if object_id not in visible:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM research_object_references WHERE source_object_id = ? ORDER BY created_at DESC",
                (object_id,),
            ).fetchall()
        references = []
        for row in rows:
            record = _decode_row(row)
            target = visible.get(str(record["target_object_id"]))
            if target:
                references.append(record | {"target": target.as_dict()})
        return references

    def sync_text_references(
        self,
        user_id: str,
        source_object_id: str,
        source_object_type: str,
        text: str,
        lab_id: str = "lab:demo",
    ) -> list[dict[str, Any]]:
        source = self.get_object(user_id, source_object_id, lab_id=lab_id)
        if source is None:
            return []
        resolved = self.extract_references_from_text(user_id, text, lab_id=lab_id)
        with self._connect() as connection:
            connection.execute("DELETE FROM research_object_references WHERE source_object_id = ?", (source_object_id,))
        created = []
        for item in resolved:
            target = item.get("object")
            if not item.get("resolved") or not isinstance(target, dict):
                continue
            created.append(
                self.create_reference(
                    user_id=user_id,
                    source_object_id=source_object_id,
                    source_object_type=source_object_type,
                    target_object_id=str(target["object_id"]),
                    reference_text=str(item["reference"]),
                    context=str(item.get("context") or ""),
                    lab_id=lab_id,
                )
            )
        return created

    def hover_card(self, user_id: str, object_id: str, lab_id: str = "lab:demo") -> dict[str, Any] | None:
        obj = self.get_object(user_id, object_id, lab_id=lab_id)
        if obj is None:
            return None
        backlinks = self.backlinks(user_id, object_id, lab_id=lab_id)
        return {
            "object": obj,
            "summary": _object_summary(obj, backlinks),
            "quick_actions": ["open", "preview", "copy_reference", "open_related_objects"],
            "backlink_count": len(backlinks),
            "backlinks_preview": backlinks[:5],
        }

    def _visible_objects(self, user_id: str, lab_id: str) -> list[ResearchObject]:
        objects: list[ResearchObject] = []
        objects.extend(self._workspace_objects(user_id, lab_id))
        objects.extend(self._user_objects(lab_id))
        objects.extend(self._notebook_objects(user_id, lab_id))
        objects.extend(self._experiment_notebook_document_objects(user_id, lab_id))
        objects.extend(self._protocol_notebook_document_objects(lab_id))
        objects.extend(self._experiment_objects(user_id, lab_id))
        objects.extend(self._general_experiment_objects(user_id, lab_id))
        objects.extend(self._protocol_objects(lab_id))
        objects.extend(self._asset_objects(lab_id))
        objects.extend(self._resource_objects(lab_id))
        objects.extend(self._inventory_objects(lab_id))
        objects.extend(self._design_objects(lab_id))
        objects.extend(self._chat_objects(user_id, lab_id))
        objects.extend(self._paper_objects(lab_id))
        objects.extend(self._knowledge_entity_objects(lab_id))
        deduped: dict[str, ResearchObject] = {}
        for item in objects:
            deduped[item.object_id] = item
        return list(deduped.values())

    def _workspace_objects(self, user_id: str, lab_id: str) -> list[ResearchObject]:
        del user_id
        with self._connect() as connection:
            rows = _select_if_exists(connection, "lab_workspaces", "SELECT * FROM lab_workspaces WHERE workspace_id = ?", (lab_id,))
        return [
            _object(
                object_id=row["workspace_id"],
                object_type="Lab",
                title=row["name"],
                subtitle=row.get("institution") or "Lab workspace",
                lab_id=row["workspace_id"],
                owner=row.get("owner_user_id") or row.get("created_by"),
                created_at=row.get("created_at"),
                metadata=row,
            )
            for row in rows
        ]

    def _user_objects(self, lab_id: str) -> list[ResearchObject]:
        with self._connect() as connection:
            rows = _select_if_exists(
                connection,
                "users",
                """
                SELECT users.*
                FROM users
                LEFT JOIN workspace_memberships wm ON wm.user_id = users.user_id
                WHERE wm.workspace_id = ? OR wm.workspace_id IS NULL
                """,
                (lab_id,),
            )
        return [
            _object(
                object_id=row["user_id"],
                object_type="Researcher",
                title=row["display_name"],
                subtitle=row.get("email") or row.get("role") or "Researcher",
                lab_id=lab_id,
                created_at=row.get("created_at"),
                updated_at=row.get("last_login"),
                metadata=row,
            )
            for row in rows
        ]

    def _notebook_objects(self, user_id: str, lab_id: str) -> list[ResearchObject]:
        objects: list[ResearchObject] = []
        for notebook in self.authz.list_visible_notebooks(user_id, lab_id):
            objects.append(
                _object(
                    object_id=notebook["notebook_id"],
                    object_type="Notebook",
                    title=notebook["title"],
                    subtitle=f"{notebook['visibility']} notebook",
                    lab_id=notebook["lab_id"],
                    owner=notebook.get("owner_user_id"),
                    created_at=notebook.get("created_at"),
                    updated_at=notebook.get("updated_at"),
                    metadata=notebook,
                )
            )
            try:
                entries = self.authz.notebook_entries(user_id, str(notebook["notebook_id"]))
            except PermissionError:
                entries = []
            for entry in entries:
                objects.append(
                    _object(
                        object_id=entry["entry_id"],
                        object_type="Notebook Entry",
                        title=entry["title"],
                        subtitle=notebook["title"],
                        lab_id=notebook["lab_id"],
                        owner=notebook.get("owner_user_id"),
                        created_at=entry.get("created_at"),
                        updated_at=entry.get("updated_at"),
                        metadata=entry | {"notebook_id": notebook["notebook_id"]},
                        keywords=[entry.get("body", "")],
                    )
                )
        return objects

    def _experiment_notebook_document_objects(self, user_id: str, lab_id: str) -> list[ResearchObject]:
        with self._connect() as connection:
            rows = _select_if_exists(connection, "experiment_notebook_documents", "SELECT * FROM experiment_notebook_documents")
        objects: list[ResearchObject] = []
        for row in rows:
            experiment_id = str(row.get("experiment_id") or "")
            if experiment_id and not self.general.can_access(user_id, experiment_id, "view"):
                continue
            objects.append(
                _object(
                    object_id=row["document_id"],
                    object_type="Notebook Entry",
                    title=row["title"],
                    subtitle=f"Experiment notebook · {experiment_id}",
                    lab_id=lab_id,
                    owner=row.get("updated_by"),
                    created_at=row.get("created_at"),
                    updated_at=row.get("updated_at"),
                    metadata=row,
                    keywords=[row.get("content", ""), row.get("plain_text_cache", "")],
                )
            )
        return objects

    def _protocol_notebook_document_objects(self, lab_id: str) -> list[ResearchObject]:
        with self._connect() as connection:
            rows = _select_if_exists(connection, "protocol_notebook_documents", "SELECT * FROM protocol_notebook_documents")
        return [
            _object(
                object_id=row["document_id"],
                object_type="Notebook Entry",
                title=row["title"],
                subtitle=f"Protocol notebook · {row.get('protocol_version_id')}",
                lab_id=lab_id,
                owner=row.get("updated_by"),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
                metadata=row,
                keywords=[row.get("content", ""), row.get("plain_text_cache", "")],
            )
            for row in rows
        ]

    def _experiment_objects(self, user_id: str, lab_id: str) -> list[ResearchObject]:
        del user_id
        objects = []
        for experiment in self.store.list_experiments():
            if lab_id and experiment.get("workspace_id") not in {None, "", lab_id, "workspace:demo-lab"}:
                continue
            title = str(experiment.get("title") or experiment.get("experiment_id") or experiment.get("id"))
            objects.append(
                _object(
                    object_id=str(experiment["id"]),
                    object_type="Experiment",
                    title=title,
                    subtitle=str(experiment.get("experiment_id") or experiment.get("source_provider") or "Experiment"),
                    lab_id=str(experiment.get("workspace_id") or lab_id),
                    owner=experiment.get("owner_user_id") or experiment.get("created_by"),
                    created_at=experiment.get("extracted_at"),
                    updated_at=experiment.get("extracted_at"),
                    metadata=experiment,
                    keywords=_flatten_values(experiment),
                )
            )
        return objects

    def _general_experiment_objects(self, user_id: str, lab_id: str) -> list[ResearchObject]:
        with self._connect() as connection:
            rows = _select_if_exists(connection, "experiment_workspaces", "SELECT * FROM experiment_workspaces WHERE lab_id = ?", (lab_id,))
            cohorts = _select_if_exists(connection, "experiment_cohorts", "SELECT * FROM experiment_cohorts")
            conditions = _select_if_exists(connection, "experiment_conditions", "SELECT * FROM experiment_conditions")
            events = _select_if_exists(connection, "experiment_events_general", "SELECT * FROM experiment_events_general")
        objects: list[ResearchObject] = []
        visible_experiments: set[str] = set()
        for row in rows:
            experiment_id = str(row["experiment_id"])
            if not self.general.can_access(user_id, experiment_id, "view"):
                continue
            visible_experiments.add(experiment_id)
            objects.append(
                _object(
                    object_id=experiment_id,
                    object_type="Experiment",
                    title=row["title"],
                    subtitle=row.get("biological_system") or row.get("status") or "Experiment workspace",
                    lab_id=row.get("lab_id") or lab_id,
                    owner=row.get("owner_user_id"),
                    created_at=row.get("created_at"),
                    updated_at=row.get("updated_at"),
                    metadata=row,
                    keywords=_flatten_values(row),
                )
            )
        for row in cohorts:
            if row.get("experiment_id") in visible_experiments:
                objects.append(_object(row["cohort_id"], "Cohort", row["name"], row.get("description") or row["experiment_id"], lab_id, metadata=row))
        for row in conditions:
            if row.get("experiment_id") in visible_experiments:
                objects.append(_object(row["condition_id"], "Condition", row["name"], row.get("condition_type") or row["experiment_id"], lab_id, metadata=row))
        for row in events:
            if row.get("experiment_id") in visible_experiments:
                objects.append(_object(row["event_id"], "Timeline Event", row["title"], row.get("event_type") or row["experiment_id"], lab_id, metadata=row))
        return objects

    def _protocol_objects(self, lab_id: str) -> list[ResearchObject]:
        objects: list[ResearchObject] = []
        for protocol in self.protocol_hub.list_protocols():
            if protocol.get("lab_id") not in {None, "", lab_id}:
                continue
            objects.append(
                _object(
                    object_id=protocol["protocol_id"],
                    object_type="Protocol",
                    title=protocol["title"],
                    subtitle=protocol.get("short_name") or protocol.get("category") or "Protocol",
                    lab_id=protocol.get("lab_id") or lab_id,
                    owner=protocol.get("owner_user_id"),
                    created_at=protocol.get("created_at"),
                    updated_at=protocol.get("updated_at"),
                    metadata=protocol,
                    keywords=_flatten_values(protocol),
                )
            )
            for version in protocol.get("versions", []):
                objects.append(
                    _object(
                        object_id=version["protocol_version_id"],
                        object_type="Protocol Version",
                        title=f"{protocol['title']} {version.get('version_label') or version.get('version_number')}",
                        subtitle=version.get("summary_of_changes") or "Protocol version",
                        lab_id=protocol.get("lab_id") or lab_id,
                        owner=version.get("created_by"),
                        created_at=version.get("created_at"),
                        updated_at=version.get("approved_at"),
                        metadata=version | {"protocol_id": protocol["protocol_id"]},
                    )
                )
                for material in self.protocol_hub.materials(str(version["protocol_version_id"])):
                    material_type = _resource_object_type(str(material.get("name") or ""), "Resource")
                    objects.append(
                        _object(
                            object_id=str(material["material_id"]),
                            object_type=material_type,
                            title=str(material["name"]),
                            subtitle=f"Protocol material · {protocol['title']}",
                            lab_id=protocol.get("lab_id") or lab_id,
                            metadata=material | {"protocol_id": protocol["protocol_id"]},
                        )
                    )
                for medium in self.protocol_hub.media(str(version["protocol_version_id"])):
                    objects.append(
                        _object(
                            object_id=str(medium["media_id"]),
                            object_type="Media",
                            title=str(medium["recipe"]),
                            subtitle=f"Protocol media · {protocol['title']}",
                            lab_id=protocol.get("lab_id") or lab_id,
                            metadata=medium | {"protocol_id": protocol["protocol_id"]},
                        )
                    )
        return objects

    def _asset_objects(self, lab_id: str) -> list[ResearchObject]:
        objects = []
        for asset in self.store.list_assets(query=None):
            if lab_id and asset.get("workspace_id") not in {None, "", lab_id, "workspace:demo-lab"}:
                continue
            object_type = _asset_object_type(str(asset.get("asset_type") or ""), str(asset.get("provider") or ""))
            objects.append(
                _object(
                    object_id=str(asset["asset_id"]),
                    object_type=object_type,
                    title=str(asset.get("title") or asset.get("filename") or asset["asset_id"]),
                    subtitle=f"{asset.get('provider') or 'asset'} · {asset.get('filename') or ''}",
                    lab_id=str(asset.get("workspace_id") or lab_id),
                    owner=asset.get("owner_user_id") or asset.get("created_by"),
                    created_at=asset.get("created_at"),
                    updated_at=asset.get("updated_at"),
                    metadata=asset,
                    keywords=_flatten_values(asset),
                )
            )
        return objects

    def _resource_objects(self, lab_id: str) -> list[ResearchObject]:
        objects = []
        for resource in self.store.list_resources():
            if lab_id and resource.get("workspace_id") not in {None, "", lab_id, "workspace:demo-lab"}:
                continue
            objects.append(
                _object(
                    object_id=str(resource["resource_id"]),
                    object_type=_resource_object_type(str(resource.get("name") or ""), str(resource.get("resource_type") or "Resource")),
                    title=str(resource.get("name") or resource["resource_id"]),
                    subtitle=str(resource.get("vendor") or resource.get("resource_type") or "Resource"),
                    lab_id=str(resource.get("workspace_id") or lab_id),
                    owner=resource.get("owner_user_id") or resource.get("created_by"),
                    created_at=resource.get("created_at"),
                    updated_at=resource.get("updated_at"),
                    metadata=resource,
                    keywords=_flatten_values(resource),
                )
            )
        return objects

    def _inventory_objects(self, lab_id: str) -> list[ResearchObject]:
        objects = []
        for item in self.store.list_inventory_items():
            if lab_id and item.get("workspace_id") not in {None, "", lab_id, "workspace:demo-lab"}:
                continue
            objects.append(
                _object(
                    object_id=str(item["item_id"]),
                    object_type="Inventory Item",
                    title=str(item.get("name") or item["item_id"]),
                    subtitle=" · ".join(str(value) for value in [item.get("vendor"), item.get("catalog_number"), item.get("storage_location")] if value),
                    lab_id=str(item.get("workspace_id") or lab_id),
                    owner=item.get("owner_user_id") or item.get("created_by"),
                    created_at=item.get("created_at"),
                    updated_at=item.get("updated_at"),
                    metadata=item,
                    keywords=_flatten_values(item),
                )
            )
        for purchase in self.store.list_purchase_records():
            objects.append(_object(str(purchase["purchase_id"]), "Purchase", str(purchase["item_name"]), str(purchase.get("vendor") or "Purchase"), lab_id, metadata=purchase, keywords=_flatten_values(purchase)))
        return objects

    def _design_objects(self, lab_id: str) -> list[ResearchObject]:
        objects = []
        with self._connect() as connection:
            designs = _select_if_exists(connection, "experiment_designs", "SELECT * FROM experiment_designs")
            layouts = _select_if_exists(connection, "plate_layouts", "SELECT * FROM plate_layouts")
            reminders = _select_if_exists(connection, "design_events", "SELECT * FROM design_events WHERE reminder_enabled = 1 OR alert_enabled = 1")
        for design in designs:
            if lab_id and design.get("workspace_id") not in {None, "", lab_id, "workspace:demo-lab"}:
                continue
            objects.append(_object(design["design_id"], "Experiment Design", design["title"], design.get("experiment_type") or "Design", lab_id, owner=design.get("owner_user_id"), metadata=design, keywords=_flatten_values(design)))
        for layout in layouts:
            objects.append(_object(layout["layout_id"], "Plate Layout", layout["title"], layout.get("format") or "Layout", lab_id, owner=layout.get("owner_user_id"), metadata=layout))
        for reminder in reminders:
            objects.append(_object(reminder["event_id"], "Reminder", reminder["title"], reminder.get("day") or reminder.get("due_date") or "Design reminder", lab_id, metadata=reminder))
        return objects

    def _chat_objects(self, user_id: str, lab_id: str) -> list[ResearchObject]:
        objects: list[ResearchObject] = []
        try:
            conversations = self.chat.list_conversations(user_id, lab_id)
        except Exception:
            conversations = []
        for conversation in conversations:
            objects.append(
                _object(
                    object_id=conversation["conversation_id"],
                    object_type="Conversation",
                    title=conversation["name"],
                    subtitle=conversation.get("conversation_type") or "Conversation",
                    lab_id=conversation.get("lab_id") or lab_id,
                    owner=conversation.get("created_by"),
                    created_at=conversation.get("created_at"),
                    updated_at=conversation.get("archived_at"),
                    metadata=conversation,
                    keywords=_flatten_values(conversation),
                )
            )
            try:
                messages = self.chat.list_messages(user_id, str(conversation["conversation_id"]), limit=25).get("messages", [])
            except (ChatAuthorizationError, PermissionError):
                messages = []
            for message in messages:
                body = str(message.get("body") or "")
                title = body[:60] if body else "Chat message"
                objects.append(
                    _object(
                        object_id=str(message["message_id"]),
                        object_type="Chat Message",
                        title=title,
                        subtitle=str(conversation["name"]),
                        lab_id=conversation.get("lab_id") or lab_id,
                        owner=message.get("sender_user_id"),
                        created_at=message.get("created_at"),
                        updated_at=message.get("edited_at"),
                        metadata={"conversation_id": conversation["conversation_id"]},
                        keywords=[body],
                    )
                )
        return objects

    def _paper_objects(self, lab_id: str) -> list[ResearchObject]:
        objects = []
        for document in self.store.list_documents():
            provider = str(document.get("provider") or "")
            if provider != "literature":
                continue
            if lab_id and document.get("workspace_id") not in {None, "", lab_id, "workspace:demo-lab"}:
                continue
            objects.append(_object(str(document["id"]), "Paper", str(document["title"]), provider, lab_id, metadata=document, keywords=_flatten_values(document)))
        return objects

    def _knowledge_entity_objects(self, lab_id: str) -> list[ResearchObject]:
        del lab_id
        graph = self.knowledge_graph.get_graph()
        objects = []
        for entity in graph.entities.values():
            object_type = _entity_object_type(entity.entity_type)
            objects.append(
                _object(
                    object_id=f"entity:{entity.name}",
                    object_type=object_type,
                    title=entity.name,
                    subtitle=f"{entity.entity_type} · {len(entity.relationships)} references",
                    lab_id="lab:demo",
                    metadata={"entity_type": entity.entity_type, "reference_count": len(entity.relationships), "variants": list(entity.variants.keys())},
                    keywords=[entity.name, entity.entity_type, *entity.variants.keys()],
                )
            )
        return objects

    def _implicit_backlinks(self, user_id: str, object_id: str, visible: dict[str, ResearchObject], lab_id: str) -> list[dict[str, Any]]:
        target = visible.get(object_id)
        if target is None:
            return []
        title = _normalize(target.title)
        if not title:
            return []
        backlinks: list[dict[str, Any]] = []
        for source in visible.values():
            if source.object_id == object_id:
                continue
            text = _normalize(" ".join([source.title, source.subtitle, *source.search_keywords, json.dumps(source.metadata, default=str)]))
            if title and title in text:
                backlinks.append(
                    {
                        "reference_id": f"implicit:{source.object_id}:{object_id}",
                        "source_object_id": source.object_id,
                        "source_object_type": source.object_type,
                        "target_object_id": object_id,
                        "target_object_type": target.object_type,
                        "reference_text": target.title,
                        "context": "Implicit title/metadata co-occurrence.",
                        "source": source.as_dict(),
                        "implicit": True,
                    }
                )
        return backlinks[:25]


def _object(
    object_id: str,
    object_type: str,
    title: str,
    subtitle: str = "",
    lab_id: str = "lab:demo",
    owner: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    metadata: dict[str, Any] | None = None,
    keywords: list[Any] | None = None,
) -> ResearchObject:
    return ResearchObject(
        object_id=str(object_id),
        object_type=object_type,
        title=str(title),
        subtitle=str(subtitle or ""),
        lab_id=str(lab_id or "lab:demo"),
        owner_user_id=owner,
        created_at=created_at,
        updated_at=updated_at,
        icon=OBJECT_TYPE_ICONS.get(object_type, "hub"),
        search_keywords=[str(item) for item in keywords or [] if item is not None and str(item).strip()],
        metadata=metadata or {},
    )


def _reference_tokens(text: str) -> list[str]:
    bracketed = re.findall(r"\[\[([^\]]+)\]\]", text or "")
    at_refs = re.findall(
        r"(?<!\w)@([A-Za-z0-9][A-Za-z0-9_.:+#/-]*(?:\s+(?:[A-Z][A-Za-z0-9_.:+#/-]*|v?\d+(?:\.\d+)*)){0,4})",
        text or "",
    )
    return [*_dedupe(bracketed), *_dedupe(at_refs)]


def _clean_reference(reference: str) -> str:
    clean = reference.strip()
    if clean.startswith("[[") and clean.endswith("]]"):
        clean = clean[2:-2]
    if clean.startswith("@"):
        clean = clean[1:]
    return clean.strip()


def _context_for_reference(text: str, reference: str, radius: int = 80) -> str:
    raw = reference if reference in text else f"@{reference}"
    index = text.find(raw)
    if index < 0:
        raw = f"[[{reference}]]"
        index = text.find(raw)
    if index < 0:
        return ""
    start = max(0, index - radius)
    end = min(len(text), index + len(raw) + radius)
    return text[start:end].strip()


def _score_object(item: ResearchObject, query: str) -> float:
    haystack = _normalize(" ".join([item.object_id, item.title, item.subtitle, item.object_type, *item.search_keywords, json.dumps(item.metadata, default=str)]))
    title = _normalize(item.title)
    object_id = _normalize(item.object_id)
    score = 0.0
    if query == object_id:
        score += 180
    if query == title:
        score += 160
    elif title.startswith(query):
        score += 120
    elif query in title:
        score += 90
    elif query in haystack:
        score += 55
    else:
        ratio = SequenceMatcher(None, query, title).ratio()
        if ratio >= 0.62:
            score += ratio * 40
    score += {"Experiment": 15, "Protocol": 14, "Inventory Item": 12, "Resource": 11, "Paper": 9, "Notebook": 8}.get(item.object_type, 0)
    return score


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().strip())


def _normalize_type(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    for key, value in list(payload.items()):
        if key.endswith("_json") and isinstance(value, str):
            try:
                payload[key.removesuffix("_json")] = json.loads(value)
            except json.JSONDecodeError:
                payload[key.removesuffix("_json")] = value
    return payload


def _select_if_exists(connection: sqlite3.Connection, table: str, sql: str, values: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    exists = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)).fetchone()
    if not exists:
        return []
    return [_decode_row(row) for row in connection.execute(sql, values).fetchall()]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    results = []
    for item in items:
        clean = item.strip(" ,.;:()")
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            results.append(clean)
    return results


def _flatten_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        flattened: list[str] = []
        for item in value.values():
            flattened.extend(_flatten_values(item))
        return flattened
    if isinstance(value, list):
        flattened = []
        for item in value:
            flattened.extend(_flatten_values(item))
        return flattened
    return [str(value)]


def _asset_object_type(asset_type: str, provider: str) -> str:
    if provider == "graphpad" or asset_type == "graphpad":
        return "GraphPad Analysis"
    if asset_type in {"spreadsheet", "csv"}:
        return "Spreadsheet"
    if asset_type in {"image", "microscopy"}:
        return "Image"
    if asset_type == "literature":
        return "Paper"
    return "Custom"


def _resource_object_type(name: str, resource_type: str) -> str:
    normalized = _normalize_type(resource_type)
    mapping = {
        "compound": "Compound",
        "small_molecule": "Compound",
        "media": "Media",
        "equipment": "Equipment",
        "antibody": "Resource",
        "marker": "Resource",
        "gene": "Resource",
        "protein": "Resource",
    }
    if normalized in mapping:
        return mapping[normalized]
    if re.fullmatch(r"[A-Z0-9-]{2,12}", name.strip()):
        return "Compound"
    return "Resource"


def _entity_object_type(entity_type: str) -> str:
    mapping = {
        "compound": "Compound",
        "treatment": "Compound",
        "marker": "Resource",
        "gene": "Resource",
        "protein": "Resource",
        "cell_line": "Sample",
        "organoid_batch": "Sample",
    }
    return mapping.get(_normalize_type(entity_type), "Custom")


def _object_summary(obj: dict[str, Any], backlinks: list[dict[str, Any]]) -> str:
    title = str(obj.get("title") or "Object")
    object_type = str(obj.get("object_type") or "Object")
    count = len(backlinks)
    if count:
        return f"{object_type} {title} is referenced by {count} visible ResearchOS objects."
    return f"{object_type} {title} is available as a live ResearchOS reference."

"""Protocol intelligence for ResearchOS.

Protocols are derived from existing ResearchOS documents and assets. This keeps
the MVP read-only: ResearchOS can detect, compare, summarize, and link protocol
records, but it never edits source protocol documents automatically.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings, get_settings
from app.storage import SQLiteStore


@dataclass(frozen=True)
class Protocol:
    """A first-class protocol object derived from documents/assets."""

    id: str
    title: str
    version: str
    source_document_id: str | None
    provider: str
    content: str
    created_at: str | None = None
    updated_at: str | None = None
    source_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ProtocolService:
    """Build protocol workspaces, histories, metrics, and comparisons."""

    def __init__(self, settings: Settings | None = None, store: SQLiteStore | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or SQLiteStore(settings=self.settings)

    def list_protocols(self) -> list[dict[str, Any]]:
        """Return all protocol objects as API dictionaries."""

        protocols = self._protocols()
        return [self._protocol_payload(protocol, include_content=False) for protocol in protocols]

    def get_protocol(self, protocol_id: str) -> dict[str, Any] | None:
        """Return a full protocol workspace."""

        protocol = self._find_protocol(protocol_id)
        if protocol is None:
            return None
        history = self.history(protocol.id)
        experiments = self._linked_experiments(protocol)
        literature = self._related_literature(protocol)
        statistics = self._linked_statistics(experiments)
        usage = self._usage_stats(protocol, experiments)
        success = self._success_metrics(experiments)
        return self._protocol_payload(protocol, include_content=True) | {
            "history": history,
            "timeline": self._timeline(protocol, experiments, statistics),
            "experiments": experiments,
            "related_literature": literature,
            "statistics": statistics,
            "usage_statistics": usage,
            "success_metrics": success,
            "research_copilot": self._copilot(protocol, experiments, literature, statistics, success),
        }

    def history(self, protocol_id: str) -> list[dict[str, Any]]:
        """Return every known version in the same protocol family."""

        protocol = self._find_protocol(protocol_id)
        if protocol is None:
            return []
        family = _protocol_family(protocol.title)
        versions = [item for item in self._protocols() if _protocol_family(item.title) == family]
        versions.sort(key=lambda item: (_version_sort_key(item.version), str(item.updated_at or "")))
        return [self._protocol_payload(item, include_content=False) for item in versions]

    def compare(self, protocol_id: str, other_id: str) -> dict[str, Any] | None:
        """Compare two protocol versions and detect content changes."""

        left = self._find_protocol(protocol_id)
        right = self._find_protocol(other_id)
        if left is None or right is None:
            return None
        left_lines = left.content.splitlines()
        right_lines = right.content.splitlines()
        diff = list(difflib.unified_diff(left_lines, right_lines, fromfile=left.title, tofile=right.title, lineterm=""))
        added = [line[1:] for line in diff if line.startswith("+") and not line.startswith("+++")]
        removed = [line[1:] for line in diff if line.startswith("-") and not line.startswith("---")]
        return {
            "left": self._protocol_payload(left, include_content=False),
            "right": self._protocol_payload(right, include_content=False),
            "summary": {
                "added_count": len(added),
                "removed_count": len(removed),
                "changed": bool(added or removed),
                "interpretation": _change_interpretation(added, removed),
            },
            "changes": {
                "added": added[:50],
                "removed": removed[:50],
                "diff": diff[:120],
            },
        }

    def _protocols(self) -> list[Protocol]:
        protocols: list[Protocol] = []
        for document in self.store.get_all_research_documents():
            text = f"{document.title}\n{document.content}"
            metadata = document.metadata if isinstance(document.metadata, dict) else {}
            if "protocol" not in text.lower() and str(metadata.get("document_type", "")).lower() != "protocol":
                continue
            version = _detect_version(document.title, document.content)
            protocols.append(
                Protocol(
                    id=_protocol_id(document.id, document.title, version),
                    title=document.title,
                    version=version,
                    source_document_id=document.id,
                    provider=document.provider,
                    content=document.content,
                    created_at=document.created_at,
                    updated_at=document.updated_at,
                    source_path=document.source_path,
                    metadata=metadata,
                )
            )

        for asset in self.store.list_assets(asset_type="protocol"):
            title = str(asset.get("title") or asset.get("filename") or asset.get("asset_id"))
            content = str((asset.get("metadata") or {}).get("content") or asset.get("path") or title)
            version = _detect_version(title, content)
            protocols.append(
                Protocol(
                    id=_protocol_id(str(asset.get("asset_id")), title, version),
                    title=title,
                    version=version,
                    source_document_id=None,
                    provider=str(asset.get("provider") or "asset"),
                    content=content,
                    created_at=asset.get("created_at"),
                    updated_at=asset.get("updated_at"),
                    source_path=asset.get("path"),
                    metadata=asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {},
                )
            )
        protocols.sort(key=lambda item: (str(item.updated_at or ""), item.title), reverse=True)
        return protocols

    def _find_protocol(self, protocol_id: str) -> Protocol | None:
        for protocol in self._protocols():
            if protocol.id == protocol_id or protocol.source_document_id == protocol_id:
                return protocol
        return None

    def _protocol_payload(self, protocol: Protocol, include_content: bool) -> dict[str, Any]:
        experiments = self._linked_experiments(protocol)
        usage = self._usage_stats(protocol, experiments)
        success = self._success_metrics(experiments)
        payload = {
            "id": protocol.id,
            "title": protocol.title,
            "version": protocol.version,
            "family": _protocol_family(protocol.title),
            "provider": protocol.provider,
            "source_document_id": protocol.source_document_id,
            "source_path": protocol.source_path,
            "created_at": protocol.created_at,
            "updated_at": protocol.updated_at,
            "usage_statistics": usage,
            "success_metrics": success,
            "linked_experiment_count": len(experiments),
        }
        if include_content:
            payload["content"] = protocol.content
            payload["metadata"] = protocol.metadata
        return payload

    def _linked_experiments(self, protocol: Protocol) -> list[dict[str, Any]]:
        protocol_terms = _important_terms(f"{protocol.title} {protocol.content}")
        linked = []
        for experiment in self.store.list_experiments():
            haystack = " ".join(
                str(value)
                for value in [
                    experiment.get("title"),
                    experiment.get("experiment_id"),
                    experiment.get("notes"),
                    experiment.get("conclusions"),
                    experiment.get("source_document_id"),
                    *_as_list(experiment.get("compounds")),
                    *_as_list(experiment.get("treatments")),
                    *_as_list(experiment.get("markers")),
                    *_as_list(experiment.get("imaging_methods")),
                ]
                if value
            ).lower()
            overlap = sorted(term for term in protocol_terms if term in haystack)
            if protocol.source_document_id and experiment.get("source_document_id") == protocol.source_document_id:
                overlap.append("source_document")
            if overlap:
                linked.append(experiment | {"protocol_link_reasons": sorted(set(overlap))[:8]})
        linked.sort(key=lambda item: (len(item.get("protocol_link_reasons", [])), str(item.get("date") or "")), reverse=True)
        return linked

    def _related_literature(self, protocol: Protocol) -> list[dict[str, Any]]:
        terms = _important_terms(f"{protocol.title} {protocol.content}")
        literature = []
        for document in self.store.list_documents():
            if document.get("provider") != "literature":
                continue
            detail = self.store.get_document(str(document["id"]))
            text = f"{document.get('title')} {detail.get('content') if detail else ''}".lower()
            overlap = sorted(term for term in terms if term in text)
            if overlap:
                literature.append(document | {"protocol_link_reasons": overlap[:8]})
        return literature[:10]

    def _linked_statistics(self, experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        references = {str(experiment.get("id") or "") for experiment in experiments}
        references.update(str(experiment.get("experiment_id") or "") for experiment in experiments)
        stats = []
        for asset in self.store.list_assets(query=None):
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            if metadata.get("statistics") and str(asset.get("experiment_id") or "") in references:
                stats.append(asset)
        return stats[:20]

    def _usage_stats(self, protocol: Protocol, experiments: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "experiment_count": len(experiments),
            "first_used": min((str(item.get("date") or item.get("extracted_at") or "") for item in experiments), default=None),
            "last_used": max((str(item.get("date") or item.get("extracted_at") or "") for item in experiments), default=None),
            "linked_by": "source document and term overlap",
            "protocol_terms": _important_terms(f"{protocol.title} {protocol.content}")[:12],
        }

    def _success_metrics(self, experiments: list[dict[str, Any]]) -> dict[str, Any]:
        positive_terms = re.compile(r"\b(improved|increase|increased|stronger|successful|organized|higher|rescued|ready)\b", re.I)
        concern_terms = re.compile(r"\b(failed|issue|detachment|background|low|weak|problem|drift|contamination)\b", re.I)
        successes = 0
        concerns = 0
        for experiment in experiments:
            text = f"{experiment.get('notes') or ''} {experiment.get('conclusions') or ''}"
            successes += int(bool(positive_terms.search(text)))
            concerns += int(bool(concern_terms.search(text)))
        total = len(experiments)
        return {
            "linked_experiments": total,
            "positive_outcome_count": successes,
            "concern_count": concerns,
            "success_rate": round(successes / total, 3) if total else None,
            "method": "keyword-derived from existing notes/conclusions; not a statistical claim",
        }

    def _timeline(self, protocol: Protocol, experiments: list[dict[str, Any]], statistics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        events = [
            {
                "timestamp": protocol.updated_at or protocol.created_at,
                "event_type": "protocol_version",
                "title": f"{protocol.title} {protocol.version}",
                "description": "Protocol version detected from a ResearchOS document or asset.",
                "source": protocol.provider,
                "provenance": [{"fact": "protocol", "source": protocol.provider, "document": protocol.source_document_id}],
            }
        ]
        for experiment in experiments[:8]:
            events.append(
                {
                    "timestamp": experiment.get("date") or experiment.get("extracted_at"),
                    "event_type": "experiment",
                    "title": str(experiment.get("experiment_id") or experiment.get("title") or experiment.get("id")),
                    "description": "Experiment linked to protocol by source document or term overlap.",
                    "source": experiment.get("source_provider"),
                    "provenance": [{"fact": "experiment", "source": "sqlite", "experiment_id": experiment.get("id")}],
                }
            )
        for asset in statistics[:6]:
            events.append(
                {
                    "timestamp": asset.get("updated_at") or asset.get("created_at"),
                    "event_type": "statistics",
                    "title": str(asset.get("title") or asset.get("filename") or asset.get("asset_id")),
                    "description": "Parsed statistics linked through protocol experiments.",
                    "source": asset.get("provider"),
                    "provenance": [{"fact": "statistics", "source": "asset", "asset": asset.get("asset_id")}],
                }
            )
        return sorted(events, key=lambda item: str(item.get("timestamp") or ""), reverse=True)

    def _copilot(
        self,
        protocol: Protocol,
        experiments: list[dict[str, Any]],
        literature: list[dict[str, Any]],
        statistics: list[dict[str, Any]],
        success: dict[str, Any],
    ) -> dict[str, Any]:
        concerns = []
        if not experiments:
            concerns.append("No experiments are linked to this protocol yet.")
        if not statistics:
            concerns.append("No parsed statistics are linked through protocol experiments.")
        if success.get("concern_count"):
            concerns.append(f"{success['concern_count']} linked experiment(s) contain concern terms.")
        improvements = [
            "Review linked experiment outcomes before changing protocol steps.",
            "Add explicit controls, timing, concentrations, and success criteria if missing.",
        ]
        return {
            "provider": "local-fallback",
            "performance_summary": (
                f"{protocol.title} is linked to {len(experiments)} experiment(s), "
                f"{len(statistics)} statistics asset(s), and {len(literature)} literature record(s)."
            ),
            "potential_concerns": concerns or ["No obvious protocol concerns were detected from linked records."],
            "suggested_improvements": improvements,
            "guardrail": "ResearchOS never automatically edits protocol source documents.",
            "provenance": [{"fact": "protocol_performance", "source": "ProtocolService", "document": protocol.source_document_id}],
        }


def _protocol_id(source_id: str, title: str, version: str) -> str:
    digest = hashlib.sha1(f"{source_id}:{title}:{version}".encode("utf-8")).hexdigest()[:12]
    return f"protocol:{digest}"


def _protocol_family(title: str) -> str:
    cleaned = re.sub(r"\b(v|version)\s*\d+(?:\.\d+)?\b", "", title, flags=re.I)
    cleaned = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned.lower()).strip()
    return cleaned or title.lower()


def _detect_version(title: str, content: str) -> str:
    match = re.search(r"\b(?:version|v)\s*([0-9]+(?:\.[0-9]+)?)\b", f"{title}\n{content}", flags=re.I)
    return f"v{match.group(1)}" if match else "v1"


def _version_sort_key(version: str) -> tuple[int, ...]:
    values = [int(part) for part in re.findall(r"\d+", version)]
    return tuple(values or [1])


def _important_terms(text: str) -> list[str]:
    stop = {"protocol", "version", "note", "with", "from", "that", "this", "into", "the", "and", "for", "step", "steps"}
    terms = []
    for term in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", text):
        lowered = term.lower()
        if lowered in stop:
            continue
        terms.append(lowered)
    return sorted(set(terms))


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)] if value else []


def _change_interpretation(added: list[str], removed: list[str]) -> list[str]:
    notes = []
    if added:
        notes.append(f"{len(added)} line(s) were added in the compared version.")
    if removed:
        notes.append(f"{len(removed)} line(s) were removed in the compared version.")
    for label, lines in [("added", added), ("removed", removed)]:
        joined = " ".join(lines).lower()
        for field in ["concentration", "timing", "control", "antibody", "incubation", "wash", "temperature"]:
            if field in joined:
                notes.append(f"Potential {field} change detected in {label} lines.")
    return notes or ["No textual protocol changes detected."]

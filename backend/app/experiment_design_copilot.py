"""Experiment Design Copilot: narrative to reviewed draft experiment."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.config import Settings, get_settings
from app.general_experiments import GeneralExperimentService
from app.research_objects import ResearchObjectService
from app.storage import SQLiteStore

Confidence = Literal["High", "Medium", "Low", "Unknown"]


class ExperimentCopilotError(ValueError):
    """Raised for invalid copilot draft operations."""


@dataclass(frozen=True)
class ExtractionEvidence:
    field: str
    value: Any
    evidence: str
    start: int | None
    end: int | None
    confidence: Confidence


@dataclass(frozen=True)
class ClarificationQuestion:
    question_id: str
    field: str
    question: str
    required: bool
    reason: str
    status: str = "pending"
    answer: str | None = None


class ExperimentExtractionProvider:
    """Provider interface for deterministic or future LLM extraction."""

    provider_name = "base"

    def extract(self, narrative: str, objects: list[dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError

    def resolve_protocol(self, narrative: str, objects: list[dict[str, Any]]) -> dict[str, Any] | None:
        del narrative, objects
        return None

    def identify_ambiguities(self, draft: dict[str, Any]) -> list[str]:
        return []

    def generate_questions(self, draft: dict[str, Any]) -> list[ClarificationQuestion]:
        return []

    def build_draft(self, extraction: dict[str, Any]) -> dict[str, Any]:
        return extraction


class DeterministicExtractor(ExperimentExtractionProvider):
    """Regex-first extraction for safe demos and tests."""

    provider_name = "deterministic"

    def extract(self, narrative: str, objects: list[dict[str, Any]]) -> dict[str, Any]:
        evidence: list[ExtractionEvidence] = []
        lower = narrative.lower()
        protocol = self.resolve_protocol(narrative, objects)
        biological_system = _extract_biological_system(narrative, evidence)
        sample_unit = _extract_sample_unit(narrative, evidence)
        cohorts = _extract_cohorts(narrative, evidence)
        conditions = _extract_conditions(narrative, evidence)
        interventions = _extract_interventions(narrative, evidence, conditions)
        events = _extract_events(narrative, evidence)
        expected_duration = _extract_expected_duration(narrative, evidence)
        if protocol:
            evidence.append(
                _evidence(
                    "protocol",
                    protocol["title"],
                    _sentence_containing(narrative, protocol["matched_text"]),
                    narrative.lower().find(protocol["matched_text"].lower()),
                    confidence="High" if protocol["matched_text"].startswith("@") else "Medium",
                )
            )
        if "morpholog" in lower or "retinal cup" in lower:
            evidence.append(_evidence("expected_morphology", "mentioned", _sentence_containing(narrative, "morpholog"), lower.find("morpholog"), "Low"))
        draft = {
            "title": _infer_title(narrative),
            "biological_system": biological_system,
            "sample_unit": sample_unit,
            "protocol": protocol,
            "cohorts": cohorts,
            "conditions": conditions,
            "interventions": interventions,
            "events": events,
            "expected_duration": expected_duration,
            "expected_morphology": "mentioned" if "morpholog" in lower or "retinal cup" in lower else None,
            "evidence": [asdict(item) for item in evidence],
            "confidence": _confidence_summary(evidence),
        }
        draft["ambiguities"] = self.identify_ambiguities(draft)
        draft["clarification_questions"] = [asdict(item) for item in self.generate_questions(draft)]
        draft["sample_planning"] = _sample_planning_preview(draft)
        draft["timeline_preview"] = _timeline_preview(draft)
        draft["warnings"] = _warnings(draft)
        return draft

    def resolve_protocol(self, narrative: str, objects: list[dict[str, Any]]) -> dict[str, Any] | None:
        protocol_objects = [item for item in objects if item.get("object_type") in {"Protocol", "Protocol Version"}]
        tokens = []
        for match in re.finditer(r"@([A-Za-z0-9_.:+#/-]+)", narrative):
            tokens.append((match.group(0), match.group(1)))
        if "meyer" in narrative.lower():
            tokens.append(("Meyer", "Meyer"))
        if "nakano" in narrative.lower():
            tokens.append(("Nakano", "Nakano"))
        for raw, token in tokens:
            token_l = token.lower()
            for obj in protocol_objects:
                haystack = f"{obj.get('title')} {obj.get('subtitle')} {obj.get('object_id')}".lower()
                if token_l in haystack:
                    return {
                        "object_id": obj.get("object_id"),
                        "title": obj.get("title"),
                        "object_type": obj.get("object_type"),
                        "matched_text": raw,
                        "version_specified": obj.get("object_type") == "Protocol Version" or bool(re.search(r"\bv\d+|\d+\.\d+", raw.lower())),
                        "confidence": "High" if raw.startswith("@") else "Medium",
                    }
        return None

    def identify_ambiguities(self, draft: dict[str, Any]) -> list[str]:
        ambiguities = []
        if not draft.get("biological_system"):
            ambiguities.append("Biological system is missing.")
        if not draft.get("sample_unit"):
            ambiguities.append("Sample unit is missing.")
        if draft.get("protocol") and not draft["protocol"].get("version_specified"):
            ambiguities.append("Protocol mentioned but exact version is unspecified.")
        if not _has_replicates(draft):
            ambiguities.append("Missing biological replicate count.")
        if not _has_sample_counts(draft):
            ambiguities.append("Missing sample count per collection or condition.")
        if _has_dmso(draft):
            ambiguities.append("DMSO dilution is ambiguous unless final dilution is stated.")
        if _timeline_conflict(draft):
            ambiguities.append("Timeline contains potentially conflicting or duplicate treatment events.")
        return ambiguities

    def generate_questions(self, draft: dict[str, Any]) -> list[ClarificationQuestion]:
        questions: list[ClarificationQuestion] = []
        if not _has_replicates(draft):
            questions.append(ClarificationQuestion("replicates", "replicate_count", "How many biological replicates should each condition include?", True, "Sample planning requires replicate counts."))
        if not _has_sample_counts(draft):
            questions.append(ClarificationQuestion("sample_counts", "sample_count_per_replicate", "How many sample units should be used per replicate or collection?", True, "Collection/sample requirements are not specified."))
        if draft.get("protocol") and not draft["protocol"].get("version_specified"):
            questions.append(ClarificationQuestion("protocol_version", "protocol_version", "Which exact protocol version should this experiment reference?", True, "Historical experiments must reference exact protocol versions."))
        if _has_dmso(draft):
            questions.append(ClarificationQuestion("dmso_dilution", "vehicle", "Does DMSO refer to stock dilution or final dilution?", False, "Vehicle concentration is ambiguous."))
        if any(event.get("event_type") == "imaging" for event in draft.get("events", [])):
            questions.append(ClarificationQuestion("longitudinal_imaging", "imaging", "Are imaging events longitudinal on the same samples or destructive endpoints?", False, "Sample planning differs for longitudinal versus destructive imaging."))
        return questions


class MockExtractor(DeterministicExtractor):
    """Test double with deterministic behavior."""

    provider_name = "mock"


class ExperimentDesignCopilot:
    """Narrative-to-draft experiment service with explicit approval."""

    def __init__(self, settings: Settings | None = None, store: SQLiteStore | None = None, provider: ExperimentExtractionProvider | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or SQLiteStore(settings=self.settings)
        self.general = GeneralExperimentService(settings=self.settings)
        self.objects = ResearchObjectService(settings=self.settings, store=self.store)
        self.provider = provider or DeterministicExtractor()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return self.store._connect()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiment_copilot_sessions (
                    session_id TEXT PRIMARY KEY,
                    lab_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    narrative TEXT NOT NULL,
                    draft_json TEXT NOT NULL,
                    clarification_answers_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'awaiting_clarification',
                    created_experiment_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def create_draft(self, user_id: str, narrative: str, source_type: str = "typed_text", lab_id: str = "lab:demo") -> dict[str, Any]:
        if not narrative.strip():
            raise ExperimentCopilotError("Narrative text is required.")
        objects = self.objects.list_objects(user_id, lab_id=lab_id, limit=1000)
        draft = self.provider.build_draft(self.provider.extract(narrative, objects))
        session_id = f"copilot-session:{uuid.uuid4().hex[:16]}"
        status = "awaiting_clarification" if draft.get("clarification_questions") else "awaiting_approval"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_copilot_sessions
                    (session_id, lab_id, user_id, source_type, narrative, draft_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, lab_id, user_id, source_type, narrative, json.dumps(draft), status),
            )
        return self.get_draft(user_id, session_id)

    def get_draft(self, user_id: str, session_id: str) -> dict[str, Any]:
        row = self._session_row(session_id)
        if row is None or row["user_id"] != user_id:
            raise ExperimentCopilotError("Copilot draft not found.")
        draft = json.loads(row["draft_json"])
        return {
            "session_id": row["session_id"],
            "status": row["status"],
            "source_type": row["source_type"],
            "narrative": row["narrative"],
            "draft": draft,
            "clarification_answers": json.loads(row["clarification_answers_json"] or "{}"),
            "created_experiment_id": row["created_experiment_id"],
            "guardrails": [
                "Draft only; no experiment is created until researcher approval.",
                "Unknown is preferred over invented details.",
                "Every extracted field is backed by evidence when detected.",
            ],
        }

    def answer_clarifications(self, user_id: str, session_id: str, answers: dict[str, Any]) -> dict[str, Any]:
        row = self._session_row(session_id)
        if row is None or row["user_id"] != user_id:
            raise ExperimentCopilotError("Copilot draft not found.")
        draft = json.loads(row["draft_json"])
        existing = json.loads(row["clarification_answers_json"] or "{}")
        merged = existing | {key: str(value) for key, value in answers.items() if str(value).strip()}
        for question in draft.get("clarification_questions", []):
            if question["question_id"] in merged:
                question["status"] = "answered"
                question["answer"] = merged[question["question_id"]]
        _apply_clarification_answers(draft, merged)
        status = "awaiting_approval" if all(not q.get("required") or q.get("status") == "answered" for q in draft.get("clarification_questions", [])) else "awaiting_clarification"
        draft["sample_planning"] = _sample_planning_preview(draft)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE experiment_copilot_sessions
                SET draft_json = ?, clarification_answers_json = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ?
                """,
                (json.dumps(draft), json.dumps(merged), status, session_id),
            )
        return self.get_draft(user_id, session_id)

    def approve_draft(self, user_id: str, session_id: str, title: str | None = None, experiment_id: str | None = None) -> dict[str, Any]:
        row = self._session_row(session_id)
        if row is None or row["user_id"] != user_id:
            raise ExperimentCopilotError("Copilot draft not found.")
        if row["created_experiment_id"]:
            workspace = self.general.get_workspace(str(row["created_experiment_id"]), user_id)
            return {"created_new": False, "experiment": workspace["experiment"] if workspace else None, "workspace": workspace}
        draft = json.loads(row["draft_json"])
        required_unanswered = [q for q in draft.get("clarification_questions", []) if q.get("required") and q.get("status") != "answered"]
        if required_unanswered:
            raise ExperimentCopilotError("Required clarification questions must be answered before approval.")
        protocol = draft.get("protocol") or {}
        selected_protocol_id = _protocol_id_from_object(protocol.get("object_id"))
        selected_version_id = protocol.get("object_id") if protocol.get("object_type") == "Protocol Version" else None
        if selected_protocol_id and not selected_version_id:
            protocol_detail = self.general.get_protocol(selected_protocol_id)
            selected_version_id = protocol_detail.get("current_version_id") if protocol_detail else None
        experiment_title = title or draft.get("title") or "Draft experiment"
        if selected_protocol_id and selected_version_id:
            experiment = self.general.create_from_protocol(user_id, selected_protocol_id, selected_version_id, experiment_title, experiment_id=experiment_id)
        else:
            experiment = self.general.create_blank_experiment(
                actor_user_id=user_id,
                lab_id=row["lab_id"],
                title=experiment_title,
                experiment_id=experiment_id,
                biological_system=draft.get("biological_system"),
                sample_unit_type=draft.get("sample_unit") or "sample",
                expected_end_day=draft.get("expected_duration"),
                status="draft",
            )
        created_id = experiment["experiment_id"]
        self._populate_experiment(user_id, created_id, draft)
        with self._connect() as connection:
            connection.execute(
                "UPDATE experiment_copilot_sessions SET status = 'approved', created_experiment_id = ?, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (created_id, session_id),
            )
        return {"created_new": True, "experiment": experiment, "workspace": self.general.get_workspace(created_id, user_id), "copilot_session_id": session_id}

    def demo_narrative(self) -> dict[str, str]:
        return {
            "title": "Retinal organoid SAG timing demo",
            "narrative": DEMO_NARRATIVE,
        }

    def _session_row(self, session_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM experiment_copilot_sessions WHERE session_id = ?", (session_id,)).fetchone()

    def _populate_experiment(self, user_id: str, experiment_id: str, draft: dict[str, Any]) -> None:
        cohort_id_by_name: dict[str, str] = {}
        condition_id_by_name: dict[str, str] = {}
        for cohort in draft.get("cohorts", []):
            created = self.general.add_cohort(user_id, experiment_id, {"name": cohort["name"], "start_day": cohort.get("start_day"), "metadata": {"source": "copilot"}})
            cohort_id_by_name[cohort["name"]] = created["cohort_id"]
        for condition in draft.get("conditions", []):
            created = self.general.add_condition(
                user_id,
                experiment_id,
                {
                    "name": condition["name"],
                    "condition_type": condition.get("condition_type", "custom"),
                    "replicate_count": condition.get("replicate_count"),
                    "sample_count_per_replicate": condition.get("sample_count_per_replicate"),
                    "metadata": {"source": "copilot"},
                },
            )
            condition_id_by_name[condition["name"]] = created["condition_id"]
        for intervention in draft.get("interventions", []):
            condition_name = intervention.get("condition")
            self.general.add_intervention(
                user_id,
                experiment_id,
                {
                    "condition_id": condition_id_by_name.get(condition_name or ""),
                    "name": intervention["name"],
                    "intervention_type": intervention.get("intervention_type", "compound"),
                    "concentration_value": intervention.get("concentration_value"),
                    "concentration_unit": intervention.get("concentration_unit"),
                    "dose_value": intervention.get("dose_value"),
                    "dose_unit": intervention.get("dose_unit"),
                    "notes": intervention.get("notes"),
                },
            )
        for event in draft.get("events", []):
            self.general.add_event(
                user_id,
                experiment_id,
                {
                    "title": event["title"],
                    "event_type": event.get("event_type", "custom"),
                    "day": event.get("day"),
                    "source": "manual",
                    "metadata": {"source": "copilot", "confidence": event.get("confidence")},
                },
            )


DEMO_NARRATIVE = (
    "Using the Meyer retinal organoid protocol, plan NK_Expt_26 with an early treatment cohort on D1 "
    "and a late treatment cohort on D9. Conditions should include untreated, DMSO control, SAG 300 nM, "
    "and SAG 300 nM plus GRKi 10 nM. Collect untreated D1, early cohort D2 and D3, late untreated baseline D9, "
    "and late cohort D11 and D13. Image all conditions on D16, D25, and D35. Culture endpoint is D90. "
    "Needs clarification: DMSO 1000x likely means 1:1000 final dilution."
)


def _extract_biological_system(text: str, evidence: list[ExtractionEvidence]) -> str | None:
    patterns = [("retinal organoid", "retinal organoid"), ("organoid", "organoid"), ("rpe", "RPE"), ("stem cell", "stem cells"), ("cell culture", "cell culture")]
    for needle, value in patterns:
        idx = text.lower().find(needle)
        if idx >= 0:
            evidence.append(_evidence("biological_system", value, _sentence_containing(text, needle), idx, "High"))
            return value
    return None


def _extract_sample_unit(text: str, evidence: list[ExtractionEvidence]) -> str | None:
    for needle, value in [("organoid", "organoid"), ("well", "well"), ("dish", "dish"), ("animal", "animal"), ("sample", "sample")]:
        idx = text.lower().find(needle)
        if idx >= 0:
            evidence.append(_evidence("sample_unit", value, _sentence_containing(text, needle), idx, "Medium"))
            return value
    return None


def _extract_cohorts(text: str, evidence: list[ExtractionEvidence]) -> list[dict[str, Any]]:
    cohorts = []
    for match in re.finditer(r"(early|late)[\w\s-]{0,30}?\bD(\d+)", text, flags=re.I):
        name = f"{match.group(1).capitalize()} treatment cohort on D{match.group(2)}"
        cohorts.append({"name": name, "start_day": int(match.group(2)), "confidence": "High"})
        evidence.append(_evidence("cohort", name, _sentence_containing(text, match.group(0)), match.start(), "High"))
    return _unique_by(cohorts, "name")


def _extract_conditions(text: str, evidence: list[ExtractionEvidence]) -> list[dict[str, Any]]:
    specs = [
        ("untreated", "Untreated", "untreated"),
        ("dmso", "DMSO control", "vehicle_control"),
        ("vehicle", "Vehicle control", "vehicle_control"),
        ("sag", "SAG 300 nM", "treatment"),
        ("grki", "SAG 300 nM + GRKi 10 nM", "treatment"),
    ]
    conditions = []
    lower = text.lower()
    for needle, name, kind in specs:
        idx = lower.find(needle)
        if idx >= 0:
            conditions.append({"name": name, "condition_type": kind, "confidence": "High" if needle in {"sag", "dmso", "untreated"} else "Medium"})
            evidence.append(_evidence("condition", name, _sentence_containing(text, needle), idx, "High"))
    return _unique_by(conditions, "name")


def _extract_interventions(text: str, evidence: list[ExtractionEvidence], conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    interventions = []
    for compound in ["SAG", "GRKi", "BMP4", "DMSO"]:
        for match in re.finditer(rf"\b{re.escape(compound)}\b(?:\s*(\d+(?:\.\d+)?)\s*(nM|uM|µM|ng/mL|mg/mL|x))?", text, flags=re.I):
            value = float(match.group(1)) if match.group(1) else None
            unit = match.group(2) if match.group(2) else None
            condition = "SAG 300 nM + GRKi 10 nM" if compound.lower() == "grki" else ("DMSO control" if compound.lower() == "dmso" else None)
            if compound == "SAG" and any("GRKi" in c["name"] for c in conditions):
                condition = None
            interventions.append({"name": compound, "intervention_type": "compound", "condition": condition, "concentration_value": value, "concentration_unit": unit, "confidence": "High" if unit else "Medium"})
            evidence.append(_evidence("intervention", compound, _sentence_containing(text, match.group(0)), match.start(), "High" if unit else "Medium"))
    return _unique_by(interventions, "name", "concentration_value", "concentration_unit")


def _extract_events(text: str, evidence: list[ExtractionEvidence]) -> list[dict[str, Any]]:
    events = []
    for match in re.finditer(r"\bD(\d+)\b", text, flags=re.I):
        day = int(match.group(1))
        sentence = _sentence_containing(text, match.group(0))
        sentence_l = sentence.lower()
        if "image" in sentence_l or "imaging" in sentence_l:
            event_type = "imaging"
            title = f"Imaging D{day}"
        elif "collect" in sentence_l or "collection" in sentence_l:
            event_type = "collection"
            title = f"Collection D{day}"
        elif "endpoint" in sentence_l:
            event_type = "endpoint"
            title = f"Endpoint D{day}"
        elif "treat" in sentence_l or "cohort" in sentence_l:
            event_type = "treatment"
            title = f"Treatment/cohort start D{day}"
        else:
            event_type = "milestone"
            title = f"Milestone D{day}"
        events.append({"title": title, "day": day, "event_type": event_type, "confidence": "Medium", "evidence": sentence})
        evidence.append(_evidence("event", title, sentence, match.start(), "Medium"))
    return _unique_by(events, "title", "day")


def _extract_expected_duration(text: str, evidence: list[ExtractionEvidence]) -> int | None:
    match = re.search(r"(endpoint|end|culture endpoint)[^\n.]*?\bD(\d+)\b", text, flags=re.I)
    if not match:
        return None
    day = int(match.group(2))
    evidence.append(_evidence("expected_duration", day, _sentence_containing(text, match.group(0)), match.start(), "High"))
    return day


def _evidence(field: str, value: Any, sentence: str, start: int, confidence: Confidence = "Medium") -> ExtractionEvidence:
    return ExtractionEvidence(field=field, value=value, evidence=sentence, start=start if start >= 0 else None, end=(start + len(str(value))) if start >= 0 else None, confidence=confidence)


def _sentence_containing(text: str, needle: str) -> str:
    lower = text.lower()
    index = lower.find(str(needle).lower())
    if index < 0:
        return ""
    start = max(lower.rfind(".", 0, index), lower.rfind("\n", 0, index)) + 1
    end_dot = lower.find(".", index)
    end_newline = lower.find("\n", index)
    ends = [pos for pos in [end_dot, end_newline] if pos >= 0]
    end = min(ends) if ends else len(text)
    return text[start:end].strip()


def _infer_title(text: str) -> str:
    match = re.search(r"\b(NK[_ -]?Expt[_ -]?\d+|EXP[-_ ]?\d+)\b", text, flags=re.I)
    if match:
        return match.group(1).replace(" ", "_").replace("-", "_")
    return "Draft experiment from narrative"


def _confidence_summary(evidence: list[ExtractionEvidence]) -> dict[str, Confidence]:
    summary: dict[str, Confidence] = {}
    rank = {"Unknown": 0, "Low": 1, "Medium": 2, "High": 3}
    for item in evidence:
        if rank[item.confidence] >= rank.get(summary.get(item.field, "Unknown"), 0):
            summary[item.field] = item.confidence
    return summary


def _has_replicates(draft: dict[str, Any]) -> bool:
    return any(condition.get("replicate_count") for condition in draft.get("conditions", []))


def _has_sample_counts(draft: dict[str, Any]) -> bool:
    return any(condition.get("sample_count_per_replicate") for condition in draft.get("conditions", []))


def _has_dmso(draft: dict[str, Any]) -> bool:
    return any("DMSO" in condition.get("name", "") for condition in draft.get("conditions", []))


def _timeline_conflict(draft: dict[str, Any]) -> bool:
    treatment_days = [event.get("day") for event in draft.get("events", []) if event.get("event_type") == "treatment"]
    return len(treatment_days) != len(set(treatment_days)) and bool(treatment_days)


def _warnings(draft: dict[str, Any]) -> list[str]:
    warnings = ["Draft requires researcher approval before experiment creation."]
    warnings.extend(draft.get("ambiguities") or [])
    return _dedupe(warnings)


def _sample_planning_preview(draft: dict[str, Any]) -> dict[str, Any]:
    replicate_counts = [c.get("replicate_count") for c in draft.get("conditions", []) if c.get("replicate_count")]
    sample_counts = [c.get("sample_count_per_replicate") for c in draft.get("conditions", []) if c.get("sample_count_per_replicate")]
    if not replicate_counts or not sample_counts:
        return {"status": "incomplete", "message": "Cannot calculate samples required because replicate count or sample count is missing.", "missing_values": ["biological_replicates", "sample_units_per_replicate"]}
    return {"status": "preview", "message": "Sample planning preview is available after approval.", "replicate_counts": replicate_counts, "sample_counts": sample_counts}


def _timeline_preview(draft: dict[str, Any]) -> list[dict[str, Any]]:
    inherited = []
    protocol = draft.get("protocol")
    if protocol:
        inherited.append({"title": "Inherited protocol events", "event_type": "protocol", "source": "inherited", "day": None, "protocol": protocol.get("title")})
    return [*inherited, *sorted(draft.get("events", []), key=lambda item: item.get("day") if item.get("day") is not None else 999999)]


def _apply_clarification_answers(draft: dict[str, Any], answers: dict[str, str]) -> None:
    replicate = _int_from_answer(answers.get("replicates"))
    sample_count = _int_from_answer(answers.get("sample_counts"))
    for condition in draft.get("conditions", []):
        if replicate and not condition.get("replicate_count"):
            condition["replicate_count"] = replicate
        if sample_count and not condition.get("sample_count_per_replicate"):
            condition["sample_count_per_replicate"] = sample_count
    if answers.get("protocol_version") and draft.get("protocol"):
        draft["protocol"]["clarified_version"] = answers["protocol_version"]
    if answers.get("dmso_dilution"):
        draft["vehicle_note"] = answers["dmso_dilution"]


def _int_from_answer(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


def _protocol_id_from_object(object_id: str | None) -> str | None:
    if not object_id:
        return None
    if object_id.startswith("protocol-version:"):
        parts = object_id.split(":")
        if len(parts) >= 3:
            return f"protocol:{parts[1]}"
    if object_id.startswith("protocol:"):
        return object_id
    return None


def _unique_by(items: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result = []
    for item in items:
        key = tuple(item.get(name) for name in keys)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

"""Hybrid AI-assisted protocol extraction helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.ai.provider_manager import get_ai_provider
from app.ai_providers import AIProviderError
from app.config import Settings


PROTOCOL_EXTRACTION_SCHEMA_VERSION = "protocol-extraction-hybrid-v1"

EXTRACTION_SECTIONS = {
    "timeline",
    "materials",
    "media_recipes",
    "expected_results_qc",
    "troubleshooting",
    "unclassified_notes",
}


@dataclass(frozen=True)
class ProtocolAIResult:
    draft: dict[str, Any] | None
    provider: str
    model: str | None
    error: str | None = None


def ai_extraction_enabled(settings: Settings) -> bool:
    return settings.ai_provider.lower() not in {"", "none"}


def classify_protocol_with_ai(
    *,
    settings: Settings,
    canonical_blocks: list[dict[str, Any]],
    deterministic_draft: dict[str, Any],
    user_instruction: str | None = None,
) -> ProtocolAIResult:
    """Ask the configured provider for schema-constrained protocol extraction."""

    if not ai_extraction_enabled(settings):
        return ProtocolAIResult(draft=None, provider="none", model=None, error="No AI provider configured.")
    try:
        provider = get_ai_provider(settings)
        prompt = _build_prompt(canonical_blocks, deterministic_draft, user_instruction)
        raw = provider.chat(prompt)
        parsed = _parse_json_object(raw)
        validated = validate_ai_protocol_draft(parsed, canonical_blocks)
        return ProtocolAIResult(
            draft=validated,
            provider=getattr(provider, "provider_name", settings.ai_provider),
            model=settings.ai_model,
        )
    except (AIProviderError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return ProtocolAIResult(
            draft=None,
            provider=settings.ai_provider,
            model=settings.ai_model,
            error=str(exc),
        )


def validate_ai_protocol_draft(payload: dict[str, Any], canonical_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    valid_source_ids = {str(block.get("block_id")) for block in canonical_blocks if block.get("block_id")}
    result: dict[str, Any] = {
        "protocol_title": _nullable_string(payload.get("protocol_title")),
        "timeline": [],
        "materials": [],
        "media_recipes": [],
        "expected_results_qc": [],
        "troubleshooting": [],
        "unclassified_notes": [],
    }
    for section in EXTRACTION_SECTIONS:
        values = payload.get(section) or []
        if not isinstance(values, list):
            raise ValueError(f"AI field {section} must be a list.")
        for item in values:
            if not isinstance(item, dict):
                continue
            source_ids = [str(value) for value in item.get("source_ids") or [] if str(value) in valid_source_ids]
            if not source_ids:
                raise ValueError(f"AI item in {section} referenced no valid source IDs.")
            normalized = dict(item)
            normalized["source_ids"] = source_ids
            normalized["confidence"] = _confidence(normalized.get("confidence"))
            result[section].append(normalized)
    return result


def ai_draft_to_legacy_draft(
    *,
    ai_draft: dict[str, Any],
    deterministic_draft: dict[str, Any],
    canonical_blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Map strict AI extraction JSON into the existing review draft shape."""

    block_by_id = {str(block.get("block_id")): block for block in canonical_blocks}
    draft = dict(deterministic_draft)
    if ai_draft.get("protocol_title"):
        draft["proposed_title"] = ai_draft["protocol_title"]
    draft["proposed_events"] = [
        {
            "title": item.get("step_title") or item.get("day_or_time") or "Protocol step",
            "relative_day": _day_from_value(item.get("day_or_time")),
            "event_type": "protocol_step",
            "description": item.get("instructions"),
            "default_duration": item.get("duration"),
            "metadata": {
                "temperature": item.get("temperature"),
                "incubation": item.get("incubation"),
                "notes": item.get("notes"),
            },
            **_legacy_source_fields(item, block_by_id, "ai"),
        }
        for item in ai_draft.get("timeline", [])
    ] or draft.get("proposed_events", [])
    draft["proposed_materials"] = [
        {
            "name": item.get("name") or "Material",
            "vendor": item.get("supplier"),
            "catalog_number": item.get("catalog_number"),
            "concentration": item.get("working_concentration") or item.get("stock_concentration"),
            "notes": item.get("notes"),
            **_legacy_source_fields(item, block_by_id, "ai"),
        }
        for item in ai_draft.get("materials", [])
        if item.get("name")
    ] or draft.get("proposed_materials", [])
    draft["proposed_media"] = [
        {
            "recipe": item.get("name") or "Media recipe",
            "components": item.get("components") or [],
            "preparation": item.get("preparation"),
            "storage": item.get("storage"),
            **_legacy_source_fields(item, block_by_id, "ai"),
        }
        for item in ai_draft.get("media_recipes", [])
    ] or draft.get("proposed_media", [])
    draft["proposed_expected_results"] = [
        {
            "title": item.get("checkpoint") or "Expected result",
            "description": item.get("expected_observation"),
            "metadata": {
                "acceptance_criterion": item.get("acceptance_criterion"),
                "failure_criterion": item.get("failure_criterion"),
                "timing": item.get("timing"),
            },
            **_legacy_source_fields(item, block_by_id, "ai"),
        }
        for item in ai_draft.get("expected_results_qc", [])
    ] or draft.get("proposed_expected_results", [])
    draft["proposed_troubleshooting"] = [
        {
            "issue": item.get("problem") or "Troubleshooting item",
            "possible_causes": item.get("possible_causes") or [],
            "possible_solutions": item.get("recommended_actions") or [],
            **_legacy_source_fields(item, block_by_id, "ai"),
        }
        for item in ai_draft.get("troubleshooting", [])
    ] or draft.get("proposed_troubleshooting", [])
    notes = [
        {
            "source_ids": item.get("source_ids") or [],
            "text": item.get("text"),
            "reason_unclassified": item.get("reason_unclassified"),
            "confidence": item.get("confidence") or "low",
        }
        for item in ai_draft.get("unclassified_notes", [])
    ]
    evidence = dict(draft.get("extraction_evidence") or {})
    evidence["ai_unclassified_notes"] = notes
    draft["extraction_evidence"] = evidence
    draft["warnings"] = [
        *list(draft.get("warnings") or []),
        "AI-assisted extraction may contain errors. Verify all protocol details before use.",
    ]
    return draft


def extraction_items_from_draft(
    *,
    extraction_run_id: str,
    draft: dict[str, Any],
    origin: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    section_map = {
        "timeline": draft.get("proposed_events") or [],
        "materials": draft.get("proposed_materials") or [],
        "media_recipes": draft.get("proposed_media") or [],
        "expected_results_qc": [
            *(draft.get("proposed_expected_results") or []),
            *(draft.get("proposed_qc") or []),
        ],
        "troubleshooting": draft.get("proposed_troubleshooting") or [],
    }
    for section, values in section_map.items():
        for value in values:
            if not isinstance(value, dict):
                continue
            source_ids = list(value.get("source_ids") or [])
            items.append(
                {
                    "item_id": f"protocol-extraction-item:{len(items) + 1:04d}:{extraction_run_id}",
                    "extraction_run_id": extraction_run_id,
                    "section": section,
                    "source_ids": source_ids,
                    "raw_source_text": value.get("source_excerpt") or value.get("description") or value.get("notes") or "",
                    "normalized": value,
                    "confidence": value.get("confidence") or "medium",
                    "origin": value.get("origin") or origin,
                    "review_status": value.get("review_status") or "needs_review",
                }
            )
    evidence = dict(draft.get("extraction_evidence") or {})
    for note in evidence.get("unclassified_notes", {}).get("items", []) if isinstance(evidence.get("unclassified_notes"), dict) else []:
        items.append(
            {
                "item_id": f"protocol-extraction-item:{len(items) + 1:04d}:{extraction_run_id}",
                "extraction_run_id": extraction_run_id,
                "section": "unclassified_notes",
                "source_ids": [],
                "raw_source_text": str(note),
                "normalized": {"text": str(note)},
                "confidence": "low",
                "origin": origin,
                "review_status": "needs_review",
            }
        )
    return items


def _build_prompt(
    canonical_blocks: list[dict[str, Any]],
    deterministic_draft: dict[str, Any],
    user_instruction: str | None,
) -> str:
    source = {
        "schema_version": PROTOCOL_EXTRACTION_SCHEMA_VERSION,
        "source_blocks": canonical_blocks,
        "rules_only_draft": deterministic_draft,
        "user_instruction": user_instruction or None,
    }
    return (
        "Extract a scientific protocol draft as strict JSON only. "
        "Use only facts directly supported by source_blocks. Use null for absent facts. "
        "Every extracted item must include at least one valid source_ids entry. "
        "Do not add supplier, catalog number, concentration, duration, temperature, or timing from outside the source. "
        "Return keys: protocol_title, timeline, materials, media_recipes, expected_results_qc, troubleshooting, unclassified_notes. "
        "Input JSON:\n"
        f"{json.dumps(source, ensure_ascii=False)}"
    )


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("AI extraction response must be a JSON object.")
    return parsed


def _legacy_source_fields(item: dict[str, Any], block_by_id: dict[str, dict[str, Any]], origin: str) -> dict[str, Any]:
    source_ids = [str(value) for value in item.get("source_ids") or []]
    excerpts = [str(block_by_id[source_id].get("text") or "") for source_id in source_ids if source_id in block_by_id]
    return {
        "source_ids": source_ids,
        "source_excerpt": "\n".join(excerpts)[:1000],
        "source_location": ", ".join(source_ids),
        "confidence": _confidence(item.get("confidence")),
        "origin": origin,
        "draft_status": "proposed",
    }


def _confidence(value: Any) -> str:
    normalized = str(value or "low").lower()
    return normalized if normalized in {"high", "medium", "low", "unknown"} else "low"


def _nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _day_from_value(value: Any) -> int | None:
    if value is None:
        return None
    import re

    match = re.search(r"\bD(?:ay\s*)?(\d{1,3})\b|\bday\s+(\d{1,3})\b", str(value), flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1) or match.group(2))

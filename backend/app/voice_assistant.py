"""Voice laboratory assistant scaffolding.

This module is intentionally speech-provider agnostic. The first implementation
accepts a transcript from the client and parses deterministic commands locally.
Future iOS, Android, Whisper, OpenAI, Apple Speech, or Android Speech providers
can implement the same provider interface without changing session logic.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


VOICE_COMMAND_TYPES = {
    "start_experiment",
    "start_session",
    "end_session",
    "observation",
    "treatment",
    "media_change",
    "collection",
    "imaging",
    "custom_note",
}


@dataclass(frozen=True)
class SpeechResult:
    """Normalized output from any future speech-to-text provider."""

    transcript: str
    provider: str
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SpeechProvider(Protocol):
    """Interface for future local, mobile, or cloud speech providers."""

    name: str

    def transcribe(self, audio_reference: str | None = None, transcript: str | None = None) -> SpeechResult:
        """Return a transcript without committing any laboratory record."""


class PlaceholderSpeechProvider:
    """Local placeholder provider used until speech capture is wired in."""

    name = "placeholder"

    def transcribe(self, audio_reference: str | None = None, transcript: str | None = None) -> SpeechResult:
        text = (transcript or "").strip()
        if not text:
            text = "Voice capture placeholder. Type or paste the transcript before confirming."
        return SpeechResult(
            transcript=text,
            provider=self.name,
            confidence=None,
            metadata={
                "audio_reference": audio_reference,
                "cloud_speech_used": False,
                "requires_confirmation": True,
            },
        )


@dataclass(frozen=True)
class VoiceCommand:
    """Reviewable command parsed from a transcript."""

    voice_session_id: str
    command_type: str
    transcript: str
    parsed_fields: dict[str, Any]
    confidence: str
    suggested_corrections: list[str]
    requires_confirmation: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe command draft."""

        return {
            "voice_session_id": self.voice_session_id,
            "command_type": self.command_type,
            "transcript": self.transcript,
            "parsed_fields": self.parsed_fields,
            "confidence": self.confidence,
            "suggested_corrections": self.suggested_corrections,
            "requires_confirmation": self.requires_confirmation,
        }


def supported_speech_providers() -> list[dict[str, Any]]:
    """Return current and planned speech providers for UI capability display."""

    return [
        {
            "provider": "placeholder",
            "status": "active",
            "cloud_required": False,
            "notes": "Accepts typed/pasted transcripts. No audio leaves ResearchOS.",
        },
        {"provider": "ios", "status": "planned", "cloud_required": "device-dependent"},
        {"provider": "android", "status": "planned", "cloud_required": "device-dependent"},
        {"provider": "whisper", "status": "planned", "cloud_required": False},
        {"provider": "openai", "status": "planned", "cloud_required": True},
        {"provider": "apple_speech", "status": "planned", "cloud_required": "device-dependent"},
        {"provider": "android_speech", "status": "planned", "cloud_required": "device-dependent"},
    ]


def draft_voice_command(
    transcript: str | None,
    *,
    audio_reference: str | None = None,
    session_id: str | None = None,
    experiment_id: str | None = None,
    provider: SpeechProvider | None = None,
) -> dict[str, Any]:
    """Parse a reviewable voice command without writing to storage."""

    speech_provider = provider or PlaceholderSpeechProvider()
    speech = speech_provider.transcribe(audio_reference=audio_reference, transcript=transcript)
    command = parse_voice_command(speech.transcript)
    payload = command.as_dict()
    payload["speech_provider"] = speech.provider
    payload["speech"] = {
        "provider": speech.provider,
        "confidence": speech.confidence,
        "metadata": speech.metadata,
    }
    payload["session_id"] = session_id
    payload["experiment_id"] = experiment_id
    payload["status"] = "draft"
    payload["message"] = "Review the transcript and parsed command before confirming. Nothing has been saved yet."
    return payload


def parse_voice_command(transcript: str) -> VoiceCommand:
    """Classify a transcript into a deterministic laboratory command."""

    normalized = transcript.strip()
    lower = normalized.lower()
    command_type = "custom_note"
    parsed: dict[str, Any] = {"note": normalized}
    corrections: list[str] = []

    if re.search(r"\bstart\s+(an?\s+)?experiment\b", lower):
        command_type = "start_experiment"
        parsed = {"experiment_id": _extract_experiment_id(normalized), "note": normalized}
    elif re.search(r"\bstart\s+(a\s+)?session\b", lower):
        command_type = "start_session"
        parsed = {"experiment_id": _extract_experiment_id(normalized), "note": normalized}
    elif re.search(r"\bend\s+(the\s+)?session\b", lower):
        command_type = "end_session"
        parsed = {"note": normalized}
    elif "media change" in lower or "changed media" in lower:
        command_type = "media_change"
        parsed = {"media_type": _extract_after_keywords(normalized, ["media change", "changed media"]), "note": normalized}
    elif re.search(r"\b(treat|treatment|treated|added|add)\b", lower):
        command_type = "treatment"
        parsed = {
            "compound": _extract_compound(normalized),
            "dose": _extract_dose(normalized),
            "timepoint": _extract_timepoint(normalized),
            "note": normalized,
        }
    elif re.search(r"\b(collect|collection|collected|harvest|harvested)\b", lower):
        command_type = "collection"
        parsed = {"timepoint": _extract_timepoint(normalized), "note": normalized}
    elif re.search(r"\b(image|imaging|microscopy|stain|staining)\b", lower):
        command_type = "imaging"
        parsed = {"markers": _extract_marker_like_terms(normalized), "timepoint": _extract_timepoint(normalized), "note": normalized}
    elif re.search(r"\b(observation|observe|observed|note)\b", lower):
        command_type = "observation"
        parsed = {"note": normalized}

    if command_type == "custom_note":
        corrections.append("Command type was not obvious; review whether this should be an observation, treatment, media change, collection, or imaging note.")
    if command_type == "treatment" and not parsed.get("compound"):
        corrections.append("Treatment command detected, but no compound or reagent was confidently parsed.")
    if command_type in {"start_session", "start_experiment"} and not parsed.get("experiment_id"):
        corrections.append("No experiment ID was detected; the active session or manual selection will be used.")

    return VoiceCommand(
        voice_session_id=f"voice-session:{uuid.uuid4().hex[:16]}",
        command_type=command_type,
        transcript=normalized,
        parsed_fields={key: value for key, value in parsed.items() if value not in (None, "", [])},
        confidence="medium" if command_type != "custom_note" else "low",
        suggested_corrections=corrections,
    )


def session_event_from_voice_command(command_type: str, transcript: str, parsed_fields: dict[str, Any]) -> dict[str, Any]:
    """Map a confirmed voice command to a session event payload."""

    title_by_type = {
        "observation": "Voice Observation",
        "treatment": "Voice Treatment",
        "media_change": "Voice Media Change",
        "collection": "Voice Collection",
        "imaging": "Voice Imaging",
        "custom_note": "Voice Note",
        "start_experiment": "Voice Experiment Note",
        "start_session": "Voice Session Started",
        "end_session": "Voice Session Ended",
    }
    event_type_by_command = {
        "observation": "observation",
        "treatment": "treatment",
        "media_change": "media_change",
        "collection": "collection",
        "imaging": "imaging",
        "custom_note": "voice_note",
        "start_experiment": "manual_note",
        "start_session": "manual_note",
        "end_session": "manual_note",
    }
    return {
        "event_type": event_type_by_command.get(command_type, "voice_note"),
        "title": title_by_type.get(command_type, "Voice Note"),
        "content": transcript,
        "metadata": {
            "source": "voice_assistant",
            "command_type": command_type,
            "parsed_fields": parsed_fields,
            "requires_confirmation_before_commit": True,
        },
    }


def voice_markdown_entry(command_type: str, transcript: str, parsed_fields: dict[str, Any]) -> str:
    """Create a reviewable pending notebook draft from a confirmed transcript."""

    title = command_type.replace("_", " ").title()
    lines = [
        f"# Voice {title}",
        "",
        "> Source: ResearchOS Voice Assistant confirmed transcript.",
        "",
        "## Confirmed Transcript",
        "",
        transcript.strip(),
        "",
        "## Parsed Command",
        "",
        f"- Command: {command_type}",
    ]
    for key, value in parsed_fields.items():
        lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    lines.extend(
        [
            "",
            "## Review Note",
            "",
            "This entry was generated from a confirmed transcript. ResearchOS did not silently modify the original wording.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _extract_after_keywords(text: str, keywords: list[str]) -> str | None:
    lower = text.lower()
    for keyword in keywords:
        index = lower.find(keyword)
        if index >= 0:
            value = text[index + len(keyword) :].strip(" :.-")
            return value or None
    return None


def _extract_experiment_id(text: str) -> str | None:
    patterns = [
        r"\b(NK[_\-\s]?Expt[_\-\s]?\d+)\b",
        r"\b(EXP[_\-\s]?\d+)\b",
        r"\b(experiment\s+\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", "_", match.group(1)).replace("-", "_")
    return None


def _extract_dose(text: str) -> str | None:
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(nM|uM|µM|mM|M|ng/ml|ug/ml|µg/ml|mg/ml|%)\b", text, flags=re.IGNORECASE)
    return f"{match.group(1)} {match.group(2)}" if match else None


def _extract_timepoint(text: str) -> str | None:
    match = re.search(r"\b(Day\s*\d+|D\d+|hour\s*\d+|\d+\s*h)\b", text, flags=re.IGNORECASE)
    return match.group(1).replace(" ", "") if match else None


def _extract_compound(text: str) -> str | None:
    match = re.search(r"\b(?:treated|treat|treatment|added|add)\s+(?:with\s+)?([A-Za-z][A-Za-z0-9+\-/ ]{1,40}?)(?:\s+(?:at|to|for|from|on|$)|[,.])", text, flags=re.IGNORECASE)
    if not match:
        return None
    candidate = match.group(1).strip(" .,:;")
    return candidate or None


def _extract_marker_like_terms(text: str) -> list[str]:
    terms = re.findall(r"\b[A-Z][A-Z0-9]{2,8}\b", text)
    return sorted(set(terms))

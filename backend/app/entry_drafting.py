"""Draft structured lab notebook entries from dictated raw notes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.ai_providers import AIProviderError, get_ai_provider
from app.config import Settings, get_settings


ENTRY_FIELDS = [
    "title",
    "experiment_id",
    "objective",
    "date",
    "researcher",
    "cell_line",
    "organoid_batch",
    "differentiation_day",
    "conditions",
    "treatment_schedule",
    "reagents_concentrations",
    "controls",
    "planned_readouts",
    "observations",
    "issues_deviations",
    "next_steps",
]


@dataclass(frozen=True)
class EntryTemplate:
    """Reusable lab notebook entry template metadata."""

    id: str
    name: str
    description: str
    sections: list[str]


ENTRY_TEMPLATES = {
    "retinal_organoid": EntryTemplate(
        id="retinal_organoid",
        name="Retinal organoid experiment",
        description="Treatment, differentiation-day, batch, and readout-focused retinal organoid entry.",
        sections=["Overview", "Experimental setup", "Treatment schedule", "Readouts", "Observations", "Next steps"],
    ),
    "immunostaining": EntryTemplate(
        id="immunostaining",
        name="Immunostaining",
        description="Fixation, staining markers, antibodies, imaging, and interpretation entry.",
        sections=["Overview", "Sample and markers", "Staining workflow", "Imaging", "Results", "Next steps"],
    ),
    "media_treatment_log": EntryTemplate(
        id="media_treatment_log",
        name="Media change / treatment log",
        description="Daily media change, treatment, concentration, and deviation tracking entry.",
        sections=["Overview", "Media/treatment log", "Controls", "Observations", "Issues/deviations", "Next steps"],
    ),
    "imaging_session": EntryTemplate(
        id="imaging_session",
        name="Imaging session",
        description="Microscope session entry for samples, channels, markers, and image-quality notes.",
        sections=["Overview", "Samples", "Imaging setup", "Channels/readouts", "Observations", "Next steps"],
    ),
    "general_experiment": EntryTemplate(
        id="general_experiment",
        name="General experiment",
        description="Flexible structured scientific notebook entry.",
        sections=["Overview", "Experimental setup", "Results/observations", "Issues/deviations", "Next steps"],
    ),
}


@dataclass(frozen=True)
class DraftEntry:
    """Structured draft generated from raw dictated notes."""

    structured: dict[str, Any]
    markdown: str
    template: str
    confidence: float
    missing_fields: list[str]
    ai_used: bool
    provider: str


def available_entry_templates() -> list[dict[str, Any]]:
    """Return public metadata for supported notebook-entry templates."""

    return [
        {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "sections": template.sections,
        }
        for template in ENTRY_TEMPLATES.values()
    ]


def _resolve_template(template: str | None) -> EntryTemplate:
    """Resolve a requested template, defaulting conservatively to general."""

    key = (template or "general_experiment").strip().lower()
    if key == "general":
        key = "general_experiment"
    return ENTRY_TEMPLATES.get(key, ENTRY_TEMPLATES["general_experiment"])


def _first_match(text: str, patterns: list[str]) -> str | None:
    """Return the first regex capture found in raw notes."""

    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip(" .;:-")
    return None


def _terms(text: str, candidates: list[str]) -> list[str]:
    """Return known scientific terms detected in raw notes."""

    found = []
    for candidate in candidates:
        if re.search(rf"(?<![A-Za-z0-9-]){re.escape(candidate)}(?![A-Za-z0-9-])", text, re.I):
            found.append(candidate)
    return sorted(set(found))


def _list_from_matches(text: str, patterns: list[str]) -> list[str]:
    """Collect comma/and-separated list values from regex captures."""

    values = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I | re.S):
            raw = re.sub(r"\s+", " ", match.group(1)).strip(" .;:-")
            values.extend(item.strip(" .;:-") for item in re.split(r",|\band\b|\bplus\b", raw) if item.strip())
    return sorted(set(values))


def _experiment_id(text: str) -> str | None:
    """Extract experiment identifiers from common dictated forms."""

    create_match = re.search(r"\bcreate\s+([A-Za-z]{1,8})\s+expt\.?\s*(\d+)", text, re.I)
    if create_match:
        return f"{create_match.group(1).upper()}-EXPT-{create_match.group(2)}"

    explicit = _first_match(
        text,
        [
            r"\bexperiment(?:\s+id)?\s*[:#-]?\s*([A-Za-z0-9_-]+(?:\s*[A-Za-z0-9_-]+)?)",
            r"\bexpt\.?\s*([A-Za-z0-9_-]+)",
            r"\bexp\.?\s*([A-Za-z0-9_-]+)",
        ],
    )
    if explicit:
        return explicit.upper().replace(" ", "-")
    return None


def _title(text: str, experiment_id: str | None, treatments: list[str]) -> str:
    """Build a useful entry title from dictated notes."""

    explicit = _first_match(text, [r"\btitle\s*[:\-]\s*(.+?)(?:\.|\n|$)", r"\bcalled\s+(.+?)(?:\.|\n|$)"])
    if explicit:
        return explicit
    if experiment_id and treatments:
        return f"{experiment_id}: {' + '.join(treatments[:3])}"
    if experiment_id:
        return experiment_id
    return "Untitled experiment draft"


def _date(text: str) -> str | None:
    """Extract a date, using today's local date when dictated as today."""

    explicit = _first_match(
        text,
        [
            r"\bdate\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
            r"\bdate\s*[:\-]\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})",
        ],
    )
    if explicit:
        return explicit
    if re.search(r"\btoday\b", text, re.I):
        return date.today().isoformat()
    return None


def _differentiation_day(raw_notes: str, timing: list[str]) -> str | None:
    """Extract the most specific differentiation day or day window."""

    explicit = _first_match(
        raw_notes,
        [
            r"\bdifferentiation day\s*[:\-]?\s*(D?\d{1,3})",
            r"\bday\s*[:\-]?\s*(D?\d{1,3})\b",
            r"\b(D\d{1,3})\b",
        ],
    )
    if explicit:
        return explicit.upper() if explicit.lower().startswith("d") else f"D{explicit}"
    return timing[0] if timing else None


def _issues(raw_notes: str) -> str | None:
    """Extract deviations, issues, or troubleshooting notes."""

    return _first_match(
        raw_notes,
        [
            r"\b(?:issues?|deviations?|problems?)\s*[:\-]\s*(.+?)(?:\.|\n|$)",
            r"\b(?:issue|deviation|problem)\s+was\s+(.+?)(?:\.|\n|$)",
            r"\bbackground was\s+(.+?)(?:\.|\n|$)",
        ],
    )


def _structured_entry(raw_notes: str, template: EntryTemplate) -> dict[str, Any]:
    """Parse dictated notes with deterministic local rules."""

    known_compounds = [
        "SAG",
        "BMP4",
        "DMSO",
        "GRK inhibitor",
        "GRKi",
        "retinoic acid",
        "CHIR",
        "FGF",
        "SHH",
    ]
    known_readouts = [
        "brightfield",
        "confocal",
        "immunostaining",
        "RNA-seq",
        "qPCR",
        "flow cytometry",
        "SIX6",
        "BRN3B",
        "DAPI",
        "PAX6",
        "RAX",
        "VSX2",
    ]

    treatments = _terms(raw_notes, known_compounds)
    treatments.extend(
        _list_from_matches(
            raw_notes,
            [
                r"\btreat(?:ment|ments)?\s*[:\-]\s*(.+?)(?:\.|\n|$)",
                r"\btreated with\s+(.+?)(?:\.|\n|$)",
            ],
        )
    )
    treatments = sorted(set(treatments))

    experiment_id = _experiment_id(raw_notes)
    timing = _list_from_matches(
        raw_notes,
        [
            r"\b(day\s*\d+(?:\s*(?:to|-|through)\s*day\s*\d+)?)",
            r"\b(D\d{1,3}(?:\s*(?:to|-|through)\s*D\d{1,3})?)",
            r"\bfrom\s+(D?\d{1,3})\s+(?:to|through|-)\s+(D?\d{1,3})",
        ],
    )
    timing = [re.sub(r"\s+", " ", value) for value in timing]

    concentrations = _list_from_matches(
        raw_notes,
        [
            r"\b([0-9]+(?:\.[0-9]+)?\s*(?:nM|uM|µM|mM|ng/mL|ug/mL|µg/mL))",
            r"\bconcentration[s]?\s*[:\-]\s*(.+?)(?:\.|\n|$)",
        ],
    )

    readouts = _terms(raw_notes, known_readouts)
    readouts.extend(
        _list_from_matches(
            raw_notes,
            [
                r"\breadouts?\s*[:\-]\s*(.+?)(?:\.|\n|$)",
                r"\bmeasure\s+(.+?)(?:\.|\n|$)",
                r"\bstain(?:ing)?\s+for\s+(.+?)(?:\.|\n|$)",
            ],
        )
    )

    treatment_schedule = _first_match(
        raw_notes,
        [
            r"\btreatment schedule\s*[:\-]\s*(.+?)(?:\.|\n|$)",
            r"\btreat(?:ed)?\s+with\s+(.+?)(?:\.|\n|$)",
            r"\bfrom\s+(D?\d{1,3})\s+(?:to|through|-)\s+(D?\d{1,3})",
        ],
    )
    if not treatment_schedule and treatments:
        treatment_schedule = ", ".join(treatments)

    return {
        "title": _title(raw_notes, experiment_id, treatments),
        "experiment_id": experiment_id,
        "objective": _first_match(raw_notes, [r"\bobjective\s*[:\-]\s*(.+?)(?:\.|\n|$)", r"\bto test\s+(.+?)(?:\.|\n|$)"]),
        "date": _date(raw_notes),
        "researcher": _first_match(
            raw_notes,
            [
                r"\bresearcher\s*[:\-]\s*(.+?)(?:\.|\n|$)",
                r"\bresearcher\s+([A-Z][A-Za-z .-]+?)(?:\.|\n|$)",
                r"\bby\s+([A-Z][A-Za-z .-]+)(?:\.|\n|$)",
            ],
        ),
        "cell_line": _first_match(raw_notes, [r"\bcell line\s*[:\-]?\s*(.+?)(?:\.|\n|$)", r"\busing\s+(.+?iPSC.+?)(?:\.|\n|$)"]),
        "organoid_batch": _first_match(raw_notes, [r"\borganoid batch\s*[:\-]?\s*([A-Za-z0-9_-]+)", r"\bbatch\s*[:\-]?\s*([A-Za-z0-9_-]+)"]),
        "differentiation_day": _differentiation_day(raw_notes, sorted(set(timing))),
        "conditions": _list_from_matches(raw_notes, [r"\bconditions?\s*[:\-]\s*(.+?)(?:\.|\n|$)", r"\bcondition is\s+(.+?)(?:\.|\n|$)"]),
        "treatment_schedule": treatment_schedule,
        "reagents_concentrations": _unique_list([*treatments, *concentrations]),
        "controls": _list_from_matches(
            raw_notes,
            [
                r"\bcontrols?\s*[:\-]\s*(.+?)(?:\.|\n|$)",
                r"\bcontrol is\s+(.+?)(?:\.|\n|$)",
                r"\b([A-Za-z0-9 +/_-]+\s+control)\b",
                r"\b([A-Za-z0-9 +/_-]+\s+vehicle control)\b",
            ],
        ),
        "planned_readouts": sorted(set(readouts)),
        "observations": _first_match(raw_notes, [r"\bobservations?\s*[:\-]\s*(.+?)(?:\bnext steps?\b|\n\n|$)", r"\bobserved\s+(.+?)(?:\.|\n|$)"]),
        "issues_deviations": _issues(raw_notes),
        "next_steps": _first_match(raw_notes, [r"\bnext steps?\s*[:\-]?\s+(.+?)(?:\.|\n|$)", r"\bnext[, ]+(.+?)(?:\.|\n|$)"]),
        "template": template.id,
        "template_name": template.name,
        # Backward-compatible aliases for earlier UI/docs consumers.
        "treatments": treatments,
        "concentrations": concentrations,
        "timing_differentiation_days": sorted(set(timing)),
    }


def _unique_list(values: list[str]) -> list[str]:
    """Return sorted unique non-empty string values."""

    return sorted({str(value).strip() for value in values if str(value).strip()})


def _format_value(value: Any) -> str:
    """Format structured values for Markdown."""

    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "Not captured"
    return str(value) if value else "Not captured"


def _markdown_entry(structured: dict[str, Any], raw_notes: str, template: EntryTemplate) -> str:
    """Render a reviewable notebook entry in Markdown."""

    lines = [
        f"# {structured['title']}",
        "",
        "> ResearchOS generated draft. Review before copying, downloading, or future OneNote save.",
        "",
        "## Entry metadata",
        "",
        f"- Template: {template.name}",
        f"- Experiment ID: {_format_value(structured['experiment_id'])}",
        f"- Date: {_format_value(structured['date'])}",
        f"- Researcher: {_format_value(structured['researcher'])}",
        f"- Objective: {_format_value(structured['objective'])}",
        "",
        "## Sample context",
        "",
        f"- Cell line: {_format_value(structured['cell_line'])}",
        f"- Organoid batch: {_format_value(structured['organoid_batch'])}",
        f"- Differentiation day: {_format_value(structured['differentiation_day'])}",
        f"- Conditions: {_format_value(structured['conditions'])}",
        "",
        "## Treatment / procedure",
        "",
        f"- Treatment schedule: {_format_value(structured['treatment_schedule'])}",
        f"- Reagents and concentrations: {_format_value(structured['reagents_concentrations'])}",
        f"- Controls: {_format_value(structured['controls'])}",
        "",
        "## Planned readouts",
        "",
        f"- Planned readouts: {_format_value(structured['planned_readouts'])}",
        "",
        "## Observations",
        "",
        _format_value(structured["observations"]),
        "",
        "## Issues / deviations",
        "",
        _format_value(structured["issues_deviations"]),
        "",
        "## Next steps",
        "",
        _format_value(structured["next_steps"]),
        "",
        "## Raw dictation",
        "",
        raw_notes.strip(),
    ]
    return "\n".join(lines).strip() + "\n"


def _confidence(structured: dict[str, Any]) -> tuple[float, list[str]]:
    """Estimate confidence from field coverage."""

    missing = []
    present = 0
    for field in ENTRY_FIELDS:
        value = structured.get(field)
        if value:
            present += 1
        else:
            missing.append(field)
    return round(present / len(ENTRY_FIELDS), 2), missing


def draft_entry_from_notes(
    raw_notes: str,
    template: str | None = None,
    settings: Settings | None = None,
    use_ai: bool = True,
) -> DraftEntry:
    """Generate a structured, reviewable notebook entry from raw notes."""

    resolved_settings = settings or get_settings()
    resolved_template = _resolve_template(template)
    structured = _structured_entry(raw_notes, resolved_template)
    markdown = _markdown_entry(structured, raw_notes, resolved_template)
    confidence, missing = _confidence(structured)
    provider_name = "local-regex"
    ai_used = False

    if use_ai:
        try:
            provider = get_ai_provider(settings=resolved_settings)
            prompt = (
                "Format this draft as a clean scientific notebook Markdown entry. "
                "Do not invent missing facts. Preserve all structured fields and raw notes.\n\n"
                f"Structured fields:\n{json.dumps(structured, indent=2)}\n\n"
                f"Current Markdown:\n{markdown}"
            )
            markdown = provider.chat(prompt)
            provider_name = provider.provider_name
            ai_used = True
        except AIProviderError:
            provider_name = "local-regex"

    return DraftEntry(
        structured=structured,
        markdown=markdown,
        template=resolved_template.id,
        confidence=confidence,
        missing_fields=missing,
        ai_used=ai_used,
        provider=provider_name,
    )

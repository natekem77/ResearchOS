"""Experiment extraction pipeline.

The current implementation is regex-first and deterministic. The protocol below
also defines the interface future LLM extractors should implement.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

from app.experiments import Experiment
from app.research_document import ResearchDocument


class ExperimentExtractor(Protocol):
    """Interface for regex, LLM, or hybrid experiment extractors."""

    extractor_name: str

    def extract(self, document: ResearchDocument) -> Experiment | None:
        """Return an Experiment extracted from a document, when possible."""


def _first_match(patterns: list[str], text: str) -> str | None:
    """Return the first regex capture found in text."""

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip(" .:-")
    return None


def _unique(values: list[str]) -> list[str]:
    """Return normalized unique strings while preserving order."""

    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        normalized = re.sub(r"\s+", " ", value.strip(" .;:,"))
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            results.append(normalized)
    return results


def _section_after_heading(text: str, heading_names: list[str]) -> str | None:
    """Extract a Markdown section body after one of several headings."""

    heading_pattern = "|".join(re.escape(name) for name in heading_names)
    match = re.search(
        rf"(?ims)^\s*(?:#+\s*)?(?:{heading_pattern})\s*:?\s*$\n(?P<body>.*?)(?=^\s*(?:#+\s+.+|[A-Z][^\n]{{0,80}}:)\s*$|\Z)",
        text,
    )
    if not match:
        return None

    body = match.group("body").strip()
    return body or None


def _line_values(label: str, text: str) -> list[str]:
    """Extract values from Markdown bullet lines like '- Marker: SIX6'."""

    values = re.findall(
        rf"(?im)^\s*[-*]\s*{re.escape(label)}s?\s*:\s*(.+)$",
        text,
    )
    return _unique(values)


def _entity_hits(terms: list[str], text: str) -> list[str]:
    """Return known scientific terms present in the document text."""

    hits = []
    for term in terms:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.IGNORECASE):
            hits.append(term)
    return _unique(hits)


class RegexExperimentExtractor:
    """Regex-first extractor for lab-note style Markdown and notebook text."""

    extractor_name = "regex"

    def extract(self, document: ResearchDocument) -> Experiment | None:
        """Extract a structured experiment when the document looks experiment-like."""

        text = document.content
        date = _first_match([r"^\s*Date\s*:\s*(.+)$"], text)
        explicit_experiment_id = _first_match(
            [
                r"^\s*Experiment\s+ID\s*:\s*(.+)$",
                r"^\s*Experiment\s*:\s*(.+)$",
            ],
            text,
        )
        has_experiment_signal = bool(
            explicit_experiment_id
            or date
            or re.search(r"\b(experiment|protocol|staining|treatment|markers?)\b", text, re.I)
        )
        if not has_experiment_signal:
            return None

        digest = hashlib.sha256(document.id.encode("utf-8")).hexdigest()[:16]
        experiment_id = explicit_experiment_id or f"EXP-{digest}"

        compounds = _unique(
            _line_values("compound", text)
            + _entity_hits(["SAG", "BMP4", "DMSO"], text)
        )
        treatments = _unique(
            _line_values("treatment", text)
            + re.findall(r"(?i)\b([A-Z0-9.-]+\s*-?treated)\b", text)
            + re.findall(r"(?im)^\s*[-*]\s*Control\s*:\s*(.+)$", text)
        )
        concentrations = _unique(
            re.findall(r"(?i)\b\d+(?:\.\d+)?\s*(?:nM|uM|µM|mM|mg/mL|ug/mL|µg/mL)\b", text)
        )
        time_points = _unique(
            re.findall(r"(?i)\bD\d+(?:\s*(?:to|-|through)\s*D?\d+)?\b", text)
            + re.findall(r"(?i)\b\d+\s*(?:hours?|hrs?|days?)\b", text)
        )
        markers = _unique(
            _line_values("marker", text)
            + _entity_hits(["SIX6", "BRN3B", "DAPI"], text)
        )
        antibodies = _unique(
            _line_values("antibody", text)
            + re.findall(r"(?i)\b(primary antibody|secondary antibody|secondary-only control)\b", text)
        )
        imaging_methods = _unique(
            _entity_hits(
                ["brightfield", "fluorescence", "confocal", "immunostaining", "microscopy"],
                text,
            )
        )
        sequencing = _unique(
            _entity_hits(["RNA-seq", "scRNA-seq", "single-cell RNA-seq", "ATAC-seq"], text)
        )

        notes = _section_after_heading(
            text,
            ["Notes", "Observations", "Result summary", "Important handling notes"],
        )
        conclusions = _section_after_heading(
            text,
            ["Conclusion", "Conclusions", "Interpretation", "Preliminary interpretation"],
        )

        return Experiment(
            id=f"experiment:{digest}",
            source_document_id=document.id,
            source_provider=document.provider,
            title=document.title,
            experiment_id=experiment_id,
            date=date,
            researcher=_first_match([r"^\s*Researcher\s*:\s*(.+)$"], text),
            cell_line=_first_match([r"^\s*[-*]?\s*Cell line\s*:\s*(.+)$"], text),
            organoid_batch=_first_match(
                [
                    r"^\s*Organoid batch\s*:\s*(.+)$",
                    r"^\s*Batch\s*:\s*(.+)$",
                ],
                text,
            ),
            compounds=compounds,
            treatments=treatments,
            concentrations=concentrations,
            time_points=time_points,
            markers=markers,
            antibodies=antibodies,
            imaging_methods=imaging_methods,
            sequencing=sequencing,
            notes=notes,
            conclusions=conclusions,
        )


class LLMExperimentExtractor:
    """Placeholder interface for future LLM-backed extraction."""

    extractor_name = "llm-placeholder"

    def extract(self, document: ResearchDocument) -> Experiment | None:
        """LLM extraction is intentionally not implemented in this milestone."""

        raise NotImplementedError("LLM experiment extraction is a future provider.")


def extract_experiment(document: ResearchDocument) -> Experiment | None:
    """Extract one experiment from a document with the default regex pipeline."""

    return RegexExperimentExtractor().extract(document)

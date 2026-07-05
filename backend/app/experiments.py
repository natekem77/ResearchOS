"""Structured experiment models for ResearchOS."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Experiment:
    """Provider-agnostic structured experiment extracted from a document."""

    id: str
    source_document_id: str
    source_provider: str
    title: str
    experiment_id: str | None = None
    date: str | None = None
    researcher: str | None = None
    cell_line: str | None = None
    organoid_batch: str | None = None
    compounds: list[str] = field(default_factory=list)
    treatments: list[str] = field(default_factory=list)
    concentrations: list[str] = field(default_factory=list)
    time_points: list[str] = field(default_factory=list)
    markers: list[str] = field(default_factory=list)
    antibodies: list[str] = field(default_factory=list)
    imaging_methods: list[str] = field(default_factory=list)
    sequencing: list[str] = field(default_factory=list)
    notes: str | None = None
    conclusions: str | None = None

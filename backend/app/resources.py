"""Research resource models and normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


RESOURCE_TYPES = [
    "compound",
    "antibody",
    "marker",
    "gene",
    "protein",
    "cell_line",
    "organoid_line",
    "media",
    "growth_factor",
    "small_molecule",
    "reagent",
    "primer",
    "vector",
    "plasmid",
    "consumable",
    "equipment",
    "other",
]


RESOURCE_ENTITY_TYPES = {
    "compound": "compound",
    "growth_factor": "compound",
    "small_molecule": "compound",
    "antibody": "antibody",
    "marker": "marker",
    "gene": "gene",
    "protein": "protein",
    "cell_line": "cell_line",
    "organoid_line": "organoid_batch",
    "media": "reagent",
    "reagent": "reagent",
    "primer": "primer",
    "vector": "vector",
    "plasmid": "plasmid",
    "consumable": "consumable",
    "equipment": "equipment",
    "other": "unknown_scientific_term",
}


@dataclass(frozen=True)
class Resource:
    """Reusable laboratory material or scientific resource."""

    resource_id: str
    resource_type: str
    name: str
    aliases: list[str] = field(default_factory=list)
    vendor: str | None = None
    catalog_number: str | None = None
    lot_number: str | None = None
    rrid: str | None = None
    storage_location: str | None = None
    concentration: str | None = None
    units: str | None = None
    expiration: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_resource_type(resource_type: str | None) -> str:
    """Normalize API labels such as `Cell Line` into stable IDs."""

    normalized = (resource_type or "other").strip().lower().replace(" ", "_").replace("-", "_")
    return normalized if normalized in RESOURCE_TYPES else "other"


def resource_entity_type(resource_type: str) -> str:
    """Return the Knowledge Graph entity type for a resource type."""

    return RESOURCE_ENTITY_TYPES.get(normalize_resource_type(resource_type), "unknown_scientific_term")

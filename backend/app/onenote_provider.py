"""Read-only OneNote metadata provider backed by Microsoft Graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from app.graph_client import graph_get_all_pages


@dataclass(frozen=True)
class OneNoteMetadata:
    """Clean metadata shape returned by OneNote listing endpoints."""

    id: str
    displayName: str | None
    title: str | None
    createdDateTime: str | None
    lastModifiedDateTime: str | None


def _normalize_metadata(raw_item: dict[str, Any]) -> OneNoteMetadata:
    """Normalize Microsoft Graph OneNote metadata into a stable API shape."""

    display_name = raw_item.get("displayName")
    title = raw_item.get("title")

    return OneNoteMetadata(
        id=str(raw_item.get("id", "")),
        displayName=str(display_name) if display_name is not None else None,
        title=str(title) if title is not None else None,
        createdDateTime=_optional_string(raw_item.get("createdDateTime")),
        lastModifiedDateTime=_optional_string(raw_item.get("lastModifiedDateTime")),
    )


def _optional_string(value: Any) -> str | None:
    """Convert optional Microsoft Graph scalar values into API-safe strings."""

    return str(value) if value is not None else None


def _quote_graph_id(graph_id: str) -> str:
    """Quote Graph IDs before placing them inside endpoint paths."""

    return quote(graph_id, safe="")


def list_notebooks() -> list[OneNoteMetadata]:
    """List OneNote notebooks for the signed-in user without fetching content."""

    raw_items = graph_get_all_pages(
        "/me/onenote/notebooks",
        query_params={
            "$select": "id,displayName,createdDateTime,lastModifiedDateTime",
        },
    )
    return [_normalize_metadata(item) for item in raw_items]


def list_sections(notebook_id: str | None = None) -> list[OneNoteMetadata]:
    """List OneNote sections, optionally scoped to a notebook."""

    if notebook_id:
        path = f"/me/onenote/notebooks/{_quote_graph_id(notebook_id)}/sections"
    else:
        path = "/me/onenote/sections"

    raw_items = graph_get_all_pages(
        path,
        query_params={
            "$select": "id,displayName,createdDateTime,lastModifiedDateTime",
        },
    )
    return [_normalize_metadata(item) for item in raw_items]


def list_pages(section_id: str | None = None) -> list[OneNoteMetadata]:
    """List OneNote pages, optionally scoped to a section, without page content."""

    if section_id:
        path = f"/me/onenote/sections/{_quote_graph_id(section_id)}/pages"
    else:
        path = "/me/onenote/pages"

    raw_items = graph_get_all_pages(
        path,
        query_params={
            "$select": "id,title,createdDateTime,lastModifiedDateTime",
        },
    )
    return [_normalize_metadata(item) for item in raw_items]

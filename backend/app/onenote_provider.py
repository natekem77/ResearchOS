"""Read-only OneNote metadata provider backed by Microsoft Graph."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote

from app.graph_client import graph_get_all_pages, graph_get_text
from app.research_document import ResearchDocument


@dataclass(frozen=True)
class OneNoteMetadata:
    """Clean metadata shape returned by OneNote listing endpoints."""

    id: str
    displayName: str | None
    title: str | None
    createdDateTime: str | None
    lastModifiedDateTime: str | None


class _OneNoteHTMLTextParser(HTMLParser):
    """Small OneNote HTML to readable text converter.

    OneNote page content is HTML. The MVP sync stores clean text/Markdown-like
    content so the existing chunking, search, and extraction pipeline can work
    without browser-specific markup.
    """

    block_tags = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "p",
        "pre",
        "section",
        "table",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Preserve useful structure and skip non-content tags."""

        normalized = tag.lower()
        if normalized in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if normalized in self.block_tags:
            self.parts.append("\n")
        if normalized == "li":
            self.parts.append("- ")
        if normalized == "img":
            attrs_dict = dict(attrs)
            alt_text = attrs_dict.get("alt")
            if alt_text:
                self.parts.append(f"[Image: {alt_text}]")
        if normalized == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href")
            if href:
                self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        """Close skipped tags and add line breaks after block-level content."""

        normalized = tag.lower()
        if normalized in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if normalized in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        """Collect visible text content."""

        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        """Return normalized Markdown-like text."""

        raw_text = "".join(self.parts)
        raw_text = raw_text.replace("\xa0", " ")
        raw_text = re.sub(r"[ \t]+", " ", raw_text)
        raw_text = re.sub(r" *\n *", "\n", raw_text)
        raw_text = re.sub(r"\n{3,}", "\n\n", raw_text)
        return raw_text.strip()


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


def _document_id_for_page(page_id: str) -> str:
    """Build a stable ResearchOS document ID for a OneNote page."""

    digest = hashlib.sha256(page_id.encode("utf-8")).hexdigest()[:16]
    return f"onenote:{digest}"


def _html_to_text(html: str) -> str:
    """Convert OneNote page HTML to clean searchable text."""

    parser = _OneNoteHTMLTextParser()
    parser.feed(html)
    parser.close()
    return parser.text()


def _metadata_lookup(items: list[dict[str, Any]], name_key: str) -> dict[str, dict[str, str]]:
    """Create an ID-keyed lookup containing Graph IDs and display names."""

    lookup: dict[str, dict[str, str]] = {}
    for item in items:
        item_id = _optional_string(item.get("id"))
        if not item_id:
            continue

        name = _optional_string(item.get(name_key))
        lookup[item_id] = {
            "id": item_id,
            "name": name or item_id,
        }
    return lookup


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


def sync_onenote_pages() -> list[ResearchDocument]:
    """Fetch OneNote pages read-only and map them to ResearchDocuments.

    This function only performs Microsoft Graph GET requests. It does not write
    to OneNote and does not request write permissions.
    """

    notebooks = graph_get_all_pages(
        "/me/onenote/notebooks",
        query_params={
            "$select": "id,displayName,createdDateTime,lastModifiedDateTime",
        },
    )
    notebook_lookup = _metadata_lookup(notebooks, "displayName")

    documents: list[ResearchDocument] = []
    for notebook in notebooks:
        notebook_id = _optional_string(notebook.get("id"))
        if not notebook_id:
            continue

        sections = graph_get_all_pages(
            f"/me/onenote/notebooks/{_quote_graph_id(notebook_id)}/sections",
            query_params={
                "$select": "id,displayName,createdDateTime,lastModifiedDateTime",
            },
        )
        section_lookup = _metadata_lookup(sections, "displayName")

        for section in sections:
            section_id = _optional_string(section.get("id"))
            if not section_id:
                continue

            pages = graph_get_all_pages(
                f"/me/onenote/sections/{_quote_graph_id(section_id)}/pages",
                query_params={
                    "$select": "id,title,createdDateTime,lastModifiedDateTime,contentUrl,links",
                },
            )

            for page in pages:
                page_id = _optional_string(page.get("id"))
                if not page_id:
                    continue

                html = graph_get_text(f"/me/onenote/pages/{_quote_graph_id(page_id)}/content")
                content = _html_to_text(html)
                title = _optional_string(page.get("title")) or "Untitled OneNote page"
                content_url = _optional_string(page.get("contentUrl"))
                source_url = content_url or _page_web_url(page)

                documents.append(
                    ResearchDocument(
                        id=_document_id_for_page(page_id),
                        provider="onenote",
                        source_id=page_id,
                        title=title,
                        content=content,
                        source_url=source_url,
                        created_at=_optional_string(page.get("createdDateTime")),
                        updated_at=_optional_string(page.get("lastModifiedDateTime")),
                        metadata={
                            "notebook_id": notebook_lookup[notebook_id]["id"],
                            "notebook_name": notebook_lookup[notebook_id]["name"],
                            "section_id": section_lookup[section_id]["id"],
                            "section_name": section_lookup[section_id]["name"],
                            "page_id": page_id,
                            "page_title": title,
                            "createdDateTime": _optional_string(page.get("createdDateTime")) or "",
                            "lastModifiedDateTime": _optional_string(page.get("lastModifiedDateTime")) or "",
                            "contentUrl": content_url or "",
                        },
                    )
                )

    return documents


def _page_web_url(page: dict[str, Any]) -> str | None:
    """Return a OneNote web URL from Graph page links when available."""

    links = page.get("links")
    if not isinstance(links, dict):
        return None

    one_note_web_url = links.get("oneNoteWebUrl")
    if not isinstance(one_note_web_url, dict):
        return None

    href = one_note_web_url.get("href")
    return str(href) if href else None

"""Deterministic text extraction for uploaded protocol source documents."""

from __future__ import annotations

import csv
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree


@dataclass(frozen=True)
class ExtractedProtocolDocument:
    text: str
    source_type: str
    warnings: list[str] = field(default_factory=list)
    tables: list[dict[str, object]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


def extract_protocol_document(path: Path, *, filename: str, mime_type: str | None = None) -> ExtractedProtocolDocument:
    extension = Path(filename or path.name).suffix.lower()
    if extension == ".docx":
        return _extract_docx(path)
    if extension == ".pdf" or mime_type == "application/pdf":
        return _extract_pdf(path)
    if extension in {".txt", ".md"}:
        return ExtractedProtocolDocument(text=path.read_text(encoding="utf-8", errors="replace"), source_type="txt")
    if extension == ".rtf":
        return ExtractedProtocolDocument(text=_rtf_to_text(path.read_text(encoding="utf-8", errors="replace")), source_type="rtf")
    if extension == ".csv":
        return _extract_csv(path)
    if extension == ".xlsx":
        return _extract_xlsx(path)
    if extension == ".xls":
        return ExtractedProtocolDocument(
            text="",
            source_type="xls",
            warnings=["Legacy XLS binary extraction requires conversion to XLSX or CSV before structured extraction."],
        )
    return ExtractedProtocolDocument(text="", source_type=extension.removeprefix(".") or "document", warnings=["Unsupported protocol document type for extraction."])


def _extract_pdf(path: Path) -> ExtractedProtocolDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF extraction requires pypdf. Install backend requirements first.") from exc

    reader = PdfReader(str(path))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {index}]\n{text.strip()}")
    if not pages:
        return ExtractedProtocolDocument(
            text="",
            source_type="pdf",
            warnings=["No embedded PDF text was found. OCR is required before structured extraction."],
            metadata={"page_count": len(reader.pages), "ocr_required": True},
        )
    return ExtractedProtocolDocument(
        text="\n\n".join(pages),
        source_type="pdf",
        metadata={"page_count": len(reader.pages), "ocr_required": False},
    )


def _extract_docx(path: Path) -> ExtractedProtocolDocument:
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(document_xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    body = root.find("w:body", ns)
    if body is None:
        return ExtractedProtocolDocument(text="", source_type="docx", warnings=["DOCX document body was empty."])

    parts: list[str] = []
    tables: list[dict[str, object]] = []
    table_index = 0
    for child in list(body):
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = _docx_text(child, ns).strip()
            if text:
                parts.append(text)
        elif tag == "tbl":
            table_index += 1
            rows = _docx_table(child, ns)
            if rows:
                tables.append({"table_index": table_index, "rows": rows})
                parts.append(f"[Table {table_index}]")
                parts.extend("\t".join(cell for cell in row) for row in rows)
    return ExtractedProtocolDocument(
        text="\n".join(parts),
        source_type="docx",
        tables=tables,
        metadata={"table_count": len(tables)},
    )


def _docx_text(element: ElementTree.Element, ns: dict[str, str]) -> str:
    chunks: list[str] = []
    for node in element.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "t" and node.text:
            chunks.append(node.text)
        elif tag in {"tab"}:
            chunks.append("\t")
        elif tag in {"br", "cr"}:
            chunks.append("\n")
    return "".join(chunks)


def _docx_table(table: ElementTree.Element, ns: dict[str, str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.findall("w:tr", ns):
        cells: list[str] = []
        for cell in row.findall("w:tc", ns):
            paragraphs = [_docx_text(paragraph, ns).strip() for paragraph in cell.findall("w:p", ns)]
            cells.append("\n".join(text for text in paragraphs if text))
        if any(cell.strip() for cell in cells):
            rows.append(cells)
    return rows


def _extract_csv(path: Path) -> ExtractedProtocolDocument:
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        rows = [row for row in csv.reader(handle)]
    text = "\n".join("\t".join(cell.strip() for cell in row) for row in rows)
    tables = [{"table_index": 1, "rows": rows}] if rows else []
    return ExtractedProtocolDocument(text=text, source_type="csv", tables=tables, metadata={"table_count": len(tables)})


def _extract_xlsx(path: Path) -> ExtractedProtocolDocument:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        shared = _xlsx_shared_strings(archive) if "xl/sharedStrings.xml" in names else []
        sheet_names = sorted(name for name in names if re.match(r"xl/worksheets/sheet\d+\.xml", name))
        tables: list[dict[str, object]] = []
        parts: list[str] = []
        for index, sheet_name in enumerate(sheet_names, start=1):
            rows = _xlsx_sheet_rows(archive.read(sheet_name), shared)
            if not rows:
                continue
            tables.append({"table_index": index, "sheet": Path(sheet_name).stem, "rows": rows})
            parts.append(f"[Sheet {index}]")
            parts.extend("\t".join(cell for cell in row) for row in rows)
    return ExtractedProtocolDocument(
        text="\n".join(parts),
        source_type="xlsx",
        tables=tables,
        metadata={"table_count": len(tables)},
    )


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values: list[str] = []
    for item in root.findall("a:si", ns):
        values.append("".join(text.text or "" for text in item.findall(".//a:t", ns)))
    return values


def _xlsx_sheet_rows(sheet_xml: bytes, shared: list[str]) -> list[list[str]]:
    root = ElementTree.fromstring(sheet_xml)
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows: list[list[str]] = []
    for row in root.findall(".//a:row", ns):
        cells: list[str] = []
        for cell in row.findall("a:c", ns):
            value = cell.find("a:v", ns)
            raw = value.text if value is not None else ""
            if cell.get("t") == "s" and raw.isdigit() and int(raw) < len(shared):
                cells.append(shared[int(raw)])
            else:
                cells.append(raw or "")
        if any(cell.strip() for cell in cells):
            rows.append(cells)
    return rows


def _rtf_to_text(value: str) -> str:
    text = re.sub(r"\\'[0-9a-fA-F]{2}", "", value)
    text = re.sub(r"\\par[d]?", "\n", text)
    text = re.sub(r"\\[a-zA-Z]+\d* ?", "", text)
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()

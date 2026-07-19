"""Deterministic text extraction for uploaded protocol source documents."""

from __future__ import annotations

import csv
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree


@dataclass(frozen=True)
class ProtocolSourceBlock:
    block_id: str
    type: str
    text: str
    order: int
    heading_path: list[str] = field(default_factory=list)
    page: int | None = None
    columns: dict[str, str] | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "block_id": self.block_id,
            "type": self.type,
            "text": self.text,
            "order": self.order,
            "heading_path": self.heading_path,
            "metadata": self.metadata,
        }
        if self.page is not None:
            payload["page"] = self.page
        if self.columns is not None:
            payload["columns"] = self.columns
        return payload


@dataclass(frozen=True)
class ExtractedProtocolDocument:
    text: str
    source_type: str
    warnings: list[str] = field(default_factory=list)
    tables: list[dict[str, object]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    blocks: list[dict[str, object]] = field(default_factory=list)


def extract_protocol_document(path: Path, *, filename: str, mime_type: str | None = None) -> ExtractedProtocolDocument:
    extension = Path(filename or path.name).suffix.lower()
    if extension == ".docx":
        return _extract_docx(path)
    if extension == ".pdf" or mime_type == "application/pdf":
        return _extract_pdf(path)
    if extension in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        return ExtractedProtocolDocument(text=text, source_type="txt", blocks=_text_blocks(text))
    if extension == ".rtf":
        text = _rtf_to_text(path.read_text(encoding="utf-8", errors="replace"))
        return ExtractedProtocolDocument(text=text, source_type="rtf", blocks=_text_blocks(text))
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
    blocks: list[ProtocolSourceBlock] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            stripped = text.strip()
            pages.append(f"[Page {index}]\n{stripped}")
            blocks.append(
                ProtocolSourceBlock(
                    block_id=f"page-{index}",
                    type="page_text",
                    text=stripped,
                    order=len(blocks) + 1,
                    page=index,
                )
            )
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
        blocks=[block.to_dict() for block in blocks],
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
    blocks: list[ProtocolSourceBlock] = []
    tables: list[dict[str, object]] = []
    table_index = 0
    heading_path: list[str] = []
    for child in list(body):
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = _docx_text(child, ns).strip()
            if text:
                style = _docx_paragraph_style(child, ns)
                if _is_heading_text(text) or style.lower().startswith("heading"):
                    level = _heading_level(style) or _heading_level_from_text(text)
                    heading_path = [*heading_path[: max(level - 1, 0)], text]
                    block_type = "heading"
                else:
                    block_type = "paragraph"
                parts.append(text)
                blocks.append(
                    ProtocolSourceBlock(
                        block_id=f"p-{len(blocks) + 1}",
                        type=block_type,
                        text=text,
                        order=len(blocks) + 1,
                        heading_path=heading_path if block_type != "heading" else heading_path[:-1],
                        metadata={"style": style} if style else {},
                    )
                )
        elif tag == "tbl":
            table_index += 1
            rows = _docx_table(child, ns)
            if rows:
                tables.append({"table_index": table_index, "rows": rows})
                parts.append(f"[Table {table_index}]")
                parts.extend("\t".join(cell for cell in row) for row in rows)
                header = rows[0] if rows else []
                for row_index, row in enumerate(rows, start=1):
                    columns = {
                        (header[index] if index < len(header) and header[index].strip() else f"column_{index + 1}"): cell
                        for index, cell in enumerate(row)
                    }
                    blocks.append(
                        ProtocolSourceBlock(
                            block_id=f"table-{table_index}-row-{row_index}",
                            type="table_row",
                            text="\t".join(row),
                            order=len(blocks) + 1,
                            heading_path=heading_path,
                            columns=columns,
                            metadata={
                                "table_index": table_index,
                                "row_index": row_index,
                                "is_header": row_index == 1,
                            },
                        )
                    )
    return ExtractedProtocolDocument(
        text="\n".join(parts),
        source_type="docx",
        tables=tables,
        metadata={"table_count": len(tables)},
        blocks=[block.to_dict() for block in blocks],
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


def _docx_paragraph_style(paragraph: ElementTree.Element, ns: dict[str, str]) -> str:
    style = paragraph.find("w:pPr/w:pStyle", ns)
    return style.get(f"{{{ns['w']}}}val", "") if style is not None else ""


def _heading_level(style: str) -> int | None:
    match = re.search(r"heading\s*(\d+)|Heading(\d+)", style, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group(1) or match.group(2)
    return max(1, min(int(value), 6))


def _heading_level_from_text(text: str) -> int:
    return 1 if len(text) < 80 else 2


def _is_heading_text(text: str) -> bool:
    cleaned = text.strip().rstrip(":")
    if not cleaned or len(cleaned) > 80:
        return False
    return cleaned.lower() in {
        "timeline",
        "procedure",
        "procedures",
        "materials",
        "material",
        "reagents",
        "reagent",
        "media",
        "medium",
        "media preparation",
        "expected results",
        "qc",
        "quality control",
        "troubleshooting",
        "notes",
    }


def _extract_csv(path: Path) -> ExtractedProtocolDocument:
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        rows = [row for row in csv.reader(handle)]
    text = "\n".join("\t".join(cell.strip() for cell in row) for row in rows)
    tables = [{"table_index": 1, "rows": rows}] if rows else []
    blocks = _table_blocks(rows, heading_path=["CSV"], table_index=1)
    return ExtractedProtocolDocument(text=text, source_type="csv", tables=tables, metadata={"table_count": len(tables)}, blocks=blocks)


def _extract_xlsx(path: Path) -> ExtractedProtocolDocument:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        shared = _xlsx_shared_strings(archive) if "xl/sharedStrings.xml" in names else []
        sheet_names = sorted(name for name in names if re.match(r"xl/worksheets/sheet\d+\.xml", name))
        tables: list[dict[str, object]] = []
        parts: list[str] = []
        blocks: list[dict[str, object]] = []
        for index, sheet_name in enumerate(sheet_names, start=1):
            rows = _xlsx_sheet_rows(archive.read(sheet_name), shared)
            if not rows:
                continue
            sheet = Path(sheet_name).stem
            tables.append({"table_index": index, "sheet": sheet, "rows": rows})
            parts.append(f"[Sheet {index}]")
            parts.extend("\t".join(cell for cell in row) for row in rows)
            blocks.extend(_table_blocks(rows, heading_path=[sheet], table_index=index, order_offset=len(blocks)))
    return ExtractedProtocolDocument(
        text="\n".join(parts),
        source_type="xlsx",
        tables=tables,
        metadata={"table_count": len(tables)},
        blocks=blocks,
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


def _text_blocks(text: str) -> list[dict[str, object]]:
    heading_path: list[str] = []
    blocks: list[ProtocolSourceBlock] = []
    for line in [line.strip() for line in text.splitlines() if line.strip()]:
        if _is_heading_text(line):
            heading_path = [line.rstrip(":")]
            block_type = "heading"
        else:
            block_type = "paragraph"
        blocks.append(
            ProtocolSourceBlock(
                block_id=f"p-{len(blocks) + 1}",
                type=block_type,
                text=line,
                order=len(blocks) + 1,
                heading_path=heading_path if block_type != "heading" else heading_path[:-1],
            )
        )
    return [block.to_dict() for block in blocks]


def _table_blocks(
    rows: list[list[str]],
    *,
    heading_path: list[str],
    table_index: int,
    order_offset: int = 0,
) -> list[dict[str, object]]:
    if not rows:
        return []
    header = rows[0]
    blocks: list[ProtocolSourceBlock] = []
    for row_index, row in enumerate(rows, start=1):
        columns = {
            (header[index] if index < len(header) and header[index].strip() else f"column_{index + 1}"): cell
            for index, cell in enumerate(row)
        }
        blocks.append(
            ProtocolSourceBlock(
                block_id=f"table-{table_index}-row-{row_index}",
                type="table_row",
                text="\t".join(row),
                order=order_offset + len(blocks) + 1,
                heading_path=heading_path,
                columns=columns,
                metadata={"table_index": table_index, "row_index": row_index, "is_header": row_index == 1},
            )
        )
    return [block.to_dict() for block in blocks]

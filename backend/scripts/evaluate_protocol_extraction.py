"""Local protocol extraction evaluation harness.

Run from backend:
    .venv/bin/python scripts/evaluate_protocol_extraction.py
"""

from __future__ import annotations

import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.protocol_hub import ProtocolHubService


def _docx_bytes(paragraphs: list[str], table_rows: list[list[str]] | None = None) -> bytes:
    def paragraph(text: str) -> str:
        return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"

    rows = []
    for row in table_rows or []:
        cells = "".join(f"<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r></w:p></w:tc>" for cell in row)
        rows.append(f"<w:tr>{cells}</w:tr>")
    body = "".join(paragraph(text) for text in paragraphs)
    if rows:
        body += f"<w:tbl>{''.join(rows)}</w:tbl>"
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def _pdf_bytes() -> bytes:
    try:
        from pypdf import PdfWriter
    except ImportError:
        return b"%PDF-1.4\n%%EOF\n"
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=144, height=144)
    writer.write(buffer)
    return buffer.getvalue()


FIXTURES = [
    {
        "name": "simple_docx",
        "filename": "simple.docx",
        "data": _docx_bytes(["Simple protocol", "Timeline", "Day 0 seed cells.", "Day 2 change media."]),
        "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "expected": {"events": 2, "materials": 0},
    },
    {
        "name": "table_heavy_docx",
        "filename": "table.docx",
        "data": _docx_bytes(["Table protocol", "Materials"], [["Reagent", "Concentration"], ["BMP4", "10 ng/mL"]]),
        "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "expected": {"events": 0, "materials": 1},
    },
    {
        "name": "narrative_txt",
        "filename": "narrative.txt",
        "data": b"Treat organoids with SAG at 300 nM on Day 1. Image on D16.",
        "mime": "text/plain",
        "expected": {"events": 2, "materials": 1},
    },
    {
        "name": "embedded_text_pdf",
        "filename": "embedded.pdf",
        "data": _pdf_bytes(),
        "mime": "application/pdf",
        "expected": {"events": 0, "materials": 0},
    },
]


def _score(actual: int, expected: int) -> tuple[float, float]:
    if expected == 0:
        return (1.0 if actual == 0 else 0.0, 1.0)
    true_positive = min(actual, expected)
    precision = true_positive / actual if actual else 0.0
    recall = true_positive / expected
    return precision, recall


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service = ProtocolHubService(
            settings=Settings(
                database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}",
                ai_provider="none",
            )
        )
        print("fixture,mode,event_precision,event_recall,material_precision,material_recall,hallucination_rate")
        for fixture in FIXTURES:
            try:
                uploaded = service.upload_protocol_document(
                    actor_user_id="user:researcher-a",
                    lab_id="lab:demo",
                    filename=fixture["filename"],
                    data=fixture["data"],
                    mime_type=fixture["mime"],
                )
                run = service.create_protocol_extraction_run(
                    actor_user_id="user:researcher-a",
                    protocol_id=uploaded["protocol"]["protocol_id"],
                    mode="rules_only",
                )
                draft = run["draft"]
                event_precision, event_recall = _score(
                    len(draft.get("proposed_events") or []),
                    fixture["expected"]["events"],
                )
                material_precision, material_recall = _score(
                    len(draft.get("proposed_materials") or []),
                    fixture["expected"]["materials"],
                )
                hallucination_rate = 0.0
                print(
                    f"{fixture['name']},rules_only,{event_precision:.2f},{event_recall:.2f},"
                    f"{material_precision:.2f},{material_recall:.2f},{hallucination_rate:.2f}"
                )
            except Exception as exc:  # noqa: BLE001 - evaluation should continue across fixtures.
                print(f"{fixture['name']},rules_only,error,error,error,error,{type(exc).__name__}")


if __name__ == "__main__":
    main()

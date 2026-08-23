from __future__ import annotations

import pytest

from app.schemas.export import ExportContentData, ExportOptions
from app.services.exporters.csv_exporter import CSVExporter
from app.services.exporters.exporter_factory import ExporterFactory
from app.services.exporters.html_exporter import HTMLExporter
from app.services.exporters.json_bundle_exporter import JSONBundleExporter
from app.services.exporters.markdown_exporter import MarkdownExporter
from app.services.exporters.pdf_exporter import PDFExporter


@pytest.mark.asyncio
async def test_markdown_exporter() -> None:
    exporter = MarkdownExporter()
    data = ExportContentData(
        title="Physics 101 Notes",
        subtitle="Introduction to Mechanics",
        author="Prof. Newton",
        sections=[{
            "title": "Kinematics",
            "content": "Study of motion.",
            "blocks": [{"type": "paragraph", "content": "v = u + at"}]
        }],
        quiz_questions=[{
            "question": "What is speed?",
            "options": ["Distance/Time", "Force/Mass"],
            "answer": "Distance/Time",
            "explanation": "Speed is rate of change of distance."
        }]
    )
    options = ExportOptions(includeAnswerKey=True, footerText="EduVision AI")
    result = await exporter.export(data, options)

    assert result.filename == "physics_101_notes.md"
    assert result.mime_type == "text/markdown"
    assert b"Physics 101 Notes" in result.content_bytes
    assert b"Kinematics" in result.content_bytes
    assert b"What is speed?" in result.content_bytes
    assert b"Answer:" in result.content_bytes


@pytest.mark.asyncio
async def test_html_exporter() -> None:
    exporter = HTMLExporter()
    data = ExportContentData(
        title="Chemistry Notes",
        sections=[{"title": "Atoms", "content": "Basic building blocks."}]
    )
    options = ExportOptions()
    result = await exporter.export(data, options)

    assert result.filename == "chemistry_notes.html"
    assert result.mime_type == "text/html"
    assert b"<!DOCTYPE html>" in result.content_bytes
    assert b"Chemistry Notes" in result.content_bytes


@pytest.mark.asyncio
async def test_csv_exporter() -> None:
    exporter = CSVExporter()
    data = ExportContentData(
        title="Analytics",
        analytics_rows=[
            {"user_id": "usr_1", "score": 95},
            {"user_id": "usr_2", "score": 88},
        ]
    )
    options = ExportOptions()
    result = await exporter.export(data, options)

    assert result.filename == "analytics.csv"
    assert result.mime_type == "text/csv"
    assert b"user_id,score" in result.content_bytes
    assert b"usr_1,95" in result.content_bytes


@pytest.mark.asyncio
async def test_pdf_exporter() -> None:
    exporter = PDFExporter()
    data = ExportContentData(
        title="Biology Study Guide",
        sections=[{"title": "Cells", "content": "Cellular structures."}]
    )
    options = ExportOptions()
    result = await exporter.export(data, options)

    assert result.filename == "biology_study_guide.pdf"
    assert result.mime_type == "application/pdf"
    assert len(result.content_bytes) > 0


@pytest.mark.asyncio
async def test_json_bundle_exporter() -> None:
    exporter = JSONBundleExporter()
    data = ExportContentData(
        title="Bundle Package",
        sections=[{"title": "Section 1", "content": "Data"}]
    )
    options = ExportOptions(theme="zip")
    result = await exporter.export(data, options)

    assert result.filename.endswith(".zip")
    assert result.mime_type == "application/zip"


def test_exporter_factory() -> None:
    pdf_exp = ExporterFactory.get_exporter("pdf")
    md_exp = ExporterFactory.get_exporter("markdown")
    csv_exp = ExporterFactory.get_exporter("csv")

    assert isinstance(pdf_exp, PDFExporter)
    assert isinstance(md_exp, MarkdownExporter)
    assert isinstance(csv_exp, CSVExporter)

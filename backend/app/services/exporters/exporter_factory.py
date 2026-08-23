from __future__ import annotations

from app.core.exceptions import ValidationError
from app.services.exporters.base_exporter import BaseExporter
from app.services.exporters.csv_exporter import CSVExporter
from app.services.exporters.docx_exporter import DOCXExporter
from app.services.exporters.html_exporter import HTMLExporter
from app.services.exporters.json_bundle_exporter import JSONBundleExporter
from app.services.exporters.markdown_exporter import MarkdownExporter
from app.services.exporters.pdf_exporter import PDFExporter
from app.services.exporters.pptx_exporter import PPTXExporter
from shared.constants import ExportFormat


class ExporterFactory:
    @staticmethod
    def get_exporter(export_format: str) -> BaseExporter:
        fmt = export_format.lower()
        if fmt == ExportFormat.PDF.value:
            return PDFExporter()
        elif fmt in (ExportFormat.MARKDOWN.value, "md"):
            return MarkdownExporter()
        elif fmt == ExportFormat.HTML.value:
            return HTMLExporter()
        elif fmt == ExportFormat.DOCX.value:
            return DOCXExporter()
        elif fmt == ExportFormat.PPTX.value:
            return PPTXExporter()
        elif fmt in ("csv", "tsv"):
            return CSVExporter()
        elif fmt in (ExportFormat.FLASHCARDS.value, ExportFormat.MINDMAP.value, ExportFormat.ZIP.value, "json"):
            return JSONBundleExporter()
        else:
            raise ValidationError(f"Unsupported export format: '{export_format}'")

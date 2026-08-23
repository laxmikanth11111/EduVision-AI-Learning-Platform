from __future__ import annotations

import io
import json
import zipfile

from app.models.export_template import ExportTemplate
from app.schemas.export import ExportContentData, ExportOptions
from app.services.exporters.base_exporter import BaseExporter, ExportResult


class JSONBundleExporter(BaseExporter):
    async def export(
        self,
        data: ExportContentData,
        options: ExportOptions,
        template: ExportTemplate | None = None,
    ) -> ExportResult:
        payload = {
            "title": data.title,
            "subtitle": data.subtitle,
            "author": data.author,
            "created_at": data.created_at,
            "sections": data.sections,
            "quiz_questions": data.quiz_questions if options.include_answer_key else [
                {k: v for k, v in q.items() if k not in ("answer", "explanation")}
                for q in data.quiz_questions
            ],
            "metadata": data.metadata,
        }

        format_type = options.theme if options.theme in ("zip", "flashcards", "mindmap") else "json"
        safe_title = "".join(c for c in data.title.lower() if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")

        if format_type == "zip":
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("bundle_metadata.json", json.dumps(payload, indent=2))
                # Add markdown study guide to zip
                md_content = f"# {data.title}\n\n" + "\n\n".join(
                    f"## {s.get('title')}\n{s.get('content', '')}" for s in data.sections
                )
                zf.writestr("study_guide.md", md_content)

            filename = f"{safe_title or 'export'}_bundle.zip"
            return ExportResult.create(
                content=zip_buffer.getvalue(),
                filename=filename,
                mime_type="application/zip",
            )

        json_bytes = json.dumps(payload, indent=2).encode("utf-8")
        filename = f"{safe_title or 'export'}.json"

        return ExportResult.create(
            content=json_bytes,
            filename=filename,
            mime_type="application/json",
        )

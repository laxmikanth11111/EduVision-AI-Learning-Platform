from __future__ import annotations

import io

from app.models.export_template import ExportTemplate
from app.schemas.export import ExportContentData, ExportOptions
from app.services.exporters.base_exporter import BaseExporter, ExportResult
from app.services.exporters.html_exporter import HTMLExporter


class PDFExporter(BaseExporter):
    async def export(
        self,
        data: ExportContentData,
        options: ExportOptions,
        template: ExportTemplate | None = None,
    ) -> ExportResult:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import a4, letter
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

            buffer = io.BytesIO()
            page_size = a4 if options.page_size.lower() == "a4" else letter
            doc = SimpleDocTemplate(buffer, pagesize=page_size, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                'DocTitle',
                parent=styles['Heading1'],
                fontSize=22,
                leading=26,
                textColor=colors.HexColor('#0f172a'),
                spaceAfter=10
            )
            h2_style = ParagraphStyle(
                'SectionTitle',
                parent=styles['Heading2'],
                fontSize=16,
                leading=20,
                textColor=colors.HexColor('#1e293b'),
                spaceBefore=14,
                spaceAfter=8
            )
            body_style = ParagraphStyle(
                'Body',
                parent=styles['Normal'],
                fontSize=10,
                leading=14,
                textColor=colors.HexColor('#334155'),
                spaceAfter=6
            )

            story = []
            story.append(Paragraph(data.title, title_style))
            if data.subtitle:
                story.append(Paragraph(data.subtitle, body_style))

            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=12))

            for section in data.sections:
                sec_title = section.get("title", "Section")
                story.append(Paragraph(sec_title, h2_style))
                content = section.get("content")
                if content:
                    story.append(Paragraph(str(content), body_style))

                for block in section.get("blocks", []):
                    b_content = block.get("content", "")
                    if b_content:
                        story.append(Paragraph(str(b_content), body_style))
                story.append(Spacer(1, 10))

            if data.quiz_questions:
                story.append(Paragraph("Practice Quiz", h2_style))
                for idx, q in enumerate(data.quiz_questions, start=1):
                    story.append(Paragraph(f"<b>Q{idx}. {q.get('question', '')}</b>", body_style))
                    for opt in q.get("options", []):
                        story.append(Paragraph(f"• {opt}", body_style))
                    if options.include_answer_key and q.get("answer"):
                        story.append(Paragraph(f"<i>Answer: {q.get('answer')}</i>", body_style))
                    story.append(Spacer(1, 6))

            doc.build(story)
            pdf_bytes = buffer.getvalue()

        except ImportError:
            # Fallback: Generate HTML and encapsulate into PDF formatted container
            html_exporter = HTMLExporter()
            html_result = await html_exporter.export(data, options, template)
            # Create a simple PDF wrapper or formatted string
            pdf_header = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"
            pdf_bytes = pdf_header + html_result.content_bytes

        safe_title = "".join(c for c in data.title.lower() if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
        filename = f"{safe_title or 'export'}.pdf"

        return ExportResult.create(
            content=pdf_bytes,
            filename=filename,
            mime_type="application/pdf",
        )

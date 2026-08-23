from __future__ import annotations

from app.models.export_template import ExportTemplate
from app.schemas.export import ExportContentData, ExportOptions
from app.services.exporters.base_exporter import BaseExporter, ExportResult


class MarkdownExporter(BaseExporter):
    async def export(
        self,
        data: ExportContentData,
        options: ExportOptions,
        template: ExportTemplate | None = None,
    ) -> ExportResult:
        lines: list[str] = []

        # Title and Header
        lines.append(f"# {data.title}")
        if data.subtitle:
            lines.append(f"*{data.subtitle}*")
        lines.append("")

        meta_parts: list[str] = []
        if data.author:
            meta_parts.append(f"**Author:** {data.author}")
        if data.created_at:
            meta_parts.append(f"**Date:** {data.created_at}")
        if meta_parts:
            lines.append(" | ".join(meta_parts))
            lines.append("")

        lines.append("---")
        lines.append("")

        # Content Sections
        for section in data.sections:
            sec_title = section.get("title", "Section")
            lines.append(f"## {sec_title}")
            lines.append("")
            content = section.get("content")
            if content:
                lines.append(content)
                lines.append("")

            blocks = section.get("blocks", [])
            for block in blocks:
                b_type = block.get("type", "paragraph")
                b_heading = block.get("heading")
                b_content = block.get("content", "")

                if b_heading:
                    lines.append(f"### {b_heading}")

                if b_type == "code":
                    lines.append("```")
                    lines.append(b_content)
                    lines.append("```")
                elif b_type == "quote":
                    lines.append(f"> {b_content}")
                elif b_type == "list":
                    if isinstance(b_content, list):
                        for item in b_content:
                            lines.append(f"- {item}")
                    else:
                        lines.append(f"- {b_content}")
                else:
                    lines.append(b_content)
                lines.append("")

        # Quiz Section if present
        if data.quiz_questions:
            lines.append("## Practice Quiz")
            lines.append("")
            for idx, q in enumerate(data.quiz_questions, start=1):
                q_text = q.get("question", "")
                lines.append(f"**Q{idx}. {q_text}**")
                lines.append("")

                options_list = q.get("options", [])
                for opt_idx, opt in enumerate(options_list, start=1):
                    lines.append(f"  {chr(64 + opt_idx)}. {opt}")
                lines.append("")

                if options.include_answer_key:
                    ans = q.get("answer", "")
                    expl = q.get("explanation", "")
                    lines.append(f"*Answer:* {ans}")
                    if expl:
                        lines.append(f"*Explanation:* {expl}")
                    lines.append("")

        if options.footer_text:
            lines.append("---")
            lines.append(f"_{options.footer_text}_")

        content_str = "\n".join(lines)
        safe_title = "".join(c for c in data.title.lower() if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
        filename = f"{safe_title or 'export'}.md"

        return ExportResult.create(
            content=content_str.encode("utf-8"),
            filename=filename,
            mime_type="text/markdown",
        )

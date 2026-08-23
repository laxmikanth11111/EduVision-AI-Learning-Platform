from __future__ import annotations

import html

from app.models.export_template import ExportTemplate
from app.schemas.export import ExportContentData, ExportOptions
from app.services.exporters.base_exporter import BaseExporter, ExportResult

DEFAULT_HTML_CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
    color: #1e293b;
    background-color: #f8fafc;
    margin: 0;
    padding: 2rem;
}
.container {
    max-width: 800px;
    margin: 0 auto;
    background: #ffffff;
    padding: 2.5rem;
    border-radius: 8px;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
}
h1 { color: #0f172a; margin-top: 0; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5rem; }
h2 { color: #1e293b; margin-top: 2rem; }
h3 { color: #334155; }
.meta { color: #64748b; font-size: 0.9rem; margin-bottom: 1.5rem; }
.section { margin-bottom: 2rem; }
.code-block { background: #0f172a; color: #f8fafc; padding: 1rem; border-radius: 6px; font-family: monospace; overflow-x: auto; }
.quote-block { border-left: 4px solid #3b82f6; padding-left: 1rem; color: #475569; font-style: italic; }
.quiz-item { background: #f1f5f9; padding: 1rem; border-radius: 6px; margin-bottom: 1rem; }
.answer-key { background: #dcfce7; color: #166534; padding: 0.5rem; border-radius: 4px; margin-top: 0.5rem; font-size: 0.9rem; }
footer { margin-top: 3rem; text-align: center; color: #94a3b8; font-size: 0.85rem; border-top: 1px solid #e2e8f0; padding-top: 1rem; }
"""


class HTMLExporter(BaseExporter):
    async def export(
        self,
        data: ExportContentData,
        options: ExportOptions,
        template: ExportTemplate | None = None,
    ) -> ExportResult:
        css = (template.css_styles if template and template.css_styles else DEFAULT_HTML_CSS)
        header_html = template.header_html if template and template.header_html else ""
        footer_html = template.footer_html if template and template.footer_html else (
            f"<footer><p>{html.escape(options.footer_text)}</p></footer>" if options.footer_text else ""
        )

        body_parts: list[str] = []
        if header_html:
            body_parts.append(header_html)

        body_parts.append(f"<h1>{html.escape(data.title)}</h1>")
        if data.subtitle:
            body_parts.append(f"<p class='subtitle'><em>{html.escape(data.subtitle)}</em></p>")

        meta_parts: list[str] = []
        if data.author:
            meta_parts.append(f"Author: {html.escape(data.author)}")
        if data.created_at:
            meta_parts.append(f"Date: {html.escape(data.created_at)}")
        if meta_parts:
            body_parts.append(f"<div class='meta'>{' | '.join(meta_parts)}</div>")

        # Sections
        for section in data.sections:
            sec_title = html.escape(section.get("title", "Section"))
            body_parts.append("<div class='section'>")
            body_parts.append(f"<h2>{sec_title}</h2>")

            content = section.get("content")
            if content:
                body_parts.append(f"<p>{html.escape(content)}</p>")

            blocks = section.get("blocks", [])
            for block in blocks:
                b_type = block.get("type", "paragraph")
                b_heading = block.get("heading")
                b_content = block.get("content", "")

                if b_heading:
                    body_parts.append(f"<h3>{html.escape(b_heading)}</h3>")

                if b_type == "code":
                    body_parts.append(f"<pre class='code-block'><code>{html.escape(str(b_content))}</code></pre>")
                elif b_type == "quote":
                    body_parts.append(f"<blockquote class='quote-block'>{html.escape(str(b_content))}</blockquote>")
                elif b_type == "list":
                    body_parts.append("<ul>")
                    if isinstance(b_content, list):
                        for item in b_content:
                            body_parts.append(f"<li>{html.escape(str(item))}</li>")
                    else:
                        body_parts.append(f"<li>{html.escape(str(b_content))}</li>")
                    body_parts.append("</ul>")
                else:
                    body_parts.append(f"<p>{html.escape(str(b_content))}</p>")

            body_parts.append("</div>")

        # Quiz Questions
        if data.quiz_questions:
            body_parts.append("<div class='section'>")
            body_parts.append("<h2>Practice Quiz</h2>")
            for idx, q in enumerate(data.quiz_questions, start=1):
                q_text = html.escape(q.get("question", ""))
                body_parts.append("<div class='quiz-item'>")
                body_parts.append(f"<p><strong>Q{idx}. {q_text}</strong></p>")

                options_list = q.get("options", [])
                if options_list:
                    body_parts.append("<ol type='A'>")
                    for opt in options_list:
                        body_parts.append(f"<li>{html.escape(str(opt))}</li>")
                    body_parts.append("</ol>")

                if options.include_answer_key:
                    ans = html.escape(str(q.get("answer", "")))
                    expl = html.escape(str(q.get("explanation", "")))
                    body_parts.append(f"<div class='answer-key'><strong>Answer:</strong> {ans}")
                    if expl:
                        body_parts.append(f"<br/><em>Explanation:</em> {expl}")
                    body_parts.append("</div>")

                body_parts.append("</div>")
            body_parts.append("</div>")

        if footer_html:
            body_parts.append(footer_html)

        html_document = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(data.title)}</title>
    <style>{css}</style>
</head>
<body>
    <div class="container">
        {"".join(body_parts)}
    </div>
</body>
</html>"""

        safe_title = "".join(c for c in data.title.lower() if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
        filename = f"{safe_title or 'export'}.html"

        return ExportResult.create(
            content=html_document.encode("utf-8"),
            filename=filename,
            mime_type="text/html",
        )

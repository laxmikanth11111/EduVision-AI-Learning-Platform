from __future__ import annotations

import csv
import io

from app.models.export_template import ExportTemplate
from app.schemas.export import ExportContentData, ExportOptions
from app.services.exporters.base_exporter import BaseExporter, ExportResult


class CSVExporter(BaseExporter):
    async def export(
        self,
        data: ExportContentData,
        options: ExportOptions,
        template: ExportTemplate | None = None,
    ) -> ExportResult:
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")

        # If analytics_rows exist, write tabular CSV
        if data.analytics_rows:
            # Determine headers
            field_keys: list[str] = []
            for row in data.analytics_rows:
                for k in row:
                    if k not in field_keys:
                        field_keys.append(k)

            writer.writerow(field_keys)
            for row in data.analytics_rows:
                writer.writerow([row.get(k, "") for k in field_keys])
        else:
            # Fallback to key-value / section content table
            writer.writerow(["Section", "Heading", "Content", "Type"])
            for section in data.sections:
                sec_title = section.get("title", "")
                blocks = section.get("blocks", [])
                if not blocks:
                    writer.writerow([sec_title, "", section.get("content", ""), "paragraph"])
                else:
                    for b in blocks:
                        writer.writerow([
                            sec_title,
                            b.get("heading", ""),
                            str(b.get("content", "")),
                            b.get("type", "paragraph"),
                        ])

        csv_str = output.getvalue()
        safe_title = "".join(c for c in data.title.lower() if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
        filename = f"{safe_title or 'export'}.csv"

        return ExportResult.create(
            content=csv_str.encode("utf-8"),
            filename=filename,
            mime_type="text/csv",
        )

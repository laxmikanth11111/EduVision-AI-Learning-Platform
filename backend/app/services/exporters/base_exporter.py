from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.export_template import ExportTemplate
from app.schemas.export import ExportContentData, ExportOptions


@dataclass
class ExportResult:
    content_bytes: bytes
    filename: str
    mime_type: str
    file_size_bytes: int
    checksum_sha256: str

    @classmethod
    def create(cls, content: bytes, filename: str, mime_type: str) -> ExportResult:
        sha256 = hashlib.sha256(content).hexdigest()
        return cls(
            content_bytes=content,
            filename=filename,
            mime_type=mime_type,
            file_size_bytes=len(content),
            checksum_sha256=sha256,
        )


class BaseExporter(ABC):
    @abstractmethod
    async def export(
        self,
        data: ExportContentData,
        options: ExportOptions,
        template: ExportTemplate | None = None,
    ) -> ExportResult:
        ...

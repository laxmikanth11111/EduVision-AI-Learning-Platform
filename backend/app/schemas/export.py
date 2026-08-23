from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shared.constants import ExportFormat, ExportKind


class ExportOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    include_answer_key: bool = Field(default=False, alias="includeAnswerKey")
    page_size: str = Field(default="letter", alias="pageSize")
    include_diagrams: bool = Field(default=True, alias="includeDiagrams")
    theme: str = Field(default="standard")
    header_text: str | None = Field(default=None, alias="headerText")
    footer_text: str | None = Field(default=None, alias="footerText")


class ExportCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    format: str = Field(default=ExportFormat.PDF.value)
    kind: str = Field(default=ExportKind.NOTES.value)
    include_modes: list[str] = Field(
        default_factory=lambda: ["theory", "summary", "quiz"], alias="includeModes"
    )
    options: ExportOptions = Field(default_factory=ExportOptions)
    template_key: str = Field(default="standard", alias="templateKey")


class ExportJobData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    export_id: str = Field(alias="exportId")
    status: str
    estimated_duration: int = Field(default=30, alias="estimatedDuration")
    queued_at: datetime = Field(alias="queuedAt")
    progress_percentage: int = Field(default=0, alias="progressPercentage")
    kind: str
    format: str


class ExportJobResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    success: bool = True
    data: ExportJobData
    meta: dict[str, Any] = Field(default_factory=dict)


class ExportStatusData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    export_id: str = Field(alias="exportId")
    status: str
    download_url: str | None = Field(default=None, alias="downloadUrl")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    file_size: int = Field(default=0, alias="fileSize")
    format: str
    progress_percentage: int = Field(default=0, alias="progressPercentage")
    error_message: str | None = Field(default=None, alias="errorMessage")


class ExportStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    success: bool = True
    data: ExportStatusData
    meta: dict[str, Any] = Field(default_factory=dict)


class AnalyticsExportData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    export_url: str = Field(alias="exportUrl")
    expires_at: datetime = Field(alias="expiresAt")
    format: str = Field(default="csv")
    fields: list[str] = Field(
        default_factory=lambda: [
            "user_id",
            "completion_percent",
            "quiz_score",
            "time_spent_min",
            "last_active",
        ]
    )


class AnalyticsExportResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    success: bool = True
    data: AnalyticsExportData
    meta: dict[str, Any] = Field(default_factory=dict)


class ExportTemplateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    public_id: str = Field(alias="publicId")
    name: str
    template_key: str = Field(alias="templateKey")
    description: str | None = None
    kind: str
    format: str
    is_default: bool = Field(alias="isDefault")


class ExportContentData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    subtitle: str | None = None
    author: str | None = None
    created_at: str | None = None
    sections: list[dict[str, Any]] = Field(default_factory=list)
    quiz_questions: list[dict[str, Any]] = Field(default_factory=list)
    analytics_rows: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

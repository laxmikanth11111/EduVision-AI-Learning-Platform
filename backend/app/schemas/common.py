from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")
TItem = TypeVar("TItem")


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    message: str | None = None
    request_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class APIErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail


class PaginationMeta(BaseModel):
    page: int = Field(ge=1, description="Current page number")
    page_size: int = Field(ge=1, le=1000, description="Items per page")
    total: int = Field(ge=0, description="Total number of items")
    total_pages: int = Field(ge=0, description="Total number of pages")
    has_next: bool = Field(description="Whether a next page exists")
    has_previous: bool = Field(description="Whether a previous page exists")


class CursorPaginationMeta(BaseModel):
    cursor: str | None = Field(None, description="Opaque cursor for the next page")
    previous_cursor: str | None = Field(None, description="Opaque cursor for the previous page")
    has_next: bool = Field(description="Whether a next page exists")
    has_previous: bool = Field(description="Whether a previous page exists")
    total: int | None = Field(None, description="Total items (if computed)")


class PaginatedResponse(BaseModel, Generic[TItem]):
    success: bool = True
    data: list[TItem] = Field(default_factory=list)
    pagination: PaginationMeta
    request_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CursorPaginatedResponse(BaseModel, Generic[TItem]):
    success: bool = True
    data: list[TItem] = Field(default_factory=list)
    pagination: CursorPaginationMeta
    request_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

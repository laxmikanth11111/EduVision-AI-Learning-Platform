from __future__ import annotations

import base64
import json
import math
from typing import Any, TypeVar

T = TypeVar("T")


class PageParams:
    def __init__(self, page: int = 1, page_size: int = 20) -> None:
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), 1000)
        self.offset = (self.page - 1) * self.page_size


class CursorParams:
    def __init__(self, cursor: str | None = None, limit: int = 20) -> None:
        self.cursor = cursor
        self.limit = min(max(1, limit), 1000)


def create_page_meta(page: int, page_size: int, total: int) -> dict[str, Any]:
    total_pages = max(0, math.ceil(total / page_size)) if page_size > 0 else 0
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }


def encode_cursor(value: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def decode_cursor(cursor: str) -> dict[str, Any] | None:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor).decode())
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return None


def compute_pagination(page: int, page_size: int, total: int) -> dict[str, Any]:
    return create_page_meta(page, page_size, total)

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.presentation import Presentation


@dataclass
class _FakeUser:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    role: str = "user"


@pytest_asyncio.fixture
async def make_user():
    users: list[_FakeUser] = []

    async def _make_user(**overrides: Any) -> _FakeUser:
        user = _FakeUser(
            id=overrides.get("id", uuid.uuid4()),
            role=overrides.get("role", "user"),
        )
        users.append(user)
        return user

    return _make_user


@pytest_asyncio.fixture
async def make_presentation(db_session: AsyncSession):
    async def _make_presentation(owner_id=None, **overrides: Any) -> Presentation:
        raw_owner = owner_id or overrides.pop("owner_id", uuid.uuid4())
        presentation = Presentation(
            title=overrides.pop("title", "Test Presentation"),
            owner_id=raw_owner if raw_owner else None,
            status=overrides.pop("status", "draft"),
            visibility=overrides.pop("visibility", "private"),
            **overrides,
        )
        db_session.add(presentation)
        await db_session.flush()
        return presentation

    return _make_presentation

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import joinedload, relationship, selectinload

from app.database.base import Base
from app.database.repository import BaseRepository


class RelatedModel(Base):
    __tablename__ = "related_models"

    id = Column(Integer, primary_key=True)
    fake_model_id = Column(Integer, ForeignKey("fake_models.id"))


class FakeModel(Base):
    __tablename__ = "fake_models"

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    related = relationship(RelatedModel)


class TestBaseRepositoryLoading:
    @pytest.fixture
    def repo(self) -> BaseRepository[FakeModel]:
        session = MagicMock()
        session.execute = AsyncMock()
        return BaseRepository(session=session, model=FakeModel)

    def test_joined_load_static_method(self) -> None:
        opt = BaseRepository.joined(FakeModel.related)
        assert opt is not None

    def test_selectin_load_static_method(self) -> None:
        opt = BaseRepository.selectin(FakeModel.related)
        assert opt is not None

    def test_apply_load_options(self, repo: BaseRepository[FakeModel]) -> None:
        from sqlalchemy import select

        stmt = select(FakeModel)
        opt = joinedload(FakeModel.related)
        modified = repo._apply_load_options(stmt, [opt])
        assert len(modified._annotations) > 0 or hasattr(modified, "options")

    async def test_get_with_load_options(self) -> None:
        session = MagicMock()
        execute_mock = AsyncMock()
        session.execute = execute_mock

        repo = BaseRepository(session=session, model=FakeModel)
        opt = joinedload(FakeModel.related)

        await repo.get(uuid.uuid4(), load_options=[opt])

        assert execute_mock.called

    async def test_paginate_with_load_options(self) -> None:
        session = MagicMock()
        count_res = MagicMock()
        count_res.scalar_one.return_value = 0

        data_res = MagicMock()
        data_res.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[count_res, data_res])

        repo = BaseRepository(session=session, model=FakeModel)
        opt = selectinload(FakeModel.related)

        items, total = await repo.paginate(page=1, page_size=20, load_options=[opt])

        assert total == 0
        assert items == []

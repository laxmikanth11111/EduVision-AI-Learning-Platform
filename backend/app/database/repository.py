from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, UnaryExpression, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import (
    contains_eager,
    joinedload,
    load_only,
    selectinload,
    subqueryload,
)
from sqlalchemy.orm.strategy_options import _AbstractLoad
from sqlalchemy.sql.expression import delete as sql_delete

from app.core.exceptions import NotFoundError
from app.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)

# Preserves the exact Select shape across `_apply_load_options`. SQLAlchemy 2.x
# models `Select` as variadic (`Select[*Ts]`), and `Select.options()` returns the
# same type it was given, so a dedicated TypeVar keeps the row type intact
# instead of widening or narrowing it at every call site.
SelectType = TypeVar("SelectType", bound=Select[Any])

LoadType = list[_AbstractLoad | type[_AbstractLoad]]


class BaseRepository(Generic[ModelType]):
    def __init__(self, session: AsyncSession, model: type[ModelType]) -> None:
        self._session = session
        self._model = model

    @staticmethod
    def joined(*paths: Any) -> _AbstractLoad:
        return joinedload(*paths)

    @staticmethod
    def selectin(*paths: Any) -> _AbstractLoad:
        return selectinload(*paths)

    @staticmethod
    def subquery(*paths: Any) -> _AbstractLoad:
        return subqueryload(*paths)

    @staticmethod
    def load_only_fields(*columns: Any) -> _AbstractLoad:
        return load_only(*columns)

    @staticmethod
    def eager_contains(*paths: Any) -> _AbstractLoad:
        return contains_eager(*paths)

    def _apply_load_options(
        self,
        stmt: SelectType,
        load_options: LoadType | None,
    ) -> SelectType:
        if load_options:
            options: list[Any] = load_options
            stmt = stmt.options(*options)
        return stmt

    async def create(self, **kwargs: Any) -> ModelType:
        instance = self._model(**kwargs)
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def get(
        self,
        id: uuid.UUID,
        load_options: LoadType | None = None,
    ) -> ModelType | None:
        stmt = select(self._model).where(self._model.id == id)  # type: ignore[attr-defined]
        stmt = self._apply_load_options(stmt, load_options)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_raise(
        self,
        id: uuid.UUID,
        load_options: LoadType | None = None,
    ) -> ModelType:
        instance = await self.get(id, load_options=load_options)
        if instance is None:
            raise NotFoundError(
                message=f"{self._model.__name__} not found",
                details={"id": str(id)},
            )
        return instance

    async def find(
        self,
        load_options: LoadType | None = None,
        **filters: Any,
    ) -> list[ModelType]:
        stmt = select(self._model).filter_by(**filters)
        stmt = self._apply_load_options(stmt, load_options)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_one(
        self,
        load_options: LoadType | None = None,
        **filters: Any,
    ) -> ModelType | None:
        stmt = select(self._model).filter_by(**filters).limit(1)
        stmt = self._apply_load_options(stmt, load_options)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_one_or_raise(
        self,
        load_options: LoadType | None = None,
        **filters: Any,
    ) -> ModelType:
        instance = await self.find_one(load_options=load_options, **filters)
        if instance is None:
            raise NotFoundError(
                message=f"{self._model.__name__} not found",
                details=filters,
            )
        return instance

    async def update(self, id: uuid.UUID, **kwargs: Any) -> ModelType:
        instance = await self.get_or_raise(id)
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def delete(self, id: uuid.UUID, hard: bool = False) -> None:
        if hard:
            stmt = sql_delete(self._model).where(self._model.id == id)  # type: ignore[attr-defined]
            await self._session.execute(stmt)
            return

        instance = await self.get_or_raise(id)
        if hasattr(instance, "soft_delete"):
            instance.soft_delete()
            await self._session.flush()
            return

        # The model has no soft-delete capability. Falling back to a hard
        # delete preserves the delete contract: a requested delete must not
        # silently no-op just because the model cannot be soft-deleted.
        stmt = sql_delete(self._model).where(self._model.id == id)  # type: ignore[attr-defined]
        await self._session.execute(stmt)

    async def count(self, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self._model).filter_by(**filters)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def paginate(
        self,
        page: int = 1,
        page_size: int = 20,
        order_by: str | None = None,
        descending: bool = False,
        load_options: LoadType | None = None,
        **filters: Any,
    ) -> tuple[list[ModelType], int]:
        base_stmt = select(self._model).filter_by(**filters)

        count_stmt = select(func.count()).select_from(self._model).filter_by(**filters)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        order_columns: list[UnaryExpression[Any]] = []
        if order_by and hasattr(self._model, order_by):
            col = getattr(self._model, order_by)
            order_columns.append(col.desc() if descending else col.asc())
        if hasattr(self._model, "id") and (not order_by or order_by != "id"):
            order_columns.append(self._model.id.asc())  # type: ignore[attr-defined]

        stmt = base_stmt
        if order_columns:
            stmt = stmt.order_by(*order_columns)

        stmt = stmt.offset(offset).limit(page_size)
        stmt = self._apply_load_options(stmt, load_options)

        result = await self._session.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def exists(self, **filters: Any) -> bool:
        stmt = select(self._model).filter_by(**filters).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def refresh(self, instance: ModelType) -> ModelType:
        await self._session.refresh(instance)
        return instance

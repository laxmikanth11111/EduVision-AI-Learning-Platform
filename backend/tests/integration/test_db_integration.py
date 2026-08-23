from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import JSON, Column, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base, TimestampMixin

pytestmark = pytest.mark.integration


class IntegrationTestModel(Base, TimestampMixin):
    __tablename__ = "integration_test_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    metadata_json = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)


@pytest_asyncio.fixture(autouse=True)
async def create_table(pg_engine):
    async with pg_engine.begin() as conn:
        await conn.run_sync(IntegrationTestModel.__table__.create, checkfirst=True)
    yield
    async with pg_engine.begin() as conn:
        await conn.run_sync(IntegrationTestModel.__table__.drop, checkfirst=True)


class TestPostgreSQLIntegration:
    async def test_uuid_primary_key(self, pg_session: AsyncSession) -> None:
        model_id = uuid.uuid4()
        instance = IntegrationTestModel(id=model_id, name="test-uuid")
        pg_session.add(instance)
        await pg_session.flush()

        result = await pg_session.get(IntegrationTestModel, model_id)
        assert result is not None
        assert result.id == model_id

    async def test_jsonb_column(self, pg_session: AsyncSession) -> None:
        metadata = {"key": "value", "nested": {"a": 1, "b": [2, 3]}, "enabled": True}
        instance = IntegrationTestModel(name="test-jsonb", metadata_json=metadata)
        pg_session.add(instance)
        await pg_session.flush()

        result = await pg_session.get(IntegrationTestModel, instance.id)
        assert result is not None
        assert result.metadata_json == metadata

    async def test_unique_constraint(self, pg_session: AsyncSession) -> None:
        stmt = text("CREATE UNIQUE INDEX uq_name ON integration_test_models (name)")
        await pg_session.execute(stmt)
        await pg_session.commit()

        pg_session.add(IntegrationTestModel(name="unique-name"))
        await pg_session.flush()

        duplicate = IntegrationTestModel(name="unique-name")
        pg_session.add(duplicate)
        with pytest.raises(IntegrityError):
            await pg_session.flush()

    async def test_transaction_rollback(self, pg_session: AsyncSession) -> None:
        instance = IntegrationTestModel(name="rollback-test")
        pg_session.add(instance)
        await pg_session.flush()

        await pg_session.rollback()

        result = await pg_session.get(IntegrationTestModel, instance.id)
        assert result is None

    async def test_index_usage(self, pg_session: AsyncSession) -> None:
        instances = [IntegrationTestModel(name=f"index-test-{i}") for i in range(10)]
        for inst in instances:
            pg_session.add(inst)
        await pg_session.flush()

        from sqlalchemy import select, text

        stmt = select(IntegrationTestModel).where(
            IntegrationTestModel.name == "index-test-5"
        )
        result = await pg_session.execute(stmt)
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.name == "index-test-5"

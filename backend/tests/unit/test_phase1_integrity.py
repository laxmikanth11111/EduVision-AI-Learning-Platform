"""Phase 1 individual-user foundation & production-hardening regression tests.

Covers the fixes made for the Phase 1 foundation:
* visual canvas strict-ownership guard (null-owner bypass closed)
* bounded file upload reads
* base-repository soft-delete contract fallback
* UserRole reduced to an individual "user" role
* Redis-backed refresh-token revocation (in-memory fallback path)
* migration 0025 wiring and model agreement
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import Column, String

from app.database.base import Base as _SaBase
from app.database.base import SoftDeletableBaseModel
from shared.constants import UserRole


class _PlainRow(_SaBase):
    __tablename__ = "phase1_plain_row"

    id = Column(String(36), primary_key=True)


class _SoftRow(SoftDeletableBaseModel):
    __tablename__ = "phase1_soft_row"

    label = Column(String(36))


# ---------------------------------------------------------------------------
# Visual canvas strict-ownership guard
# ---------------------------------------------------------------------------

def _canvas(user_id) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), user_id=user_id)


def _fake_persistence_service(canvas) -> SimpleNamespace:
    repo = SimpleNamespace(get_or_raise=AsyncMock(return_value=canvas))
    return SimpleNamespace(canvas_repo=repo)


class TestVisualCanvasOwnerGuard:
    @pytest.mark.parametrize(
        "canvas_user_id",
        [None, uuid.uuid4()],
        ids=["null-owner", "other-owner"],
    )
    async def test_denies_non_owner_and_null_owner(self, canvas_user_id) -> None:
        from app.api.v1.visual_canvases import _assert_canvas_owner
        from app.core.exceptions import NotFoundError

        requester = SimpleNamespace(id=uuid.uuid4())

        with pytest.raises(NotFoundError):
            await _assert_canvas_owner(
                canvas_id=uuid.uuid4(),
                user=requester,
                persistence_service=_fake_persistence_service(_canvas(canvas_user_id)),
            )

    async def test_allows_owner(self) -> None:
        from app.api.v1.visual_canvases import _assert_canvas_owner

        owner_id = uuid.uuid4()
        requester = SimpleNamespace(id=owner_id)

        await _assert_canvas_owner(
            canvas_id=uuid.uuid4(),
            user=requester,
            persistence_service=_fake_persistence_service(_canvas(owner_id)),
        )


# ---------------------------------------------------------------------------
# Bounded upload reads
# ---------------------------------------------------------------------------

class _FakeUpload:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self, size: int = -1) -> bytes:
        return self._data if size == -1 else self._data[:size]


class TestBoundedUpload:
    async def test_accepts_upload_within_limit(self) -> None:
        from app.api.v1.presentations import _read_upload_bounded
        from app.core.config import settings

        data = b"x" * (settings.UPLOAD_MAX_FILE_SIZE - 1)
        result = await _read_upload_bounded(_FakeUpload(data))
        assert result == data

    async def test_rejects_upload_over_limit(self) -> None:
        from fastapi import HTTPException

        from app.api.v1.presentations import _read_upload_bounded
        from app.core.config import settings

        over = b"x" * (settings.UPLOAD_MAX_FILE_SIZE + 1)
        with pytest.raises(HTTPException) as excinfo:
            await _read_upload_bounded(_FakeUpload(over))
        assert excinfo.value.status_code == 413


# ---------------------------------------------------------------------------
# UserRole -> individual user
# ---------------------------------------------------------------------------

class TestUserRoleIndividual:
    def test_role_is_individual_user(self) -> None:
        assert UserRole.USER.value == "user"

    def test_no_multi_role_members(self) -> None:
        for legacy in ("STUDENT", "TEACHER", "ADMIN", "SUPER_ADMIN"):
            assert not hasattr(UserRole, legacy)


# ---------------------------------------------------------------------------
# Base repository delete contract
# ---------------------------------------------------------------------------

class TestBaseRepositoryDelete:
    async def test_hard_delete_for_non_soft_deletable_model(self) -> None:
        """delete(hard=False) on a model without soft-delete must hard delete,
        not silently no-op."""
        import uuid as _uuid

        from app.database.repository import BaseRepository

        instance = SimpleNamespace(id=str(_uuid.uuid4()))
        result = SimpleNamespace(scalar_one_or_none=lambda: instance)

        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        repo = BaseRepository(session, _PlainRow)
        await repo.delete(instance.id, hard=False)

        # get_or_raise -> get consumed one execute call returning the instance
        assert session.execute.await_count >= 1
        # the final executed statement (the DELETE) must be a SQL delete
        stmt = session.execute.await_args_list[-1].args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True})).strip().upper()
        assert compiled.startswith("DELETE FROM")

    async def test_soft_delete_sets_deleted_at(self) -> None:
        import uuid as _uuid

        from app.database.repository import BaseRepository

        instance = _SoftRow(id=_uuid.uuid4(), label="x")
        result = SimpleNamespace(scalar_one_or_none=lambda: instance)

        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        repo = BaseRepository(session, _SoftRow)
        await repo.delete(instance.id, hard=False)

        assert instance.deleted_at is not None
        session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# Refresh-token revocation (Redis-backed, in-memory fallback)
# ---------------------------------------------------------------------------

class TestRefreshTokenRevocation:
    @pytest.mark.asyncio
    async def test_revoke_and_detect_fallback_in_memory(self, monkeypatch) -> None:
        import app.api.v1.auth as auth

        async def _raise_pool():
            raise RuntimeError("redis unavailable")

        monkeypatch.setattr(
            "app.workers.redis_client.get_redis_pool", _raise_pool
        )
        monkeypatch.setattr(auth, "_revoked_refresh_jtis", set())

        jti = "some-jti-value"
        assert await auth._is_refresh_jti_revoked(jti) is False
        await auth._revoke_refresh_jti(jti)
        assert await auth._is_refresh_jti_revoked(jti) is True

    @pytest.mark.asyncio
    async def test_unrevoked_token_is_not_revoked(self, monkeypatch) -> None:
        import app.api.v1.auth as auth

        async def _raise_pool():
            raise RuntimeError("redis unavailable")

        monkeypatch.setattr(
            "app.workers.redis_client.get_redis_pool", _raise_pool
        )
        monkeypatch.setattr(auth, "_revoked_refresh_jtis", set())

        assert await auth._is_refresh_jti_revoked("never-revoked-jti") is False


# ---------------------------------------------------------------------------
# Migration 0025 wiring and model agreement
# ---------------------------------------------------------------------------

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "database"
    / "migrations"
    / "versions"
)

EXPECTED_FK_INDEXES = {
    "ix_question_attempts_question_id": "question_attempts",
    "ix_quiz_attempts_quiz_version_id": "quiz_attempts",
    "ix_quizzes_lesson_version_id": "quizzes",
    "ix_user_answers_question_attempt_id": "user_answers",
}


class TestMigration0025:
    def test_revision_chain(self) -> None:
        import importlib.util

        path = MIGRATIONS_DIR / "0025_fk_indexes.py"
        spec = importlib.util.spec_from_file_location("m0025", path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.revision == "0025_fk_indexes"
        assert module.down_revision == "0024_p3_feedback_and_comparison"

    def test_upgrade_adds_expected_fk_indexes(self) -> None:
        tree = ast.parse(
            (MIGRATIONS_DIR / "0025_fk_indexes.py").read_text(encoding="utf-8")
        )

        created = {}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create_index"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                created[str(node.args[0].value)] = node.args[1].value  # table name

        assert created == EXPECTED_FK_INDEXES

    def test_model_agreement_indexes_exist(self) -> None:
        import app.models  # noqa: F401
        from app.database.base import Base

        coverage = {}
        for table in Base.metadata.tables.values():
            cols = {c.name for c in table.c if c.index}
            for idx in table.indexes:
                cols.update(c.name for c in idx.columns)
            coverage[table.name] = cols

        assert "question_id" in coverage["question_attempts"]
        assert "quiz_version_id" in coverage["quiz_attempts"]
        assert "lesson_version_id" in coverage["quizzes"]
        assert "question_attempt_id" in coverage["user_answers"]

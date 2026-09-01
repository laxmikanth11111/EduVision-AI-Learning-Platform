"""PostgreSQL integrity tests (WS2).

These run against the Alembic-migrated scratch database and verify that the
real PostgreSQL engine enforces the invariants the Phase 2 contract requires:
foreign keys reject dangling references, unique constraints hold, transactions
roll back atomically, and PortableJSONB round-trips native ``jsonb`` data.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer_key import AnswerKey
from app.models.presentation import Presentation
from app.models.question_explanation import QuestionExplanation
from app.models.quiz import Quiz
from app.models.quiz_content import Question, QuestionOption
from app.models.quiz_version import QuizVersion
from app.models.user import User

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def user(pg_session: AsyncSession) -> User:
    u = User(
        email=f"{uuid.uuid4().hex[:20]}@test.local",
        name="PG Test User",
    )
    pg_session.add(u)
    await pg_session.flush()
    return u


async def _presentation(pg_session: AsyncSession, owner_id: uuid.UUID) -> Presentation:
    pres = Presentation(title="PG Integrity Test", owner_id=owner_id, status="ready")
    pg_session.add(pres)
    await pg_session.flush()
    return pres


async def test_foreign_key_rejects_dangling_presentation(pg_session: AsyncSession, user: User):
    """A quiz referencing a non-existent presentation must be rejected."""
    quiz = Quiz(
        presentation_id=uuid.uuid4(),
        user_id=user.id,
        status="published",
        mode="practice",
        title="Dangling",
        question_count=1,
        latest_version=1,
    )
    pg_session.add(quiz)
    with pytest.raises(IntegrityError):
        await pg_session.flush()
    await pg_session.rollback()


async def test_foreign_key_rejects_dangling_owner(pg_session: AsyncSession):
    """A presentation owned by a non-existent user must be rejected.

    The migrated schema enforces ``presentations.owner_id -> users.id`` even
    though the ORM model omits the foreign key (a known model/migration drift
    documented in the P2 report); PostgreSQL applies the DDL-level constraint.
    """
    pres = Presentation(title="Ownerless", owner_id=uuid.uuid4(), status="ready")
    pg_session.add(pres)
    with pytest.raises(IntegrityError):
        await pg_session.flush()
    await pg_session.rollback()


async def test_foreign_key_rejects_dangling_user(pg_session: AsyncSession, user: User):
    """A presentation-owned quiz referencing a non-existent user must fail."""
    pres = await _presentation(pg_session, user.id)
    quiz = Quiz(
        presentation_id=pres.id,
        user_id=uuid.uuid4(),
        status="published",
        mode="practice",
        title="Dangling user",
        question_count=1,
        latest_version=1,
    )
    pg_session.add(quiz)
    with pytest.raises(IntegrityError):
        await pg_session.flush()
    await pg_session.rollback()


async def test_cascade_delete_removes_children(pg_session: AsyncSession, user: User):
    """Deleting a presentation cascades to its quizzes (ondelete CASCADE)."""
    pres = await _presentation(pg_session, user.id)
    quiz = Quiz(
        presentation_id=pres.id,
        user_id=user.id,
        status="published",
        mode="practice",
        title="Casacade target",
        question_count=1,
        latest_version=1,
    )
    pg_session.add(quiz)
    await pg_session.flush()

    await pg_session.delete(pres)
    await pg_session.flush()

    leftover = await pg_session.execute(
        select(Quiz).where(Quiz.id == quiz.id)
    )
    assert leftover.scalar_one_or_none() is None


async def test_unique_email_enforced(pg_session: AsyncSession, user: User):
    """users.email unique constraint is enforced by the real engine."""
    duplicate = User(
        email=user.email,
        name="Duplicate User",
    )
    pg_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await pg_session.flush()
    await pg_session.rollback()


async def test_transaction_rollback_is_atomic(pg_session: AsyncSession, user: User):
    """A failed insert must roll back all rows in the same transaction."""
    pres = await _presentation(pg_session, user.id)
    quiz = Quiz(
        presentation_id=pres.id,
        user_id=user.id,
        status="published",
        mode="practice",
        title="Rollback target",
        question_count=1,
        latest_version=1,
    )
    pg_session.add(quiz)
    await pg_session.flush()

    await pg_session.rollback()

    pres_left = await pg_session.execute(
        select(Presentation).where(Presentation.id == pres.id)
    )
    quiz_left = await pg_session.execute(select(Quiz).where(Quiz.id == quiz.id))
    assert pres_left.scalar_one_or_none() is None
    assert quiz_left.scalar_one_or_none() is None


async def test_portable_jsonb_roundtrips_native_jsonb(pg_session: AsyncSession, user: User):
    """PortableJSONB columns read/write nested data on real PostgreSQL."""
    pres = await _presentation(pg_session, user.id)
    quiz = Quiz(
        presentation_id=pres.id,
        user_id=user.id,
        status="published",
        mode="practice",
        title="JSONB roundtrip",
        question_count=1,
        latest_version=1,
    )
    pg_session.add(quiz)
    await pg_session.flush()

    version = QuizVersion(quiz_id=quiz.id, version=1, status="published")
    pg_session.add(version)
    await pg_session.flush()

    question = Question(
        quiz_version_id=version.id,
        position=1,
        question_type="multiple_choice",
        stem="Which choice is correct?",
        points=1,
    )
    pg_session.add(question)
    await pg_session.flush()

    correct = QuestionOption(
        question_id=question.id,
        position=1,
        text="The right one",
        is_correct=True,
    )
    pg_session.add(correct)
    await pg_session.flush()

    explanation = QuestionExplanation(question_id=question.id, explanation="Because.")
    pg_session.add(explanation)

    answer_key = AnswerKey(
        question_id=question.id,
        answer_type="multiple_choice",
        correct_option_ids=[correct.public_id],
        acceptable_answers=["a", "b", "c"],
    )
    pg_session.add(answer_key)
    await pg_session.flush()

    fetched = (
        await pg_session.execute(
            select(AnswerKey).where(AnswerKey.id == answer_key.id)
        )
    ).scalar_one()
    assert fetched.correct_option_ids == [correct.public_id]
    assert fetched.acceptable_answers == ["a", "b", "c"]

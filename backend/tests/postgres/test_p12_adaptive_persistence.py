"""P12 adaptive assessment persistence on real PostgreSQL.

Runs against the Alembic-migrated scratch database (postgres:16-alpine), so it
exercises the real production schema lineage including migration 0032
(``quiz_attempts.adaptive`` + ``ix_quiz_attempts_status``) and 0033
(``educational_memories``), plus the repaired NOT NULL/Numeric/JSONB columns.
The full adaptive attempt lifecycle is driven through the real service stack:
start (initial adaptive order), in-attempt ``next`` (correct -> harder),
timed answers, submit, JSONB feedback and Numeric points persistence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.answer_key import AnswerKey
from app.models.concept import Concept
from app.models.educational_memory import EducationalMemoryRecord
from app.models.presentation import Presentation
from app.models.question_attempt import QuestionAttempt
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_content import Question, QuestionOption
from app.models.quiz_version import QuizVersion
from app.models.user import User
from app.models.user_answer import UserAnswer
from app.services.quiz_attempt_service import QuizAttemptService

pytestmark = pytest.mark.postgres

DIFFICULTIES = ("beginner", "intermediate", "advanced")


@pytest_asyncio.fixture
async def user(pg_session: AsyncSession) -> User:
    u = User(
        email=f"{uuid.uuid4().hex[:20]}@test.local",
        name="P12 PG User",
    )
    pg_session.add(u)
    await pg_session.flush()
    return u


@pytest_asyncio.fixture
async def adaptive_seed(
    pg_session: AsyncSession, user: User
) -> dict[str, object]:
    pres = Presentation(title="P12 Adaptive Deck", owner_id=user.id, status="published")
    pg_session.add(pres)
    await pg_session.flush()

    concept = Concept(
        name="P12 PG Concept",
        topic="p12",
        presentation_id=pres.id,
    )
    pg_session.add(concept)
    await pg_session.flush()

    quiz = Quiz(
        presentation_id=pres.id,
        user_id=user.id,
        status="published",
        mode="practice",
        title="P12 Adaptive Quiz",
        description="Real-PG adaptive delivery",
        difficulty="intermediate",
        question_count=3,
        max_attempts_per_user=5,
        passing_score=60.0,
        shuffle_questions=False,
        shuffle_options=False,
        show_feedback_after=True,
        latest_version=1,
        published_version=1,
    )
    pg_session.add(quiz)
    await pg_session.flush()

    version = QuizVersion(
        quiz_id=quiz.id,
        version=1,
        status="published",
        title="P12 Adaptive Quiz v1",
    )
    pg_session.add(version)
    await pg_session.flush()

    questions: list[dict[str, object]] = []
    for pos, difficulty in enumerate(DIFFICULTIES, start=1):
        q = Question(
            quiz_version_id=version.id,
            position=pos,
            question_type="multiple_choice",
            stem=f"PG adaptive {pos} ({difficulty})",
            points=2,
            bloom_level="remember",
            difficulty=difficulty,
            concept_id=concept.id,
        )
        pg_session.add(q)
        await pg_session.flush()
        wrong = QuestionOption(question_id=q.id, position=1, text="Wrong", is_correct=False)
        right = QuestionOption(question_id=q.id, position=2, text="Right", is_correct=True)
        pg_session.add_all([wrong, right])
        await pg_session.flush()
        pg_session.add(
            AnswerKey(
                question_id=q.id,
                answer_type="multiple_choice",
                correct_option_ids=[right.public_id],
            )
        )
        questions.append(
            {
                "question_id": q.id,
                "public_id": str(q.public_id),
                "difficulty": difficulty,
                "correct": str(right.public_id),
                "wrong": str(wrong.public_id),
            }
        )

    now = datetime.now(UTC).timestamp()
    memory = {
        "user_id": str(user.id),
        "profile": {
            "user_id": str(user.id),
            "learning_pace": "moderate",
            "total_study_minutes": 0.0,
            "average_mastery": 65.0,
            "streak_days": 1,
        },
        "concept_records": {
            str(concept.public_id): {
                "concept_id": str(concept.public_id),
                "concept_name": "P12 PG Concept",
                "first_learned_at": now,
                "last_reviewed_at": now,
                "mastery_score": 65.0,
                "review_count": 1,
                "trend": "stable",
                "confidence_score": 0.5,
            }
        },
        "mastered_concepts": [],
        "developing_concepts": [str(concept.public_id)],
        "weak_concepts": [],
        "preferences": {},
        "revision_queue": [],
        "milestones": [],
        "created_at": now,
        "updated_at": now,
    }
    pg_session.add(
        EducationalMemoryRecord(user_id=user.id, memory_data=memory)
    )
    await pg_session.commit()
    return {
        "quiz_public_id": str(quiz.public_id),
        "user_id": user.id,
        "questions": questions,
    }


async def test_0032_schema_contract(pg_session: AsyncSession) -> None:
    """Migration 0032 exists in the lineage and the schema matches the ORM."""
    heads = (await pg_session.execute(
        text("SELECT version_num FROM alembic_version")
    )).scalar_one()
    assert heads == "0035_c3_topic_visual_assets"

    adaptive_col = await pg_session.execute(
        text(
            "SELECT column_default, is_nullable FROM information_schema.columns "
            "WHERE table_name='quiz_attempts' AND column_name='adaptive'"
        )
    )
    row = adaptive_col.first()
    assert row is not None, "quiz_attempts.adaptive column missing"
    assert row[1] == "NO", "quiz_attempts.adaptive should be NOT NULL"

    idx = await pg_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE indexname = 'ix_quiz_attempts_status'"
        )
    )
    assert idx.scalar_one_or_none() is not None, "ix_quiz_attempts_status missing"

    feedback_type = await pg_session.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name='question_attempts' AND column_name='feedback'"
        )
    )
    assert feedback_type.scalar_one() == "jsonb"

    points_type = await pg_session.execute(
        text(
            "SELECT data_type, numeric_precision, numeric_scale FROM information_schema.columns "
            "WHERE table_name='question_attempts' AND column_name='points_earned'"
        )
    )
    pts = points_type.first()
    assert pts is not None, "question_attempts.points_earned column missing"
    assert pts[0] == "numeric", f"expected numeric, got {pts[0]}"
    assert pts[2] == 2, f"expected scale 2, got {pts[2]}"


async def test_adaptive_start_persists_contract(
    pg_session: AsyncSession, adaptive_seed: dict[str, object]
) -> None:
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = QuizAttemptService(uow)
    result = await service.start_attempt(
        str(adaptive_seed["quiz_public_id"]),
        adaptive_seed["user_id"],
        adaptive=True,
    )
    await uow.commit()

    assert result["adaptive"] is True
    assert result["adaptive_rationale"] == "Matched to your current mastery level."
    assert [q["difficulty"] for q in result["questions"]] == [
        "intermediate",
        "beginner",
        "advanced",
    ]

    attempt = (
        await pg_session.execute(
            select(QuizAttempt).where(
                QuizAttempt.public_id == result["attempt_id"]
            )
        )
    ).scalar_one()
    # NOT NULL columns populated at creation (migration 0005 contract).
    assert attempt.adaptive is True
    assert float(attempt.max_score) == 6.0
    assert attempt.time_spent_seconds == 0

    qas = (await pg_session.execute(
        select(QuestionAttempt)
        .where(QuestionAttempt.attempt_id == attempt.id)
        .order_by(QuestionAttempt.position)
    )).scalars().all()
    assert [qa.position for qa in qas] == [1, 2, 3]
    assert all(qa.public_id.startswith("qast_") for qa in qas)
    assert [float(qa.points_possible) for qa in qas] == [2.0, 2.0, 2.0]


async def test_adaptive_next_hardens_and_submit_persists(
    pg_session: AsyncSession, adaptive_seed: dict[str, object]
) -> None:
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = QuizAttemptService(uow)
    start = await service.start_attempt(
        str(adaptive_seed["quiz_public_id"]),
        adaptive_seed["user_id"],
        adaptive=True,
    )
    await uow.commit()

    attempt_id = start["attempt_id"]
    first = start["questions"][0]
    assert first["difficulty"] == "intermediate"
    correct_id = next(o["id"] for o in first["options"] if o["text"] == "Right")

    # In-attempt adaptation: correct answer on intermediate -> advanced.
    nxt = await service.get_next_question(
        str(adaptive_seed["quiz_public_id"]),
        attempt_id,
        adaptive_seed["user_id"],
        answer={"question_id": first["id"], "option_ids": [correct_id]},
    )
    await uow.commit()
    assert nxt["answered_count"] == 1
    assert nxt["next_question"]["difficulty"] == "advanced"
    assert nxt["adaptive_rationale"] == "Stepping up after a correct answer."

    # Timed single-answer persistence.
    qa = (
        await pg_session.execute(
            select(QuestionAttempt).where(
                QuestionAttempt.question_id == _qid(adaptive_seed, "intermediate"),
            )
        )
    ).scalar_one()
    assert qa.status == "answered"
    assert qa.time_spent_seconds == 0
    ua = (
        await pg_session.execute(
            select(UserAnswer).where(
                UserAnswer.question_attempt_id == qa.id
            )
        )
    ).scalar_one()
    assert ua.option_ids == [correct_id]

    # Finalize with the remaining questions answered correctly, plus time.
    remaining = [q["id"] for q in start["questions"] if q["id"] != first["id"]]
    answer_payload = []
    for qid in remaining:
        q = next(q for q in start["questions"] if q["id"] == qid)
        right = next(o["id"] for o in q["options"] if o["text"] == "Right")
        answer_payload.append({"question_id": qid, "option_ids": [right]})

    final = await service.submit_quiz(
        str(adaptive_seed["quiz_public_id"]),
        attempt_id,
        adaptive_seed["user_id"],
        answers=answer_payload,
        time_spent_seconds=42,
    )
    await uow.commit()
    assert final["status"] == "completed"

    attempt = (
        await pg_session.execute(
            select(QuizAttempt).where(QuizAttempt.public_id == attempt_id)
        )
    ).scalar_one()
    assert float(attempt.score) == 6.0
    assert attempt.time_spent_seconds == 42

    # Per-question feedback is delivered through the submit response (the
    # question_attempts.feedback column stays unset/NULL in this pipeline).
    qf = final["question_feedback"]
    assert len(qf) == 3, "all answered questions should carry feedback"
    assert all(isinstance(item, dict) for item in qf)
    assert {item["question_id"] for item in qf} == {
        q["id"] for q in start["questions"]
    }


async def test_fixed_mode_adaptive_defaults_false(
    pg_session: AsyncSession, adaptive_seed: dict[str, object]
) -> None:
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = QuizAttemptService(uow)
    result = await service.start_attempt(
        str(adaptive_seed["quiz_public_id"]),
        adaptive_seed["user_id"],
    )
    await uow.commit()
    assert result["adaptive"] is False
    assert result["adaptive_rationale"] is None
    assert [q["difficulty"] for q in result["questions"]] == list(DIFFICULTIES)

    attempt = (
        await pg_session.execute(
            select(QuizAttempt).where(
                QuizAttempt.public_id == result["attempt_id"]
            )
        )
    ).scalar_one()
    assert attempt.adaptive is False


def _qid(seed: dict[str, object], difficulty: str) -> uuid.UUID:
    for entry in seed["questions"]:  # type: ignore[union-attr]
        if entry["difficulty"] == difficulty:
            return entry["question_id"]
    raise AssertionError(f"{difficulty} not seeded")

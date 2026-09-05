"""P12 adaptive assessment tests — deterministic selector + end-to-end delivery.

The selector is pure and deterministic (no DB, no AI). The integration tests
exercise the real HTTP stack: fixed mode is byte-identical to legacy delivery,
adaptive mode starts weak-first at matched difficulty and reacts within an
attempt (Scenario A: correct -> harder; Scenario B: incorrect -> easier).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer_key import AnswerKey
from app.models.concept import Concept
from app.models.educational_memory import EducationalMemoryRecord
from app.models.presentation import Presentation
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_content import Question, QuestionOption
from app.models.quiz_version import QuizVersion
from app.services.adaptive_assessment import (
    AdaptiveCandidate,
    AnsweredQuestion,
    order_candidate_questions,
    select_next_question,
)
from tests.conftest import TEST_USER_ID

# ---------------------------------------------------------------------------
# Pure selector tests
# ---------------------------------------------------------------------------


def _candidate(
    qid: str,
    *,
    difficulty: str = "beginner",
    bloom: str = "remember",
    concept: str | None = None,
    mastery: float = 50.0,
    position: int = 1,
) -> AdaptiveCandidate:
    return AdaptiveCandidate(
        question_public_id=qid,
        position=position,
        difficulty=difficulty,
        bloom_level=bloom,
        concept_key=concept,
        mastery_score=mastery,
    )


def test_selector_deterministic() -> None:
    candidates = [
        _candidate("a", difficulty="intermediate", concept="c", mastery=65.0, position=3),
        _candidate("b", difficulty="beginner", concept="c", mastery=65.0, position=1),
        _candidate("d", difficulty="advanced", concept="c", mastery=65.0, position=2),
    ]
    first = order_candidate_questions(candidates)
    second = order_candidate_questions(candidates)
    assert [c.question_public_id for c in first] == [
        c.question_public_id for c in second
    ]


def test_selector_weak_concepts_first() -> None:
    candidates = [
        _candidate("weak_q", concept="weak", mastery=20.0, position=1),
        _candidate("mastered_q", concept="strong", mastery=95.0, position=2),
    ]
    ordered = order_candidate_questions(candidates)
    assert [c.question_public_id for c in ordered] == ["weak_q", "mastered_q"]


def test_selector_developing_before_mastered() -> None:
    candidates = [
        _candidate("mastered_q", concept="strong", mastery=95.0, position=1),
        _candidate("developing_q", concept="mid", mastery=65.0, position=2),
        _candidate("weak_q", concept="weak", mastery=20.0, position=3),
    ]
    ordered = order_candidate_questions(candidates)
    assert [c.question_public_id for c in ordered] == [
        "weak_q",
        "developing_q",
        "mastered_q",
    ]


def test_selector_developing_band_targets_intermediate() -> None:
    candidates = [
        _candidate("beginner_q", difficulty="beginner", concept="c", mastery=65.0, position=1),
        _candidate("intermediate_q", difficulty="intermediate", concept="c", mastery=65.0, position=2),
        _candidate("advanced_q", difficulty="advanced", concept="c", mastery=65.0, position=3),
    ]
    ordered = order_candidate_questions(candidates)
    assert ordered[0].question_public_id == "intermediate_q"


def test_selector_tiebreak_public_id_stable() -> None:
    candidates = [
        _candidate("q_b", concept=None, mastery=50.0, position=1),
        _candidate("q_a", concept=None, mastery=50.0, position=1),
    ]
    ordered = order_candidate_questions(candidates)
    assert [c.question_public_id for c in ordered] == ["q_a", "q_b"]


def test_selector_correct_answer_steppes_up() -> None:
    candidates = [
        _candidate("beginner_q", difficulty="beginner", concept="c", mastery=65.0, position=1),
        _candidate("intermediate_q", difficulty="intermediate", concept="c", mastery=65.0, position=2),
        _candidate("advanced_q", difficulty="advanced", concept="c", mastery=65.0, position=3),
    ]
    history = [AnsweredQuestion(concept_key="c", is_correct=True)]
    next_q, rationale = select_next_question(candidates, history)
    assert next_q is not None
    assert next_q.question_public_id == "advanced_q"
    assert rationale == "Stepping up after a correct answer."


def test_selector_incorrect_answer_steppes_down() -> None:
    candidates = [
        _candidate("beginner_q", difficulty="beginner", concept="c", mastery=65.0, position=1),
        _candidate("intermediate_q", difficulty="intermediate", concept="c", mastery=65.0, position=2),
        _candidate("advanced_q", difficulty="advanced", concept="c", mastery=65.0, position=3),
    ]
    history = [AnsweredQuestion(concept_key="c", is_correct=False)]
    next_q, rationale = select_next_question(candidates, history)
    assert next_q is not None
    assert next_q.question_public_id == "beginner_q"
    assert rationale == "Returning to an easier level to build your confidence."


def test_selector_no_remaining_candidates() -> None:
    next_q, rationale = select_next_question([], [])
    assert next_q is None
    assert rationale == ""


def test_selector_weak_band_targets_beginner() -> None:
    candidates = [
        _candidate("beginner_q", difficulty="beginner", concept="c", mastery=20.0, position=1),
        _candidate("intermediate_q", difficulty="intermediate", concept="c", mastery=20.0, position=2),
        _candidate("advanced_q", difficulty="advanced", concept="c", mastery=20.0, position=3),
    ]
    ordered = order_candidate_questions(candidates)
    assert ordered[0].question_public_id == "beginner_q"


# ---------------------------------------------------------------------------
# End-to-end fixtures
# ---------------------------------------------------------------------------


async def _seed_quiz(
    db_session: AsyncSession,
    *,
    difficulties: list[str] = ("beginner", "intermediate", "advanced"),
    owner: uuid.UUID = TEST_USER_ID,
    with_concept: bool = True,
) -> dict[str, Any]:
    from app.models.user import User

    if owner != TEST_USER_ID:
        existing = await db_session.execute(select(User.id).where(User.id == owner))
        if existing.scalar_one_or_none() is None:
            db_session.add(
                User(
                    id=owner,
                    email=f"{owner}@example.com",
                    name="Other Owner",
                )
            )

    presentation = Presentation(
        title="Adaptive Test Presentation",
        owner_id=owner,
        status="published",
        slide_count=1,
    )
    db_session.add(presentation)
    await db_session.flush()

    concept = None
    if with_concept:
        concept = Concept(
            name="Adaptive Under Test",
            topic="p12",
            presentation_id=presentation.id,
        )
        db_session.add(concept)
        await db_session.flush()

    quiz = Quiz(
        presentation_id=presentation.id,
        user_id=owner,
        status="published",
        mode="practice",
        title="Adaptive Test Quiz",
        description="Deterministic adaptive delivery",
        difficulty="intermediate",
        question_count=len(difficulties),
        max_attempts_per_user=5,
        passing_score=60.0,
        shuffle_questions=False,
        shuffle_options=False,
        show_feedback_after=True,
        latest_version=1,
        published_version=1,
    )
    db_session.add(quiz)
    await db_session.flush()

    version = QuizVersion(
        quiz_id=quiz.id,
        version=1,
        status="published",
        title="Adaptive Test Quiz v1",
    )
    db_session.add(version)
    await db_session.flush()

    question_meta: list[dict[str, Any]] = []
    for pos, difficulty in enumerate(difficulties, start=1):
        q = Question(
            quiz_version_id=version.id,
            position=pos,
            question_type="multiple_choice",
            stem=f"Adaptive question {pos} ({difficulty})",
            points=2,
            bloom_level="remember",
            difficulty=difficulty,
            concept_id=concept.id if concept else None,
        )
        db_session.add(q)
        await db_session.flush()
        wrong = QuestionOption(question_id=q.id, position=1, text="Wrong", is_correct=False)
        right = QuestionOption(question_id=q.id, position=2, text="Right", is_correct=True)
        db_session.add_all([wrong, right])
        await db_session.flush()
        db_session.add(
            AnswerKey(
                question_id=q.id,
                answer_type="multiple_choice",
                correct_option_ids=[right.public_id],
            )
        )
        question_meta.append(
            {
                "question_id": str(q.public_id),
                "difficulty": difficulty,
                "correct_option_id": str(right.public_id),
                "wrong_option_id": str(wrong.public_id),
            }
        )

    await db_session.flush()
    await db_session.commit()
    return {
        "quiz_id": str(quiz.public_id),
        "concept_public_id": str(concept.public_id) if concept else None,
        "questions": question_meta,
    }


async def _seed_memory(
    db_session: AsyncSession,
    concept_public_id: str | None,
    mastery: float,
) -> None:
    from sqlalchemy import delete as sa_delete

    await db_session.execute(
        sa_delete(EducationalMemoryRecord).where(
            EducationalMemoryRecord.user_id == TEST_USER_ID
        )
    )
    await db_session.flush()
    now = datetime.now(UTC).timestamp()
    memory: dict[str, Any] = {
        "user_id": str(TEST_USER_ID),
        "profile": {
            "user_id": str(TEST_USER_ID),
            "learning_pace": "moderate",
            "total_study_minutes": 0.0,
            "average_mastery": mastery,
            "streak_days": 1,
        },
        "concept_records": {},
        "mastered_concepts": [],
        "developing_concepts": [],
        "weak_concepts": [],
        "preferences": {},
        "revision_queue": [],
        "milestones": [],
        "created_at": now,
        "updated_at": now,
    }
    if concept_public_id:
        memory["concept_records"][concept_public_id] = {
            "concept_id": concept_public_id,
            "concept_name": "Adaptive Under Test",
            "first_learned_at": now,
            "last_reviewed_at": now,
            "mastery_score": mastery,
            "review_count": 1,
            "trend": "stable",
            "confidence_score": 0.5,
        }
        if mastery < 50:
            memory["weak_concepts"] = [concept_public_id]
        elif mastery < 85:
            memory["developing_concepts"] = [concept_public_id]
        else:
            memory["mastered_concepts"] = [concept_public_id]
    db_session.add(
        EducationalMemoryRecord(user_id=TEST_USER_ID, memory_data=memory)
    )
    await db_session.commit()


@pytest_asyncio.fixture
async def adaptive_quiz(db_session: AsyncSession) -> dict[str, Any]:
    meta = await _seed_quiz(db_session)
    await _seed_memory(db_session, meta["concept_public_id"], mastery=65.0)
    return meta


# ---------------------------------------------------------------------------
# Delivery integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fixed_mode_unchanged(
    client: AsyncClient, adaptive_quiz: dict[str, Any]
) -> None:
    resp = await client.post(f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts")
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["adaptive"] is False
    assert data["adaptive_rationale"] is None
    assert [q["difficulty"] for q in data["questions"]] == [
        "beginner",
        "intermediate",
        "advanced",
    ]


@pytest.mark.asyncio
async def test_adaptive_start_orders_and_persists(
    client: AsyncClient, adaptive_quiz: dict[str, Any]
) -> None:
    resp = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts",
        json={"adaptive": True},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["adaptive"] is True
    assert data["adaptive_rationale"] == "Matched to your current mastery level."
    # Developing band (mastery 65) targets intermediate first.
    assert [q["difficulty"] for q in data["questions"]] == [
        "intermediate",
        "beginner",
        "advanced",
    ]
    assert sum(q["points"] for q in data["questions"]) == 6


@pytest.mark.asyncio
async def test_adaptive_start_without_metadata_degrades_to_position(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    meta = await _seed_quiz(db_session, with_concept=False)
    resp = await client.post(
        f"/api/v1/quizzes/{meta['quiz_id']}/attempts",
        json={"adaptive": True},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["adaptive"] is True
    assert data["adaptive_rationale"] == "Matched to your current mastery level."
    # No concept metadata -> default band (developing, target intermediate),
    # deterministic fitness/position ordering (still adaptive, no fallback flag).
    assert [q["difficulty"] for q in data["questions"]] == [
        "intermediate",
        "beginner",
        "advanced",
    ]


@pytest.mark.asyncio
async def test_next_first_question_no_answer(
    client: AsyncClient, adaptive_quiz: dict[str, Any]
) -> None:
    start = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts",
        json={"adaptive": True},
    )
    attempt_id = start.json()["data"]["attempt_id"]
    resp = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts/{attempt_id}/next",
        json={},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["completed"] is False
    assert data["remaining_count"] == 3
    assert data["next_question"]["difficulty"] == "intermediate"


@pytest.mark.asyncio
async def test_scenario_a_correct_hardens(
    client: AsyncClient, adaptive_quiz: dict[str, Any]
) -> None:
    start = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts",
        json={"adaptive": True},
    )
    attempt_id = start.json()["data"]["attempt_id"]
    first = start.json()["data"]["questions"][0]
    assert first["difficulty"] == "intermediate"
    correct_id = next(
        o["id"] for o in first["options"] if o["text"] == "Right"
    )
    resp = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts/{attempt_id}/next",
        json={
            "answer": {
                "question_id": first["id"],
                "option_ids": [correct_id],
            }
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["answered_count"] == 1
    assert data["remaining_count"] == 2
    # Correct answer on intermediate -> step up to advanced.
    assert data["next_question"]["difficulty"] == "advanced"
    assert data["adaptive_rationale"] == "Stepping up after a correct answer."


@pytest.mark.asyncio
async def test_scenario_b_incorrect_softens(
    client: AsyncClient, adaptive_quiz: dict[str, Any]
) -> None:
    start = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts",
        json={"adaptive": True},
    )
    attempt_id = start.json()["data"]["attempt_id"]
    first = start.json()["data"]["questions"][0]
    assert first["difficulty"] == "intermediate"
    wrong_id = next(
        o["id"] for o in first["options"] if o["text"] == "Wrong"
    )
    resp = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts/{attempt_id}/next",
        json={
            "answer": {
                "question_id": first["id"],
                "option_ids": [wrong_id],
            }
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    # Incorrect answer on intermediate -> step down to beginner.
    assert data["next_question"]["difficulty"] == "beginner"
    assert data["adaptive_rationale"] == (
        "Returning to an easier level to build your confidence."
    )


@pytest.mark.asyncio
async def test_fixed_mode_next_is_positional(
    client: AsyncClient, adaptive_quiz: dict[str, Any]
) -> None:
    start = await client.post(f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts")
    attempt_id = start.json()["data"]["attempt_id"]
    first = start.json()["data"]["questions"][0]
    assert first["difficulty"] == "beginner"
    resp = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts/{attempt_id}/next",
        json={
            "answer": {
                "question_id": first["id"],
                "option_ids": [next(o["id"] for o in first["options"] if o["text"] == "Wrong")],
            }
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["adaptive"] is False
    assert data["next_question"]["difficulty"] == "intermediate"


@pytest.mark.asyncio
async def test_resume_keeps_adaptive_order(
    client: AsyncClient, adaptive_quiz: dict[str, Any]
) -> None:
    start = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts",
        json={"adaptive": True},
    )
    attempt_id = start.json()["data"]["attempt_id"]
    resume = await client.post(f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts")
    assert resume.status_code == 201
    data = resume.json()["data"]
    assert data["attempt_id"] == attempt_id
    assert data["adaptive"] is True
    assert [q["difficulty"] for q in data["questions"]] == [
        "intermediate",
        "beginner",
        "advanced",
    ]


@pytest.mark.asyncio
async def test_adaptive_requires_two_questions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    meta = await _seed_quiz(db_session, difficulties=["beginner"])
    resp = await client.post(
        f"/api/v1/quizzes/{meta['quiz_id']}/attempts",
        json={"adaptive": True},
    )
    assert resp.status_code == 422
    quiz_row = (
        await db_session.execute(
            select(Quiz).where(Quiz.public_id == meta["quiz_id"])
        )
    ).scalar_one()
    rows = (
        await db_session.execute(
            select(QuizAttempt).where(QuizAttempt.quiz_id == quiz_row.id)
        )
    ).scalars().all()
    assert len(rows) == 0, "No attempt row should be created for a rejected start"


@pytest.mark.asyncio
async def test_ownership_enforced_on_adaptive(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    other = uuid.UUID("00000000-0000-0000-0000-000000009999")
    meta = await _seed_quiz(db_session, owner=other)
    start = await client.post(
        f"/api/v1/quizzes/{meta['quiz_id']}/attempts",
        json={"adaptive": True},
    )
    assert start.status_code == 404


@pytest.mark.asyncio
async def test_cross_user_next_is_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    other = uuid.UUID("00000000-0000-0000-0000-000000009998")
    meta = await _seed_quiz(db_session, owner=other, with_concept=False)
    resp = await client.post(
        f"/api/v1/quizzes/{meta['quiz_id']}/attempts/{uuid.uuid4()}/next",
        json={},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_next_rejects_unknown_question(
    client: AsyncClient, adaptive_quiz: dict[str, Any]
) -> None:
    start = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts",
        json={"adaptive": True},
    )
    attempt_id = start.json()["data"]["attempt_id"]
    resp = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts/{attempt_id}/next",
        json={
            "answer": {"question_id": "nonexistent_question", "option_ids": []}
        },
    )
    # Unknown question is rejected identically to any other non-owned resource.
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_next_after_submit_is_conflict(
    client: AsyncClient, adaptive_quiz: dict[str, Any]
) -> None:
    start = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts",
        json={"adaptive": True},
    )
    attempt_id = start.json()["data"]["attempt_id"]
    answers = [
        {
            "question_id": q["id"],
            "option_ids": [
                next(o["id"] for o in q["options"] if o["text"] == "Right")
            ],
        }
        for q in start.json()["data"]["questions"]
    ]
    submit = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts/{attempt_id}/submit",
        json={"time_spent_seconds": 12},
    )
    if submit.status_code != 200:
        await client.post(
            f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts/{attempt_id}/submit",
            json={"answers": answers, "time_spent_seconds": 12},
        )
    resp = await client.post(
        f"/api/v1/quizzes/{adaptive_quiz['quiz_id']}/attempts/{attempt_id}/next",
        json={},
    )
    assert resp.status_code == 409

"""P2 E2E test: full learning effectiveness chain with real DB operations.

Demonstrates the complete effectiveness measurement flow:
  baseline assessment → learning events → quiz → mastery → post-assessment → gain

Two synthetic test users demonstrate comparison-group infrastructure:
  User A: "reference" group
  User B: "eduvision" group

All data is SYNTHETIC TEST DATA. This proves software behavior only.
It does NOT prove that humans learn better.

Chain:
  1. Create presentation
  2. Create concept + quiz with questions
  3. User A starts baseline assessment (reference group)
  4. User A takes baseline quiz → low score
  5. User A records baseline score on assessment
  6. User A records learning events
  7. User A takes post-quiz → higher score
  8. User A records post score → learning gain computed
  9. User B starts baseline assessment (eduvision group)
 10. User B completes full chain
 11. Verify groups remain separated
 12. Verify comparison returns correct group-specific data
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.concept import Concept
from app.models.presentation import Presentation
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_content import Question, QuestionOption
from app.models.quiz_version import QuizVersion
from app.services.effectiveness_service import EffectivenessService
from app.services.learning_event_service import LearningEventService

pytestmark = pytest.mark.integration

TEST_USER_A = uuid.UUID("10000000-0000-0000-0000-000000000001")
TEST_USER_B = uuid.UUID("20000000-0000-0000-0000-000000000002")


async def _ensure_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Persist a user row so FK constraints are satisfied.

    The test conftest enables SQLite FK enforcement (PRAGMA foreign_keys=ON),
    so any row referencing a non-existent user is rejected.
    """
    from app.core.security import hash_password
    from app.models.user import User

    existing = await db.execute(select(User).where(User.id == user_id))
    if existing.scalar_one_or_none() is None:
        db.add(
            User(
                id=user_id,
                email=f"u{user_id.hex}@test.local",
                name="Test User",
                password_hash=hash_password("testpassword123"),
            )
        )
    await db.flush()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_presentation(db: AsyncSession, owner_id: uuid.UUID) -> Presentation:
    pres = Presentation(
        public_id=f"pres_{uuid.uuid4().hex[:16]}",
        title="E2E Effectiveness Test",
        description="P2 E2E chain test presentation",
        status="ready",
        owner_id=owner_id,
    )
    db.add(pres)
    await db.flush()
    await db.refresh(pres)
    return pres


async def _create_concept(db: AsyncSession) -> Concept:
    concept = Concept(
        name="Linear Algebra Basics",
        description="Vectors, matrices, eigenvalues",
        topic="Mathematics",
        difficulty_level="beginner",
    )
    db.add(concept)
    await db.flush()
    await db.refresh(concept)
    return concept


async def _create_quiz_with_questions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    presentation_id: uuid.UUID,
    num_questions: int = 3,
) -> tuple[Quiz, list[Question], QuizVersion]:
    await _ensure_user(db, user_id)

    quiz = Quiz(
        public_id=f"quiz_{uuid.uuid4().hex[:16]}",
        user_id=user_id,
        presentation_id=presentation_id,
        status="published",
        mode="practice",
        assessment_type="normal",
        question_count=num_questions,
        latest_version=1,
    )
    db.add(quiz)
    await db.flush()

    version = QuizVersion(
        public_id=f"qver_{uuid.uuid4().hex[:16]}",
        quiz_id=quiz.id,
        version=1,
        status="published",
    )
    db.add(version)
    await db.flush()

    questions = []
    for i in range(num_questions):
        q = Question(
            public_id=f"q_{uuid.uuid4().hex[:16]}",
            quiz_version_id=version.id,
            position=i + 1,
            question_type="multiple_choice",
            stem=f"Question {i + 1}: What is the result of vector addition?",
            points=1,
        )
        db.add(q)
        await db.flush()

        correct = QuestionOption(
            public_id=f"opt_{uuid.uuid4().hex[:16]}",
            question_id=q.id,
            position=1,
            text="Component-wise sum",
            is_correct=True,
        )
        wrong = QuestionOption(
            public_id=f"opt_{uuid.uuid4().hex[:16]}",
            question_id=q.id,
            position=2,
            text="Dot product",
            is_correct=False,
        )
        db.add_all([correct, wrong])
        await db.flush()
        questions.append((q, correct, wrong))

    return quiz, questions, version


async def _take_quiz(
    db: AsyncSession,
    quiz: Quiz,
    version: QuizVersion,
    questions: list[tuple[Question, QuestionOption, QuestionOption]],
    user_id: uuid.UUID,
    *,
    score_pct: float,
) -> QuizAttempt:
    """Simulate a quiz attempt with a specific score percentage.

    This creates the attempt directly with the desired score to focus
    on the effectiveness chain rather than quiz-scoring internals.
    """
    await _ensure_user(db, user_id)

    attempt = QuizAttempt(
        public_id=f"qatt_{uuid.uuid4().hex[:16]}",
        quiz_id=quiz.id,
        quiz_version_id=version.id,
        user_id=user_id,
        status="completed",
        score=score_pct / 100.0 * len(questions),
        max_score=float(len(questions)),
        percent_score=score_pct,
        time_spent_seconds=120,
    )
    db.add(attempt)
    await db.flush()
    await db.refresh(attempt)
    return attempt


# ---------------------------------------------------------------------------
# The E2E Chain
# ---------------------------------------------------------------------------


class TestP2EffectivenessE2E:
    """Full effectiveness chain: baseline → learning → post → gain → comparison.

    All data is SYNTHETIC TEST DATA.
    """

    async def test_full_effectiveness_chain(self, db_session: AsyncSession):
        # Ensure synthetic users exist so FK constraints are satisfied
        await _ensure_user(db_session, TEST_USER_A)
        await _ensure_user(db_session, TEST_USER_B)

        # ── Step 1: Create presentation and concept ───────────────────────
        pres_a = await _create_presentation(db_session, TEST_USER_A)
        await _create_concept(db_session)

        # ── Step 2: Create quiz with questions ────────────────────────────
        quiz_a, questions_a, version_a = await _create_quiz_with_questions(
            db_session,
            user_id=TEST_USER_A,
            presentation_id=pres_a.id,
            num_questions=3,
        )
        assert len(questions_a) == 3

        # ── Step 3: User A starts baseline assessment (reference group) ───
        effectiveness_svc = EffectivenessService(db_session)
        assessment_a = await effectiveness_svc.get_or_create_assessment(
            user_id=TEST_USER_A,
            presentation_id=pres_a.id,
            experiment_group="reference",
        )
        assert assessment_a.experiment_group == "reference"
        assert assessment_a.baseline_score is None

        # ── Step 4: User A takes baseline quiz → 40% ─────────────────────
        baseline_attempt_a = await _take_quiz(
            db_session, quiz_a, version_a, questions_a, TEST_USER_A,
            score_pct=40.0,
        )
        assert baseline_attempt_a.percent_score == 40.0

        # ── Step 5: Record baseline score on assessment ───────────────────
        assessment_a = await effectiveness_svc.record_quiz_score(
            user_id=TEST_USER_A,
            assessment_id=assessment_a.id,
            assessment_type="baseline",
            quiz_id=quiz_a.id,
            score=40.0,
            concept_scores={"vectors": 30.0, "matrices": 50.0},
        )
        assert assessment_a.baseline_score == 40.0
        assert assessment_a.status == "in_progress"

        # ── Step 6: Record learning events ────────────────────────────────
        event_svc = LearningEventService(db_session)
        await event_svc.record(
            user_id=TEST_USER_A,
            event_type="lesson_started",
            resource_type="lesson",
            resource_id="les_001",
            presentation_id=pres_a.id,
        )
        await event_svc.record(
            user_id=TEST_USER_A,
            event_type="lesson_completed",
            resource_type="lesson",
            resource_id="les_001",
            presentation_id=pres_a.id,
        )
        await event_svc.record(
            user_id=TEST_USER_A,
            event_type="quiz_completed",
            resource_type="quiz",
            resource_id=str(quiz_a.public_id),
            presentation_id=pres_a.id,
            metadata_json={"score": 40.0, "attempt": "baseline"},
        )
        events_summary = await event_svc.summary_for_presentation(
            TEST_USER_A, pres_a.id,
        )
        assert events_summary["total_events"] == 3

        # Store events summary on assessment (serialize datetimes for JSONB)
        serializable_summary = {
            "total_events": events_summary["total_events"],
            "event_types": events_summary["event_types"],
            "first_event_at": str(events_summary["first_event_at"]) if events_summary["first_event_at"] else None,
            "last_event_at": str(events_summary["last_event_at"]) if events_summary["last_event_at"] else None,
        }
        assessment_a.events_summary = serializable_summary

        # ── Step 7: User A takes post-quiz → 80% ─────────────────────────
        post_attempt_a = await _take_quiz(
            db_session, quiz_a, version_a, questions_a, TEST_USER_A,
            score_pct=80.0,
        )
        assert post_attempt_a.percent_score == 80.0

        # ── Step 8: Record post score → learning gain computed ────────────
        assessment_a = await effectiveness_svc.record_quiz_score(
            user_id=TEST_USER_A,
            assessment_id=assessment_a.id,
            assessment_type="post",
            quiz_id=quiz_a.id,
            score=80.0,
            concept_scores={"vectors": 90.0, "matrices": 70.0},
        )
        assert assessment_a.post_score == 80.0
        assert assessment_a.absolute_gain == 40.0
        assert assessment_a.normalized_gain == pytest.approx(40.0 / 60.0)
        assert assessment_a.status == "completed"

        # ── Verify concept improvements ───────────────────────────────────
        gain = effectiveness_svc._format_gain(assessment_a)
        assert gain["experiment_group"] == "reference"
        assert len(gain["concept_improvements"]) == 2
        assert gain["concept_improvements"][0]["pre"] is not None
        assert gain["concept_improvements"][0]["post"] is not None

        # ── Step 9: User B — eduvision group — complete chain ─────────────
        pres_b = await _create_presentation(db_session, TEST_USER_B)
        quiz_b, questions_b, version_b = await _create_quiz_with_questions(
            db_session,
            user_id=TEST_USER_B,
            presentation_id=pres_b.id,
            num_questions=3,
        )

        assessment_b = await effectiveness_svc.get_or_create_assessment(
            user_id=TEST_USER_B,
            presentation_id=pres_b.id,
            experiment_group="eduvision",
        )

        await _take_quiz(
            db_session, quiz_b, version_b, questions_b, TEST_USER_B,
            score_pct=30.0,
        )
        assessment_b = await effectiveness_svc.record_quiz_score(
            user_id=TEST_USER_B,
            assessment_id=assessment_b.id,
            assessment_type="baseline",
            quiz_id=quiz_b.id,
            score=30.0,
        )

        await _take_quiz(
            db_session, quiz_b, version_b, questions_b, TEST_USER_B,
            score_pct=90.0,
        )
        assessment_b = await effectiveness_svc.record_quiz_score(
            user_id=TEST_USER_B,
            assessment_id=assessment_b.id,
            assessment_type="post",
            quiz_id=quiz_b.id,
            score=90.0,
        )

        assert assessment_b.absolute_gain == 60.0
        assert assessment_b.normalized_gain == pytest.approx(60.0 / 70.0)
        assert assessment_b.experiment_group == "eduvision"

        # ── Step 10: Verify groups remain separated ───────────────────────
        gain_a = await effectiveness_svc.compute_learning_gain(
            user_id=TEST_USER_A, presentation_id=pres_a.id,
        )
        gain_b = await effectiveness_svc.compute_learning_gain(
            user_id=TEST_USER_B, presentation_id=pres_b.id,
        )
        assert gain_a is not None
        assert gain_b is not None
        assert gain_a["experiment_group"] == "reference"
        assert gain_b["experiment_group"] == "eduvision"
        assert gain_a["absolute_gain"] == 40.0
        assert gain_b["absolute_gain"] == 60.0

        # ── Step 11: Verify comparison returns correct group data ─────────
        comparison = await effectiveness_svc.compare_groups(
            group_a="reference", group_b="eduvision",
        )
        assert comparison["group_a"] == "reference"
        assert comparison["group_b"] == "eduvision"
        assert comparison["group_a_count"] == 1
        assert comparison["group_b_count"] == 1
        assert comparison["group_a_avg_absolute_gain"] == 40.0
        assert comparison["group_b_avg_absolute_gain"] == 60.0
        assert comparison["group_a_avg_baseline"] == 40.0
        assert comparison["group_b_avg_baseline"] == 30.0
        assert comparison["group_a_completed"] == 1
        assert comparison["group_b_completed"] == 1

        # ── Step 12: Verify user isolation ────────────────────────────────
        summary_a = await effectiveness_svc.user_summary(TEST_USER_A)
        summary_b = await effectiveness_svc.user_summary(TEST_USER_B)
        assert summary_a["total_assessments"] == 1
        assert summary_b["total_assessments"] == 1
        # User A's data doesn't leak into User B's summary
        assert summary_a["avg_absolute_gain"] == 40.0
        assert summary_b["avg_absolute_gain"] == 60.0

        # ── Step 13: Verify learning time tracking ────────────────────────
        await effectiveness_svc.set_learning_time(
            user_id=TEST_USER_A,
            presentation_id=pres_a.id,
            seconds=300,
        )
        gain_a_updated = await effectiveness_svc.compute_learning_gain(
            user_id=TEST_USER_A, presentation_id=pres_a.id,
        )
        assert gain_a_updated["total_learning_time_seconds"] == 300


class TestP2EffectivenessE2ERetention:
    """Extended chain including retention assessment.

    All data is SYNTHETIC TEST DATA.
    """

    async def test_retention_chain(self, db_session: AsyncSession):
        user_id = uuid.uuid4()
        await _ensure_user(db_session, user_id)
        await _ensure_user(db_session, TEST_USER_B)
        pres = await _create_presentation(db_session, user_id)
        quiz, questions, version = await _create_quiz_with_questions(
            db_session, user_id=user_id, presentation_id=pres.id, num_questions=3,
        )

        effectiveness_svc = EffectivenessService(db_session)

        # Start baseline
        assessment = await effectiveness_svc.get_or_create_assessment(
            user_id=user_id, presentation_id=pres.id,
            experiment_group="retention_test",
        )

        # Baseline: 50%
        await _take_quiz(db_session, quiz, version, questions, user_id, score_pct=50.0)
        assessment = await effectiveness_svc.record_quiz_score(
            user_id=user_id,
            assessment_id=assessment.id, assessment_type="baseline",
            quiz_id=quiz.id, score=50.0,
        )

        # Post: 85%
        await _take_quiz(db_session, quiz, version, questions, user_id, score_pct=85.0)
        assessment = await effectiveness_svc.record_quiz_score(
            user_id=user_id,
            assessment_id=assessment.id, assessment_type="post",
            quiz_id=quiz.id, score=85.0,
        )
        assert assessment.absolute_gain == 35.0

        # Retention: 70% (some forgetting)
        await _take_quiz(db_session, quiz, version, questions, user_id, score_pct=70.0)
        assessment = await effectiveness_svc.record_quiz_score(
            user_id=user_id,
            assessment_id=assessment.id, assessment_type="retention",
            quiz_id=quiz.id, score=70.0,
        )

        assert assessment.retention_loss == 15.0
        assert assessment.retention_pct == pytest.approx(70.0 / 85.0 * 100.0)
        assert assessment.status == "completed"

        # Verify full gain
        gain = effectiveness_svc._format_gain(assessment)
        assert gain["experiment_group"] == "retention_test"
        assert gain["retention_loss"] == 15.0
        assert gain["retention_pct"] is not None

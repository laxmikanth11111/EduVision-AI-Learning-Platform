"""P2 Learning Effectiveness — comprehensive test suite."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import NotFoundError, ValidationError
from app.models.effectiveness_assessment import EffectivenessAssessment
from app.models.learning_event import LearningEvent
from app.models.presentation import Presentation
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_content import Question, QuestionOption
from app.models.quiz_version import QuizVersion
from app.models.user_feedback import UserFeedback
from app.schemas.effectiveness import AssessmentType
from app.services.effectiveness_service import EffectivenessService
from app.services.feedback_service import UserFeedbackService
from app.services.learning_event_service import LearningEventService
from tests.conftest import TEST_USER_ID, TestSessionLocal

# ── Helpers ──────────────────────────────────────────────────────────────


async def _create_presentation(session) -> Presentation:
    pres = Presentation(
        public_id=f"pres_{uuid.uuid4().hex[:16]}",
        title="Test Presentation",
        description="A test presentation for effectiveness",
        status="ready",
        owner_id=TEST_USER_ID,
    )
    session.add(pres)
    await session.flush()
    return pres


async def _create_quiz_with_attempt(session, presentation) -> QuizAttempt:
    quiz = Quiz(
        public_id=f"quiz_{uuid.uuid4().hex[:16]}",
        presentation_id=presentation.id,
        user_id=TEST_USER_ID,
        status="published",
        mode="practice",
        assessment_type="normal",
        question_count=2,
        latest_version=1,
    )
    session.add(quiz)
    await session.flush()

    version = QuizVersion(
        public_id=f"qver_{uuid.uuid4().hex[:16]}",
        quiz_id=quiz.id,
        version=1,
        status="published",
    )
    session.add(version)
    await session.flush()

    q1 = Question(
        public_id=f"q_{uuid.uuid4().hex[:16]}",
        quiz_version_id=version.id,
        position=1,
        question_type="multiple_choice",
        stem="What is 2+2?",
        points=1,
    )
    q2 = Question(
        public_id=f"q_{uuid.uuid4().hex[:16]}",
        quiz_version_id=version.id,
        position=2,
        question_type="multiple_choice",
        stem="What is 3+3?",
        points=1,
    )
    session.add_all([q1, q2])
    await session.flush()

    for q in [q1, q2]:
        opt = QuestionOption(
            id=uuid.uuid4(),
            public_id=f"opt_{uuid.uuid4().hex[:16]}",
            question_id=q.id,
            position=1,
            text="4" if "2+2" in q.stem else "6",
            is_correct=True,
        )
        session.add(opt)
    await session.flush()

    attempt = QuizAttempt(
        public_id=f"qatt_{uuid.uuid4().hex[:16]}",
        quiz_id=quiz.id,
        quiz_version_id=version.id,
        user_id=TEST_USER_ID,
        status="completed",
        score=1.5,
        max_score=2.0,
        percent_score=75.0,
        time_spent_seconds=120,
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def _create_presentation_committed() -> Presentation:
    """Create a presentation in a committed session (for API tests)."""
    async with TestSessionLocal() as session:
        pres = Presentation(
            public_id=f"pres_{uuid.uuid4().hex[:16]}",
            title="API Test Presentation",
            description="Created for API tests",
            status="ready",
            owner_id=TEST_USER_ID,
        )
        session.add(pres)
        await session.commit()
        await session.refresh(pres)
        return pres


async def _ensure_user(session, user_id):
    """Persist a user row so FK constraints are satisfied.

    The test conftest enables SQLite FK enforcement (PRAGMA foreign_keys=ON),
    so any row referencing a non-existent user is rejected. Tests that create
    records owned by ad-hoc users must first insert the user.
    """
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models.user import User

    existing = await session.execute(select(User).where(User.id == user_id))
    if existing.scalar_one_or_none() is None:
        session.add(
            User(
                id=user_id,
                email=f"u{user_id.hex}@test.local",
                name="Test User",
                password_hash=hash_password("testpassword123"),
            )
        )
    await session.flush()
    return user_id


# ── P2.3: Learning Event Service Tests ──────────────────────────────────


class TestLearningEventService:
    async def test_record_event(self, db_session):
        service = LearningEventService(db_session)
        event = await service.record(
            user_id=TEST_USER_ID,
            event_type="lesson_started",
            resource_type="lesson",
            resource_id="les_123",
            presentation_id=uuid.uuid4(),
        )
        assert event.public_id is not None
        assert event.event_type == "lesson_started"
        assert event.user_id == TEST_USER_ID

    async def test_record_event_with_metadata(self, db_session):
        service = LearningEventService(db_session)
        event = await service.record(
            user_id=TEST_USER_ID,
            event_type="quiz_completed",
            metadata_json={"score": 85.0, "questions": 10},
        )
        assert event.metadata_json == {"score": 85.0, "questions": 10}

    async def test_list_events(self, db_session):
        service = LearningEventService(db_session)
        pres_id = uuid.uuid4()
        for i in range(5):
            await service.record(
                user_id=TEST_USER_ID,
                event_type="lesson_started" if i % 2 == 0 else "lesson_completed",
                presentation_id=pres_id,
            )
        events, total = await service.list_for_user(
            TEST_USER_ID, presentation_id=pres_id,
        )
        assert total == 5
        assert len(events) == 5

    async def test_list_events_filter_type(self, db_session):
        service = LearningEventService(db_session)
        pres_id = uuid.uuid4()
        await service.record(user_id=TEST_USER_ID, event_type="lesson_started", presentation_id=pres_id)
        await service.record(user_id=TEST_USER_ID, event_type="lesson_completed", presentation_id=pres_id)
        events, total = await service.list_for_user(
            TEST_USER_ID, event_type="lesson_started", presentation_id=pres_id,
        )
        assert total == 1

    async def test_summary_for_presentation(self, db_session):
        service = LearningEventService(db_session)
        pres_id = uuid.uuid4()
        await service.record(user_id=TEST_USER_ID, event_type="lesson_started", presentation_id=pres_id)
        await service.record(user_id=TEST_USER_ID, event_type="quiz_completed", presentation_id=pres_id)
        summary = await service.summary_for_presentation(TEST_USER_ID, pres_id)
        assert summary["total_events"] == 2
        assert summary["event_types"]["lesson_started"] == 1
        assert summary["event_types"]["quiz_completed"] == 1

    async def test_empty_summary(self, db_session):
        service = LearningEventService(db_session)
        summary = await service.summary_for_presentation(TEST_USER_ID, uuid.uuid4())
        assert summary["total_events"] == 0

    async def test_user_isolation(self, db_session):
        service = LearningEventService(db_session)
        other_user = await _ensure_user(db_session, uuid.uuid4())
        await service.record(user_id=TEST_USER_ID, event_type="lesson_started")
        await service.record(user_id=other_user, event_type="lesson_started")
        events, total = await service.list_for_user(TEST_USER_ID)
        assert total == 1


# ── P2.2 + P2.4: Assessment Service Tests ──────────────────────────────


class TestEffectivenessAssessment:
    async def test_get_or_create_assessment(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        a1 = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        a2 = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assert a1.id == a2.id

    async def test_start_baseline_assessment(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        result = await service.start_assessment(
            user_id=TEST_USER_ID,
            presentation_id=presentation.id,
            assessment_type=AssessmentType.BASELINE,
        )
        assert result["assessment_type"] == "baseline"
        assert "assessment_public_id" in result

    async def test_start_post_assessment(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        result = await service.start_assessment(
            user_id=TEST_USER_ID,
            presentation_id=presentation.id,
            assessment_type=AssessmentType.POST,
        )
        assert result["assessment_type"] == "post"

    async def test_start_retention_assessment(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        result = await service.start_assessment(
            user_id=TEST_USER_ID,
            presentation_id=presentation.id,
            assessment_type=AssessmentType.RETENTION,
            retention_delay_hours=72,
        )
        assert result["assessment_type"] == "retention"

    async def test_invalid_assessment_type(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        with pytest.raises(ValidationError):
            await service.start_assessment(
                user_id=TEST_USER_ID,
                presentation_id=presentation.id,
                assessment_type="invalid",
            )

    async def test_record_attempt_score_baseline(self, db_session):
        presentation = await _create_presentation(db_session)
        attempt = await _create_quiz_with_attempt(db_session, presentation)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        updated = await service.record_attempt_score(
            user_id=TEST_USER_ID,
            assessment_id=assessment.id,
            assessment_type=AssessmentType.BASELINE,
            quiz_attempt_id=attempt.id,
        )
        assert updated.baseline_score == 75.0
        assert updated.baseline_quiz_id == attempt.quiz_id

    async def test_record_attempt_score_post(self, db_session):
        presentation = await _create_presentation(db_session)
        attempt = await _create_quiz_with_attempt(db_session, presentation)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        updated = await service.record_attempt_score(
            user_id=TEST_USER_ID,
            assessment_id=assessment.id,
            assessment_type=AssessmentType.POST,
            quiz_attempt_id=attempt.id,
        )
        assert updated.post_score == 75.0

    async def test_record_with_concept_scores(self, db_session):
        presentation = await _create_presentation(db_session)
        attempt = await _create_quiz_with_attempt(db_session, presentation)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        updated = await service.record_attempt_score(
            user_id=TEST_USER_ID,
            assessment_id=assessment.id,
            assessment_type=AssessmentType.BASELINE,
            quiz_attempt_id=attempt.id,
            concept_scores={"algebra": 60.0, "geometry": 80.0},
        )
        assert updated.baseline_concept_scores == {"algebra": 60.0, "geometry": 80.0}

    async def test_nonexistent_assessment(self, db_session):
        service = EffectivenessService(db_session)
        with pytest.raises(NotFoundError):
            await service.record_attempt_score(
                user_id=TEST_USER_ID,
                assessment_id=uuid.uuid4(),
                assessment_type=AssessmentType.BASELINE,
                quiz_attempt_id=uuid.uuid4(),
            )


# ── P2.5: Learning Gain Tests ───────────────────────────────────────────


class TestLearningGain:
    async def test_gain_calculation(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.baseline_score = 40.0
        assessment.post_score = 80.0
        service._compute_gains(assessment)
        assert assessment.absolute_gain == 40.0
        assert assessment.normalized_gain == pytest.approx(40.0 / 60.0)

    async def test_gain_zero_denominator(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.baseline_score = 100.0
        assessment.post_score = 100.0
        service._compute_gains(assessment)
        assert assessment.absolute_gain == 0.0
        assert assessment.normalized_gain == 0.0

    async def test_gain_no_baseline(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.post_score = 80.0
        service._compute_gains(assessment)
        assert assessment.absolute_gain is None
        assert assessment.normalized_gain is None

    async def test_gain_no_post(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.baseline_score = 40.0
        service._compute_gains(assessment)
        assert assessment.absolute_gain is None

    async def test_retention_loss(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.post_score = 80.0
        assessment.retention_score = 60.0
        service._compute_gains(assessment)
        assert assessment.retention_loss == 20.0
        assert assessment.retention_pct == pytest.approx(75.0)

    async def test_retention_no_post_score(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.retention_score = 60.0
        service._compute_gains(assessment)
        assert assessment.retention_loss is None

    async def test_status_completed_when_all_scores(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.baseline_score = 40.0
        assessment.post_score = 80.0
        service._compute_gains(assessment)
        assert assessment.status == "completed"

    async def test_status_in_progress_partial(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.baseline_score = 40.0
        service._compute_gains(assessment)
        assert assessment.status == "in_progress"


# ── P2.5: Normalized Gain Edge Cases ────────────────────────────────────


class TestNormalizedGain:
    async def test_low_baseline_high_gain(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.baseline_score = 10.0
        assessment.post_score = 90.0
        service._compute_gains(assessment)
        assert assessment.absolute_gain == 80.0
        assert assessment.normalized_gain == pytest.approx(80.0 / 90.0)

    async def test_perfect_score(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.baseline_score = 0.0
        assessment.post_score = 100.0
        service._compute_gains(assessment)
        assert assessment.absolute_gain == 100.0
        assert assessment.normalized_gain == 1.0

    async def test_negative_gain(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.baseline_score = 80.0
        assessment.post_score = 60.0
        service._compute_gains(assessment)
        assert assessment.absolute_gain == -20.0
        assert assessment.normalized_gain < 0


# ── P2.6: Retention Tests ───────────────────────────────────────────────


class TestRetention:
    async def test_retention_full_flow(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.baseline_score = 40.0
        assessment.post_score = 80.0
        assessment.retention_score = 70.0
        service._compute_gains(assessment)
        assert assessment.retention_loss == 10.0
        assert assessment.retention_pct == pytest.approx(87.5)

    async def test_retention_zero_post(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.post_score = 0.0
        assessment.retention_score = 0.0
        service._compute_gains(assessment)
        assert assessment.retention_pct == 0.0

    async def test_retention_perfect(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.post_score = 80.0
        assessment.retention_score = 80.0
        service._compute_gains(assessment)
        assert assessment.retention_loss == 0.0
        assert assessment.retention_pct == pytest.approx(100.0)


# ── P2.7: Concept-Level Analysis Tests ──────────────────────────────────


class TestConceptAnalysis:
    async def test_concept_improvements(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.baseline_concept_scores = {"math": 30.0, "science": 70.0}
        assessment.post_concept_scores = {"math": 85.0, "science": 75.0}
        report = service._format_gain(assessment)
        assert len(report["concept_improvements"]) == 2
        math_imp = next(c for c in report["concept_improvements"] if c["concept"] == "math")
        assert math_imp["improvement"] == 55.0

    async def test_weak_and_strong_concepts(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.baseline_concept_scores = {"a": 20.0, "b": 60.0, "c": 40.0}
        assessment.post_concept_scores = {"a": 90.0, "b": 45.0, "c": 85.0}
        report = service._format_gain(assessment)
        assert "a" in report["strong_concepts"]
        assert "c" in report["strong_concepts"]
        assert "b" in report["weak_concepts"]

    async def test_no_concept_scores(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        report = service._format_gain(assessment)
        assert report["concept_improvements"] == []
        assert report["weak_concepts"] == []
        assert report["strong_concepts"] == []


# ── P2.8: User Feedback Tests ───────────────────────────────────────────


class TestUserFeedback:
    async def test_submit_feedback(self, db_session):
        service = UserFeedbackService(db_session)
        fb = await service.submit(
            user_id=TEST_USER_ID,
            presentation_id=uuid.uuid4(),
            perceived_understanding=4,
            confidence=3,
            usefulness=5,
            overall_experience=4,
            qualitative_feedback="Great visual explanations!",
        )
        assert fb.public_id is not None
        assert fb.perceived_understanding == 4
        assert fb.qualitative_feedback == "Great visual explanations!"

    async def test_submit_minimal_feedback(self, db_session):
        service = UserFeedbackService(db_session)
        fb = await service.submit(
            user_id=TEST_USER_ID,
            overall_experience=3,
        )
        assert fb.public_id is not None

    async def test_list_feedback(self, db_session):
        service = UserFeedbackService(db_session)
        pres_id = uuid.uuid4()
        for i in range(3):
            await service.submit(user_id=TEST_USER_ID, presentation_id=pres_id, overall_experience=i + 1)
        feedbacks, total = await service.list_for_user(TEST_USER_ID, presentation_id=pres_id)
        assert total == 3

    async def test_summary_for_presentation(self, db_session):
        service = UserFeedbackService(db_session)
        pres_id = uuid.uuid4()
        await service.submit(user_id=TEST_USER_ID, presentation_id=pres_id, usefulness=4, confidence=3)
        await service.submit(user_id=await _ensure_user(db_session, uuid.uuid4()), presentation_id=pres_id, usefulness=2, confidence=5)
        summary = await service.summary_for_presentation(pres_id)
        assert summary["total_count"] == 2
        assert summary["avg_usefulness"] == 3.0
        assert summary["avg_confidence"] == 4.0

    async def test_empty_summary(self, db_session):
        service = UserFeedbackService(db_session)
        summary = await service.summary_for_presentation(uuid.uuid4())
        assert summary["total_count"] == 0

    async def test_user_isolation(self, db_session):
        service = UserFeedbackService(db_session)
        await service.submit(user_id=TEST_USER_ID, overall_experience=5)
        await service.submit(user_id=await _ensure_user(db_session, uuid.uuid4()), overall_experience=1)
        feedbacks, total = await service.list_for_user(TEST_USER_ID)
        assert total == 1


# ── P2.5: User Summary Tests ────────────────────────────────────────────


class TestUserSummary:
    async def test_empty_summary(self, db_session):
        service = EffectivenessService(db_session)
        summary = await service.user_summary(uuid.uuid4())
        assert summary["total_assessments"] == 0
        assert summary["avg_absolute_gain"] is None

    async def test_summary_with_data(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=presentation.id,
        )
        assessment.baseline_score = 40.0
        assessment.post_score = 80.0
        service._compute_gains(assessment)
        assessment.status = "completed"
        await db_session.flush()

        summary = await service.user_summary(TEST_USER_ID)
        assert summary["total_assessments"] == 1
        assert summary["completed_assessments"] == 1
        assert summary["avg_baseline_score"] == 40.0
        assert summary["avg_post_score"] == 80.0
        assert summary["avg_absolute_gain"] == 40.0


# ── P2.11: E2E API Tests ────────────────────────────────────────────────
# These use _create_presentation_committed() to avoid SQLite locking


class TestEffectivenessAPI:
    async def test_record_event_api(self, client: AsyncClient):
        pres = await _create_presentation_committed()
        resp = await client.post(
            "/api/v1/effectiveness/events",
            json={
                "event_type": "lesson_started",
                "resource_type": "lesson",
                "resource_id": "les_test",
                "presentation_id": str(pres.id),
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["data"]["event_type"] == "lesson_started"

    async def test_list_events_api(self, client: AsyncClient):
        pres = await _create_presentation_committed()
        await client.post(
            "/api/v1/effectiveness/events",
            json={"event_type": "lesson_started", "presentation_id": str(pres.id)},
        )
        resp = await client.get("/api/v1/effectiveness/events")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    async def test_start_baseline_api(self, client: AsyncClient):
        pres = await _create_presentation_committed()
        resp = await client.post(
            "/api/v1/effectiveness/assessments/start",
            json={
                "presentation_id": str(pres.id),
                "assessment_type": "baseline",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["assessment_type"] == "baseline"

    async def test_start_post_api(self, client: AsyncClient):
        pres = await _create_presentation_committed()
        resp = await client.post(
            "/api/v1/effectiveness/assessments/start",
            json={
                "presentation_id": str(pres.id),
                "assessment_type": "post",
            },
        )
        assert resp.status_code == 201

    async def test_start_retention_api(self, client: AsyncClient):
        pres = await _create_presentation_committed()
        resp = await client.post(
            "/api/v1/effectiveness/assessments/start",
            json={
                "presentation_id": str(pres.id),
                "assessment_type": "retention",
                "retention_delay_hours": 72,
            },
        )
        assert resp.status_code == 201

    async def test_submit_feedback_api(self, client: AsyncClient):
        pres = await _create_presentation_committed()
        resp = await client.post(
            "/api/v1/effectiveness/feedback",
            json={
                "presentation_id": str(pres.id),
                "perceived_understanding": 4,
                "confidence": 3,
                "usefulness": 5,
                "overall_experience": 4,
                "qualitative_feedback": "Excellent visuals!",
            },
        )
        assert resp.status_code == 201

    async def test_feedback_summary_api(self, client: AsyncClient):
        pres = await _create_presentation_committed()
        resp = await client.get(
            f"/api/v1/effectiveness/feedback/summary/{pres.id}",
        )
        assert resp.status_code == 200

    async def test_user_summary_api(self, client: AsyncClient):
        resp = await client.get("/api/v1/effectiveness/summary")
        assert resp.status_code == 200
        assert "total_assessments" in resp.json()["data"]

    async def test_learning_gain_not_found(self, client: AsyncClient):
        resp = await client.get(
            f"/api/v1/effectiveness/learning-gain/{uuid.uuid4()}",
        )
        assert resp.status_code == 404

    async def test_get_assessment_not_found(self, client: AsyncClient):
        resp = await client.get(
            f"/api/v1/effectiveness/assessments/{uuid.uuid4()}",
        )
        assert resp.status_code == 404

    async def test_report_not_found(self, client: AsyncClient):
        resp = await client.get(
            f"/api/v1/effectiveness/report/{uuid.uuid4()}",
        )
        assert resp.status_code == 404


# ── P2.11: Input Validation Tests ───────────────────────────────────────


class TestInputValidation:
    async def test_invalid_assessment_type_api(self, client: AsyncClient):
        pres = await _create_presentation_committed()
        resp = await client.post(
            "/api/v1/effectiveness/assessments/start",
            json={
                "presentation_id": str(pres.id),
                "assessment_type": "invalid_type",
            },
        )
        assert resp.status_code in (400, 422)

    async def test_feedback_invalid_rating(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/effectiveness/feedback",
            json={"overall_experience": 10},
        )
        assert resp.status_code == 422

    async def test_feedback_negative_rating(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/effectiveness/feedback",
            json={"overall_experience": -1},
        )
        assert resp.status_code == 422


# ── P2.9/P2.10: Experiment Group Tests ──────────────────────────────────


class TestExperimentGroup:
    async def test_experiment_group_stored(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID,
            presentation_id=presentation.id,
            experiment_group="eduvision_v2",
        )
        assert assessment.experiment_group == "eduvision_v2"

    async def test_experiment_group_api(self, client: AsyncClient):
        pres = await _create_presentation_committed()
        resp = await client.post(
            "/api/v1/effectiveness/assessments/start",
            json={
                "presentation_id": str(pres.id),
                "assessment_type": "baseline",
                "experiment_group": "control",
            },
        )
        assert resp.status_code == 201

    async def test_experiment_group_in_gain_response(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID,
            presentation_id=presentation.id,
            experiment_group="eduvision",
        )
        gain = service._format_gain(assessment)
        assert gain["experiment_group"] == "eduvision"

    async def test_experiment_group_none_when_unset(self, db_session):
        presentation = await _create_presentation(db_session)
        service = EffectivenessService(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID,
            presentation_id=presentation.id,
        )
        gain = service._format_gain(assessment)
        assert gain["experiment_group"] is None


# ── P2.10: Group Comparison Tests ───────────────────────────────────────


class TestGroupComparison:
    async def test_compare_groups_service(self, db_session):
        service = EffectivenessService(db_session)
        other_user = await _ensure_user(db_session, uuid.uuid4())

        pres_a = await _create_presentation(db_session)
        pres_b = await _create_presentation(db_session)

        assessment_a = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=pres_a.id,
            experiment_group="reference",
        )
        assessment_a.baseline_score = 40.0
        assessment_a.post_score = 70.0
        service._compute_gains(assessment_a)

        assessment_b = await service.get_or_create_assessment(
            user_id=other_user, presentation_id=pres_b.id,
            experiment_group="eduvision",
        )
        assessment_b.baseline_score = 40.0
        assessment_b.post_score = 90.0
        service._compute_gains(assessment_b)
        await db_session.flush()

        result = await service.compare_groups(
            group_a="reference", group_b="eduvision",
        )
        assert result["group_a_count"] == 1
        assert result["group_b_count"] == 1
        assert result["group_a_avg_absolute_gain"] == 30.0
        assert result["group_b_avg_absolute_gain"] == 50.0
        assert result["group_a_avg_baseline"] == 40.0
        assert result["group_b_avg_baseline"] == 40.0

    async def test_compare_groups_empty(self, db_session):
        service = EffectivenessService(db_session)
        result = await service.compare_groups(
            group_a="nonexistent_a", group_b="nonexistent_b",
        )
        assert result["group_a_count"] == 0
        assert result["group_b_count"] == 0
        assert result["group_a_avg_absolute_gain"] is None
        assert result["group_b_avg_absolute_gain"] is None

    async def test_compare_groups_multiple_users(self, db_session):
        service = EffectivenessService(db_session)

        for i in range(3):
            pres = await _create_presentation(db_session)
            user_id = await _ensure_user(db_session, uuid.uuid4())
            assessment = await service.get_or_create_assessment(
                user_id=user_id, presentation_id=pres.id,
                experiment_group="reference",
            )
            assessment.baseline_score = 30.0 + i * 10
            assessment.post_score = 60.0 + i * 10
            service._compute_gains(assessment)

        for i in range(2):
            pres = await _create_presentation(db_session)
            user_id = await _ensure_user(db_session, uuid.uuid4())
            assessment = await service.get_or_create_assessment(
                user_id=user_id, presentation_id=pres.id,
                experiment_group="eduvision",
            )
            assessment.baseline_score = 30.0 + i * 10
            assessment.post_score = 80.0 + i * 10
            service._compute_gains(assessment)
        await db_session.flush()

        result = await service.compare_groups(
            group_a="reference", group_b="eduvision",
        )
        assert result["group_a_count"] == 3
        assert result["group_b_count"] == 2
        assert result["group_a_avg_absolute_gain"] is not None
        assert result["group_b_avg_absolute_gain"] is not None

    async def test_compare_groups_isolation(self, db_session):
        service = EffectivenessService(db_session)
        pres = await _create_presentation(db_session)
        assessment = await service.get_or_create_assessment(
            user_id=TEST_USER_ID, presentation_id=pres.id,
            experiment_group="reference",
        )
        assessment.baseline_score = 50.0
        assessment.post_score = 80.0
        service._compute_gains(assessment)
        await db_session.flush()

        result_ref = await service.compare_groups(
            group_a="reference", group_b="eduvision",
        )
        assert result_ref["group_a_count"] == 1
        assert result_ref["group_b_count"] == 0

        result_rev = await service.compare_groups(
            group_a="eduvision", group_b="reference",
        )
        assert result_rev["group_a_count"] == 0
        assert result_rev["group_b_count"] == 1

    async def test_compare_groups_api(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/effectiveness/comparison",
            params={"group_a": "reference", "group_b": "eduvision"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["group_a"] == "reference"
        assert data["group_b"] == "eduvision"

    async def test_compare_groups_missing_params(self, client: AsyncClient):
        resp = await client.get("/api/v1/effectiveness/comparison")
        assert resp.status_code == 422

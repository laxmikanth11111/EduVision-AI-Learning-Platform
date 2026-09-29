"""P13 learner-analytics aggregation on real PostgreSQL.

Runs against the Alembic-migrated scratch database (postgres:16-alpine) so the
aggregation exercises the *production schema lineage* (head is ``0036_c4_topic_animation_assets``;
P13 itself adds no migration). It exercises the
``LearnerAnalyticsService`` work directly against the real engine and pins the
correct sums/avgs over ``quiz_attempts`` / ``score_summaries`` /
``learning_sessions`` + the cached educational memory — guarding against future
drift on the newly-relied-upon columns.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.models.concept import Concept
from app.models.educational_memory import EducationalMemoryRecord
from app.models.generated_lesson import GeneratedLesson
from app.models.learning_session import LearningSession
from app.models.presentation import Presentation
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_version import QuizVersion
from app.models.score_summary import ScoreSummary
from app.models.user import User
from app.services.learner_analytics_service import LearnerAnalyticsService
from tests.postgres.conftest import expected_migration_head

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def user(pg_session: AsyncSession) -> User:
    u = User(
        email=f"{uuid.uuid4().hex[:20]}@test.local",
        name="P13 PG User",
    )
    pg_session.add(u)
    await pg_session.flush()
    return u


@pytest_asyncio.fixture
async def analytics_seed(
    pg_session: AsyncSession, user: User
) -> dict[str, Any]:
    pres = Presentation(title="P13 Analytics Deck", owner_id=user.id, status="published")
    pg_session.add(pres)
    await pg_session.flush()

    lesson = GeneratedLesson(
        presentation_id=pres.id,
        user_id=user.id,
        mode="slide",
        status="ready",
        title="P13 Analytics Lesson",
        latest_version=1,
    )
    pg_session.add(lesson)
    await pg_session.flush()

    pg_session.add(
        LearningSession(
            user_id=user.id,
            lesson_id=lesson.id,
            status="completed",
            completion_percentage=100.0,
            total_time_seconds=600,
            current_slide_position=0,
            current_block_position=0,
            resume_version=0,
            last_activity_at=None,
        )
    )

    weak = Concept(
        name="Gaussian Foundations",
        topic="probability",
        presentation_id=pres.id,
        lesson_id=lesson.id,
    )
    strong = Concept(
        name="Vector Spaces",
        topic="linear-algebra",
        presentation_id=pres.id,
        lesson_id=lesson.id,
    )
    pg_session.add_all([weak, strong])
    await pg_session.flush()

    quiz = Quiz(
        presentation_id=pres.id,
        lesson_id=lesson.id,
        user_id=user.id,
        status="published",
        mode="practice",
        title="P13 PG Checkpoint",
        question_count=2,
        max_attempts_per_user=3,
        passing_score=50.0,
        show_feedback_after=True,
        latest_version=1,
        published_version=1,
    )
    pg_session.add(quiz)
    await pg_session.flush()

    version = QuizVersion(quiz_id=quiz.id, version=1, status="published", title="v1")
    pg_session.add(version)
    await pg_session.flush()

    now = datetime.now(UTC)
    percents = [40.0, 65.0, 90.0]
    attempts: list[QuizAttempt] = []
    for index, percent in enumerate(percents):
        attempt = QuizAttempt(
            quiz_id=quiz.id,
            quiz_version_id=version.id,
            user_id=user.id,
            attempt_number=index + 1,
            status="completed",
            score=percent / 100.0,
            max_score=1.0,
            percent_score=percent,
            time_spent_seconds=240 + index * 15,
            is_practice=False,
            started_at=now - timedelta(days=2 - index) - timedelta(seconds=120),
            completed_at=now - timedelta(days=2 - index),
        )
        pg_session.add(attempt)
        attempts.append(attempt)
        await pg_session.flush()
        pg_session.add(
            ScoreSummary(
                attempt_id=attempt.id,
                total_points=3,
                earned_points=(percent / 100.0) * 3.0,
                percent=percent,
                correct_count=[1, 2, 3][index],
                incorrect_count=[2, 1, 0][index],
                partially_correct_count=0,
                unanswered_count=0,
            )
        )

    memory = _build_memory_json(str(user.id), weak.public_id, strong.public_id)
    pg_session.add(EducationalMemoryRecord(user_id=user.id, memory_data=memory))
    await pg_session.commit()

    return {
        "user": user,
        "lesson_public_id": str(lesson.public_id),
        "weak_public_id": str(weak.public_id),
        "strong_public_id": str(strong.public_id),
        "attempt_ids": [str(a.public_id) for a in attempts],
    }


def _build_memory_json(user_id: str, weak_id: str, strong_id: str) -> dict[str, Any]:
    now = time.time()
    return {
        "user_id": user_id,
        "profile": {
            "user_id": user_id,
            "learning_pace": "moderate",
            "total_study_minutes": 0.0,
            "average_mastery": 62.5,
            "streak_days": 1,
        },
        "completed_courses": [],
        "completed_lessons": [],
        "completed_topics": [],
        "mastered_concepts": [strong_id],
        "developing_concepts": [],
        "weak_concepts": [weak_id],
        "concept_records": {
            weak_id: {
                "concept_id": weak_id,
                "concept_name": "Gaussian Foundations",
                "first_learned_at": now - 3600,
                "last_reviewed_at": now,
                "mastery_score": 35.0,
                "review_count": 2,
                "trend": "improving",
                "confidence_score": 0.4,
            },
            strong_id: {
                "concept_id": strong_id,
                "concept_name": "Vector Spaces",
                "first_learned_at": now - 86400,
                "last_reviewed_at": now - 100,
                "mastery_score": 90.0,
                "review_count": 6,
                "trend": "stable",
                "confidence_score": 0.9,
            },
        },
        "preferences": {
            "preferred_visualization_type": None,
            "preferred_explanation_style": "concise",
            "preferred_difficulty": "Intermediate",
            "preferred_simulation_speed": 1.0,
        },
        "revision_queue": [],
        "milestones": [],
        "created_at": now - 86400,
        "updated_at": now,
    }


async def test_p13_no_new_migration_head_unchanged(pg_session: AsyncSession) -> None:
    """P13 reads existing tables only — the Alembic head is 0034 (P16 added it)."""
    head = (
        await pg_session.execute(text("SELECT version_num FROM alembic_version"))
    ).scalar_one()
    assert head == expected_migration_head()


async def test_p13_overview_aggregates_on_migrated_schema(
    pg_session: AsyncSession, analytics_seed: dict[str, Any]
) -> None:
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = LearnerAnalyticsService(uow)
    overview = await service.get_overview(analytics_seed["user"].id)

    assert overview.attempts_taken == 3
    assert overview.avg_percent == 65.0
    assert overview.mastered_count == 1
    assert overview.developing_count == 0
    assert overview.weak_count == 1
    assert overview.session_count == 1
    assert overview.trend_percent == 37.5
    assert overview.current_focus is not None
    assert overview.current_focus.concept_public_id == analytics_seed["weak_public_id"]
    assert overview.current_focus.band == "weak"
    assert overview.current_focus.deep_link == (
        f"/frontend/player.html?lesson={analytics_seed['lesson_public_id']}"
    )


async def test_p13_trend_points_on_migrated_schema(
    pg_session: AsyncSession, analytics_seed: dict[str, Any]
) -> None:
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = LearnerAnalyticsService(uow)
    trend = await service.get_trend(analytics_seed["user"].id, None)

    assert trend.window == 30
    assert [p.percent for p in trend.points] == [40.0, 65.0, 90.0]
    assert [p.attempts for p in trend.points] == [1, 1, 1]
    assert [p.correct for p in trend.points] == [1, 2, 3]
    assert [p.incorrect for p in trend.points] == [2, 1, 0]
    assert [p.date for p in trend.points] == sorted(p.date for p in trend.points)


async def test_p13_concepts_on_migrated_schema(
    pg_session: AsyncSession, analytics_seed: dict[str, Any]
) -> None:
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = LearnerAnalyticsService(uow)
    concepts = await service.get_concepts(analytics_seed["user"].id)

    assert concepts.max == 100
    assert len(concepts.concepts) == 2
    weak, strong = concepts.concepts
    assert weak.concept_public_id == analytics_seed["weak_public_id"]
    assert weak.band == "weak"
    assert weak.trend == "up"
    assert weak.current_mastery == 35.0
    assert weak.delta_mastery == 37.5
    assert weak.deep_link_practice == (
        f"/frontend/player.html?lesson={analytics_seed['lesson_public_id']}"
    )
    assert weak.deep_link_tutor == (
        f"/frontend/tutor.html?concept={analytics_seed['weak_public_id']}"
    )
    assert strong.band == "mastered"
    assert strong.trend == "flat"


async def test_p13_effort_on_migrated_schema(
    pg_session: AsyncSession, analytics_seed: dict[str, Any]
) -> None:
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = LearnerAnalyticsService(uow)
    effort = await service.get_effort(analytics_seed["user"].id)

    assert effort.max == 100
    assert len(effort.effort) == 2
    weak = effort.effort[0]
    assert weak.concept_public_id == analytics_seed["weak_public_id"]
    assert weak.attempts == 3
    assert weak.sessions == 1
    assert weak.time_seconds == 765
    assert weak.mastery_delta == 37.5
    assert weak.efficiency == 12.5
    assert effort.effort[1].attempts == 3


async def test_p13_single_attempt_delta_is_none(
    pg_session: AsyncSession,
) -> None:
    """With one completed attempt a mastery movement cannot be backed."""
    u = User(email=f"{uuid.uuid4().hex[:20]}@test.local", name="P13 PG Single")
    pg_session.add(u)
    await pg_session.flush()
    pres = Presentation(title="Single Deck", owner_id=u.id, status="published")
    pg_session.add(pres)
    await pg_session.flush()
    lesson = GeneratedLesson(
        presentation_id=pres.id, user_id=u.id, mode="slide", status="ready", latest_version=1
    )
    pg_session.add(lesson)
    await pg_session.flush()
    concept = Concept(
        name="Solo Concept", topic="solo", presentation_id=pres.id, lesson_id=lesson.id
    )
    pg_session.add(concept)
    await pg_session.flush()
    quiz = Quiz(
        presentation_id=pres.id,
        lesson_id=lesson.id,
        user_id=u.id,
        status="published",
        mode="practice",
        question_count=1,
        max_attempts_per_user=1,
        passing_score=50.0,
        show_feedback_after=True,
        latest_version=1,
        published_version=1,
    )
    pg_session.add(quiz)
    await pg_session.flush()
    version = QuizVersion(quiz_id=quiz.id, version=1, status="published", title="v1")
    pg_session.add(version)
    await pg_session.flush()
    pg_session.add(
        QuizAttempt(
            quiz_id=quiz.id,
            quiz_version_id=version.id,
            user_id=u.id,
            attempt_number=1,
            status="completed",
            score=0.6,
            max_score=1.0,
            percent_score=60.0,
            time_spent_seconds=120,
            is_practice=False,
            started_at=datetime.now(UTC) - timedelta(seconds=120),
            completed_at=datetime.now(UTC),
        )
    )
    pg_session.add(
        EducationalMemoryRecord(
            user_id=u.id,
            memory_data={
                "user_id": str(u.id),
                "profile": {
                    "user_id": str(u.id),
                    "learning_pace": "moderate",
                    "total_study_minutes": 0.0,
                    "average_mastery": 60.0,
                    "streak_days": 1,
                },
                "mastered_concepts": [],
                "developing_concepts": [],
                "weak_concepts": [],
                "concept_records": {
                    str(concept.public_id): {
                        "concept_id": str(concept.public_id),
                        "concept_name": "Solo Concept",
                        "first_learned_at": 0.0,
                        "last_reviewed_at": 0.0,
                        "mastery_score": 60.0,
                        "review_count": 1,
                        "trend": "stable",
                        "confidence_score": 0.5,
                    }
                },
                "preferences": {},
                "revision_queue": [],
                "milestones": [],
                "created_at": 0.0,
                "updated_at": 0.0,
            },
        )
    )
    await pg_session.commit()

    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = LearnerAnalyticsService(uow)
    effort = await service.get_effort(u.id)

    assert len(effort.effort) == 1
    assert effort.effort[0].attempts == 1
    assert effort.effort[0].mastery_delta is None
    assert effort.effort[0].efficiency is None

    concepts = await service.get_concepts(u.id)
    assert concepts.concepts[0].band == "developing"
    assert concepts.concepts[0].delta_mastery is None

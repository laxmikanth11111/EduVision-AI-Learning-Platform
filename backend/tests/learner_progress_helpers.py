"""Shared seed helpers for the learner-progress dashboard tests.

These helpers are not collected as tests (no ``test_`` prefix). They seed a
complete, deterministic learner profile directly into the test database:

  * a presentation + generated lesson with a COMPLETED learning session
  * a published quiz linked to the lesson
  * one COMPLETED quiz attempt with a fixed percent score
  * an ``EducationalMemoryRecord`` JSON blob with one weak + one mastered
    concept (so mastery, weak/strong lists and recommendations are populated)

Every seeded entity is scoped to a caller-supplied user UUID, so each test can
use a unique user and never observe another user's data.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def build_memory_json(user_id: str) -> dict[str, Any]:
    """Build an ``EducationalMemory`` JSON blob matching the Pydantic schema."""
    now = time.time()
    weak_id = "concept_gauss"
    mastered_id = "concept_vector"
    return {
        "user_id": user_id,
        "profile": {
            "user_id": user_id,
            "learning_pace": "moderate",
            "total_study_minutes": 45.0,
            "average_mastery": 62.5,
            "streak_days": 2,
        },
        "completed_courses": [],
        "completed_lessons": [],
        "completed_topics": [],
        "mastered_concepts": [mastered_id],
        "developing_concepts": [],
        "weak_concepts": [weak_id],
        "concept_records": {
            weak_id: {
                "concept_id": weak_id,
                "concept_name": "Gaussian Distributions",
                "first_learned_at": now - 3600,
                "last_reviewed_at": now,
                "mastery_score": 30.0,
                "review_count": 1,
                "trend": "improving",
                "confidence_score": 0.4,
            },
            mastered_id: {
                "concept_id": mastered_id,
                "concept_name": "Vector Spaces",
                "first_learned_at": now - 86400,
                "last_reviewed_at": now - 100,
                "mastery_score": 95.0,
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


async def seed_learner(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    email: str,
    attempt_percent: float = 85.0,
    lesson_status: str = "completed",
    memory: bool = True,
) -> dict[str, Any]:
    """Create a user + full learner profile. Returns lookups keyed by public id.

    Commits the transaction so the ASGI client (a different session over the
    same SQLite file) can observe the rows.
    """
    from app.core.security import hash_password
    from app.models.educational_memory import EducationalMemoryRecord
    from app.models.generated_lesson import GeneratedLesson
    from app.models.learning_session import LearningSession
    from app.models.presentation import Presentation
    from app.models.quiz import Quiz
    from app.models.quiz_attempt import QuizAttempt
    from app.models.quiz_version import QuizVersion
    from app.models.user import User

    existing = await session.execute(select(User).where(User.id == user_id))
    if existing.scalar_one_or_none() is None:
        session.add(
            User(
                id=user_id,
                email=email,
                name="Progress Learner",
                password_hash=hash_password("testpassword123"),
            )
        )

    pres = Presentation(
        title="Progress Deck",
        owner_id=user_id,
        status="published",
        slide_count=2,
    )
    session.add(pres)
    await session.flush()

    lesson = GeneratedLesson(
        presentation_id=pres.id,
        user_id=user_id,
        mode="slide",
        status="ready",
        title="Progress Lesson",
        latest_version=1,
    )
    session.add(lesson)
    await session.flush()

    lsession = LearningSession(
        user_id=user_id,
        lesson_id=lesson.id,
        status=lesson_status,
        completion_percentage=100.0 if lesson_status == "completed" else 40.0,
        total_time_seconds=600,
        current_slide_position=0,
        current_block_position=0,
        resume_version=0,
        last_activity_at=None,
    )
    session.add(lsession)
    await session.flush()

    quiz = Quiz(
        presentation_id=pres.id,
        lesson_id=lesson.id,
        user_id=user_id,
        status="published",
        mode="practice",
        title="Progress Checkpoint",
        question_count=2,
        max_attempts_per_user=3,
        passing_score=50.0,
        show_feedback_after=True,
        latest_version=1,
        published_version=1,
    )
    session.add(quiz)
    await session.flush()

    version = QuizVersion(quiz_id=quiz.id, version=1, status="published", title="v1")
    session.add(version)
    await session.flush()

    attempt = QuizAttempt(
        quiz_id=quiz.id,
        quiz_version_id=version.id,
        user_id=user_id,
        attempt_number=1,
        status="completed",
        score=0.85,
        max_score=1.0,
        percent_score=attempt_percent,
        time_spent_seconds=300,
        is_practice=False,
        started_at=None,
        completed_at=None,
    )
    session.add(attempt)
    await session.flush()

    if memory:
        existing_mem = await session.execute(
            select(EducationalMemoryRecord).where(
                EducationalMemoryRecord.user_id == user_id
            )
        )
        if existing_mem.scalar_one_or_none() is None:
            session.add(
                EducationalMemoryRecord(
                    user_id=user_id,
                    memory_data=build_memory_json(str(user_id)),
                )
            )

    await session.commit()

    return {
        "user_id": str(user_id),
        "presentation_id": pres.public_id,
        "lesson_id": lesson.public_id,
        "quiz_id": quiz.public_id,
        "attempt_id": attempt.public_id,
    }


async def seed_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    email: str,
) -> None:
    """Create ONLY a user row with no lesson/session/attempt/memory activity.

    Used for empty-state and cross-user isolation scenarios where the learner
    must be genuinely inactive.
    """
    from app.core.security import hash_password
    from app.models.user import User

    existing = await session.execute(select(User).where(User.id == user_id))
    if existing.scalar_one_or_none() is None:
        session.add(
            User(
                id=user_id,
                email=email,
                name="Progress Learner",
                password_hash=hash_password("testpassword123"),
            )
        )
        await session.commit()

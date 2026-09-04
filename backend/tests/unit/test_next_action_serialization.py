"""P10 C3 -- next-action assembly unit tests (NG-1 + NG-3).

The scope doc's C3 objective is "next-action assembly".
* NG-1: ``LearningRecommendation.next_action`` (computed_field) must return the
  single best action (``actions[0]``) AND serialize through ``model_dump()`` so
  the quiz-result UI can read ``recs.next_action``.
* NG-3: ``MasteryTutorService._remediate_next_action`` must produce a structured
  ``take_knowledge_check`` action (with the lesson deep-link) that closes the
  remediate -> re-practice loop and round-trips into ``TutorRemediateResponse``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.schemas.next_action import (
    ActionType,
    ActivityType,
    LearningRecommendation,
    NextAction,
    Priority,
)
from app.schemas.tutor import TutorRemediateResponse
from app.services.mastery_tutor_service import MasteryTutorService
from tests.learner_progress_helpers import seed_user


def _action(title: str) -> NextAction:
    return NextAction(
        action_type=ActionType.SIMPLIFY_EXPLANATION,
        concept_id="concept_x",
        concept_name="X",
        reason="low retention",
        activity_type=ActivityType.EXPLANATION,
        priority=Priority.HIGH,
        title=title,
        description="Re-learn this concept.",
    )


def test_next_action_returns_highest_priority_action() -> None:
    first = _action("first")
    second = _action("second")
    rec = LearningRecommendation(
        user_id="u1",
        actions=[first, second],
    )
    # actions are priority-sorted; next_action is actions[0].
    assert rec.next_action is not None
    assert rec.next_action.title == "first"


def test_next_action_serializes_in_model_dump() -> None:
    """NG-1: the UI reads ``recommendations.next_action`` from the payload."""
    rec = LearningRecommendation(
        user_id="u1",
        actions=[_action("only")],
    )
    dumped = rec.model_dump()
    assert "next_action" in dumped
    assert dumped["next_action"] is not None
    assert dumped["next_action"]["title"] == "only"
    assert dumped["next_action"]["action_type"] == "simplify_explanation"


def test_next_action_none_when_no_actions() -> None:
    rec = LearningRecommendation(user_id="u1", actions=[])
    assert rec.next_action is None
    assert rec.model_dump()["next_action"] is None


async def _seed_concept_and_lesson(
    db_session: AsyncSession, uid: uuid.UUID
) -> tuple[object, str]:
    """Seed a user + presentation + lesson + concept; returns (concept, lesson_public_id)."""
    from app.models.concept import Concept
    from app.models.generated_lesson import GeneratedLesson
    from app.models.presentation import Presentation

    pres = Presentation(title="Tutor Remediation Deck", owner_id=uid, status="published")
    db_session.add(pres)
    await db_session.flush()

    lesson = GeneratedLesson(
        presentation_id=pres.id,
        user_id=uid,
        mode="slide",
        status="ready",
        title="Remediation Lesson",
        latest_version=1,
    )
    db_session.add(lesson)
    await db_session.flush()

    concept = Concept(
        public_id=f"concept_{uuid.uuid4().hex[:10]}",
        presentation_id=pres.id,
        lesson_id=lesson.id,
        name="Gaussian Distributions",
        difficulty_level="intermediate",
    )
    db_session.add(concept)
    await db_session.commit()
    return concept, lesson.public_id


@pytest.mark.asyncio
async def test_remediate_next_action_closes_loop(db_session: AsyncSession) -> None:
    """NG-3: remediation yields a re-practice (knowledge check) action."""
    uid = uuid.uuid4()
    await seed_user(db_session, uid, email="c3_remediate@example.com")
    concept, lesson_public_id = await _seed_concept_and_lesson(db_session, uid)

    service = MasteryTutorService(UnitOfWork(session=db_session))
    action_dict = service._remediate_next_action(  # noqa: SLF001
        concept, lesson_public_id=lesson_public_id
    )
    assert action_dict is not None
    assert action_dict["action_type"] == "take_knowledge_check"
    assert action_dict["activity_type"] == "quiz"
    assert action_dict["priority"] == "high"
    assert action_dict["concept_id"] == concept.public_id
    # The metadata carries the deep-link lesson id for the "Practice this" CTA.
    assert action_dict["metadata"]["lesson_id"] == lesson_public_id

    # It must round-trip into the remediation response schema (NG-3 wire).
    resp = TutorRemediateResponse(
        target_concept_id=concept.public_id,
        target_concept_name=concept.name,
        source_kind="deterministic",
        response="Review this concept.",
        next_action=action_dict,
    )
    assert resp.next_action is not None
    assert resp.next_action.action_type == ActionType.TAKE_KNOWLEDGE_CHECK
    assert resp.next_action.metadata["lesson_id"] == lesson_public_id

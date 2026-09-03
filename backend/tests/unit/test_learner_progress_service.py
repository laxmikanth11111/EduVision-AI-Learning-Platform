"""P7 learner-progress service unit tests.

Exercise ``LearnerProgressService`` directly against the seeded test database,
verifying deterministic behaviour without HTTP: empty state, lesson
aggregation, mastery classification, recommendations, attempt history, trend,
limits and deterministic output.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.unit_of_work import UnitOfWork
from app.services.educational_memory_service import educational_memory_service
from app.services.learner_progress_service import LearnerProgressService
from tests.learner_progress_helpers import seed_learner, seed_user


@pytest.fixture(autouse=True)
def _reset_memory_cache() -> None:
    educational_memory_service._memories.clear()  # noqa: SLF001
    return


async def _progress_for(session: AsyncSession, uid: uuid.UUID):
    service = LearnerProgressService(UnitOfWork(session=session))
    return await service.get_progress(uid)


@pytest.mark.asyncio
async def test_empty_learner_state(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await seed_user(db_session, uid, email="svc_empty@example.com")
    data = await _progress_for(db_session, uid)
    assert data.summary.lessons_completed == 0
    assert data.summary.lessons_in_progress == 0
    assert data.summary.average_mastery == 0.0
    assert data.summary.mastered_concepts == 0
    assert data.summary.weak_concepts == 0
    assert data.summary.attempts_total == 0
    assert data.lesson_progress == []
    assert data.recent_attempts == []
    assert data.trend == []
    assert data.recommendations == []
    assert data.concept_mastery == []


@pytest.mark.asyncio
async def test_completed_lesson_and_mastery_aggregation(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await seed_learner(db_session, uid, email="svc_full@example.com")
    data = await _progress_for(db_session, uid)
    assert data.summary.lessons_completed == 1
    assert data.summary.lessons_in_progress == 0
    assert data.summary.mastered_concepts == 1
    assert data.summary.weak_concepts == 1
    assert data.summary.developing_concepts == 0
    assert data.summary.average_mastery == 62.5
    assert data.summary.attempts_total == 1

    assert len(data.lesson_progress) == 1
    lp = data.lesson_progress[0]
    assert lp.status == "completed"
    assert lp.completion_percentage == 100.0
    assert lp.title == "Progress Lesson"


@pytest.mark.asyncio
async def test_weak_developing_mastered_classification(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await seed_learner(db_session, uid, email="svc_class@example.com")
    data = await _progress_for(db_session, uid)
    statuses = {c.status for c in data.concept_mastery}
    assert "weak" in statuses
    assert "mastered" in statuses
    assert "developing" not in statuses
    weak = [c for c in data.concept_mastery if c.status == "weak"]
    mastered = [c for c in data.concept_mastery if c.status == "mastered"]
    assert weak[0].concept_name == "Gaussian Distributions"
    assert weak[0].mastery_score == 30.0
    assert mastered[0].concept_name == "Vector Spaces"
    assert mastered[0].mastery_score == 95.0


@pytest.mark.asyncio
async def test_deterministic_recommendations(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await seed_learner(db_session, uid, email="svc_rec@example.com")
    data = await _progress_for(db_session, uid)
    assert data.recommendations_summary
    assert data.recommendations
    # Weak mastery (<50) yields a high-priority simplification/visual action.
    actions = {r.action_type for r in data.recommendations}
    assert actions & {"simplify_explanation", "show_visual"}
    # Output is deterministic: two identical calls produce identical actions.
    again = await _progress_for(db_session, uid)
    assert [a.action_type for a in data.recommendations] == [
        a.action_type for a in again.recommendations
    ]


@pytest.mark.asyncio
async def test_attempt_history_and_trend(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await seed_learner(db_session, uid, email="svc_att@example.com", attempt_percent=85.0)
    data = await _progress_for(db_session, uid)
    assert len(data.recent_attempts) == 1
    assert data.recent_attempts[0].percent_score == 85.0
    assert data.recent_attempts[0].passed is True
    assert len(data.trend) == 1
    assert data.trend[0].value == 85.0
    assert data.trend[0].source == "quiz_attempt"


@pytest.mark.asyncio
async def test_limits_are_bounded(db_session: AsyncSession) -> None:
    uid = uuid.uuid4()
    await seed_learner(db_session, uid, email="svc_limits@example.com")
    data = await _progress_for(db_session, uid)
    # With default seed, lists are small; the assertion documents boundedness
    # invariants (no unbounded result sets).
    assert len(data.lesson_progress) <= 50
    assert len(data.concept_mastery) <= 100
    assert len(data.recommendations) <= 5
    assert len(data.trend) <= 10


@pytest.mark.asyncio
async def test_learner_scoped_never_leaks(db_session: AsyncSession) -> None:
    uid_a = uuid.uuid4()
    uid_b = uuid.uuid4()
    await seed_learner(db_session, uid_a, email="svc_a@example.com")
    await seed_user(db_session, uid_b, email="svc_b@example.com")
    data_b = await _progress_for(db_session, uid_b)
    assert data_b.summary.attempts_total == 0
    assert data_b.summary.lessons_completed == 0
    assert data_b.recent_attempts == []
    assert data_b.weak_concepts == []
    assert data_b.strong_concepts == []

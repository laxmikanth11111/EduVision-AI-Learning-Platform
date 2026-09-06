"""P14 review-outcome retention on real PostgreSQL.

Runs against the Alembic-migrated scratch database (postgres:16-alpine) so the
retention path exercises the *production schema lineage* (head is ``0034_video_projects``;
P14 itself adds no migration). It drives the
``ReviewScheduleService`` / ``LearnerAnalyticsService`` work directly against the
real engine: JSONB ``review_metadata`` round-trips (v2 history + counts + step),
the outcome->interval ladder stays deterministic, cross-user completion 404-
equalizes, and the retention surface aggregates over the migrated schema.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database.unit_of_work import UnitOfWork
from app.models.concept import Concept
from app.models.educational_memory import EducationalMemoryRecord
from app.models.generated_lesson import GeneratedLesson
from app.models.presentation import Presentation
from app.models.review_schedule import ReviewSchedule
from app.models.user import User
from app.services.learner_analytics_service import LearnerAnalyticsService
from app.services.review_schedule_service import ReviewScheduleService
from app.services.review_scheduler import interval_at_step

pytestmark = pytest.mark.postgres

_DAY = 86400.0


def _memory_blob(user_id: str, records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    now = time.time()
    all_ids = list(records)
    return {
        "user_id": user_id,
        "profile": {
            "user_id": user_id,
            "learning_pace": "moderate",
            "total_study_minutes": 0.0,
            "average_mastery": 55.0,
            "streak_days": 1,
        },
        "completed_courses": [],
        "completed_lessons": [],
        "completed_topics": [],
        "mastered_concepts": [
            cid for cid in all_ids if float(records[cid]["mastery_score"]) >= 85.0
        ],
        "developing_concepts": [
            cid for cid in all_ids if 50.0 <= float(records[cid]["mastery_score"]) < 85.0
        ],
        "weak_concepts": [cid for cid in all_ids if float(records[cid]["mastery_score"]) < 50.0],
        "concept_records": records,
        "preferences": {},
        "revision_queue": [],
        "milestones": [],
        "created_at": now - 86400,
        "updated_at": now,
    }


def _concept_record(
    name: str,
    mastery: float,
    review_count: int,
    *,
    first_learned_at: float,
    last_reviewed_at: float,
) -> dict[str, Any]:
    return {
        "concept_id": name,
        "concept_name": name,
        "first_learned_at": first_learned_at,
        "last_reviewed_at": last_reviewed_at,
        "mastery_score": mastery,
        "review_count": review_count,
        "trend": "stable",
        "confidence_score": max(0.1, min(0.9, mastery / 100.0)),
    }


@pytest_asyncio.fixture
async def review_seed(pg_session: AsyncSession) -> dict[str, Any]:
    """A learner with one weak concept + one step-0 schedule + memory blob."""
    user = User(
        email=f"{uuid.uuid4().hex[:20]}@test.local",
        name="P14 PG Reviewer",
    )
    pg_session.add(user)
    await pg_session.flush()

    pres = Presentation(title="P14 Review Deck", owner_id=user.id, status="published")
    pg_session.add(pres)
    await pg_session.flush()

    lesson = GeneratedLesson(
        presentation_id=pres.id,
        user_id=user.id,
        mode="slide",
        status="ready",
        title="P14 Review Lesson",
        latest_version=1,
    )
    pg_session.add(lesson)
    await pg_session.flush()

    concept = Concept(
        name="Quadratic Roots",
        topic="algebra",
        presentation_id=pres.id,
        lesson_id=lesson.id,
    )
    pg_session.add(concept)
    await pg_session.flush()

    now = time.time()
    memory = _memory_blob(
        str(user.id),
        {
            str(concept.public_id): _concept_record(
                "Quadratic Roots",
                40.0,
                2,
                first_learned_at=now - 10 * _DAY,
                last_reviewed_at=now - 2 * _DAY,
            )
        },
    )
    pg_session.add(EducationalMemoryRecord(user_id=user.id, memory_data=memory))

    schedule = ReviewSchedule(
        user_id=user.id,
        concept_id=concept.id,
        lesson_id=lesson.id,
        topic="Quadratic Roots",
        status="scheduled",
        scheduled_date=date.today(),
        interval_days=1,
        mastery_at_schedule=40.0,
        due_at=datetime.now(UTC),
        review_metadata={"step": 0},
    )
    pg_session.add(schedule)
    await pg_session.commit()
    await pg_session.refresh(schedule)

    return {
        "user": user,
        "schedule": schedule,
        "concept_public_id": str(concept.public_id),
        "lesson_public_id": str(lesson.public_id),
    }


async def test_p14_no_new_migration_head_unchanged(pg_session: AsyncSession) -> None:
    """P14 reads existing tables only — the Alembic head is 0034 (P16 added it)."""
    head = (await pg_session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    assert head == "0034_video_projects"


async def test_p14_complete_good_persists_jsonb_on_migrated_schema(
    pg_session: AsyncSession, review_seed: dict[str, Any]
) -> None:
    """A ``good`` completion writes v2 metadata into the JSONB column and moves
    the ladder 0 -> 1 (3 days) without touching the mastery scalar."""
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = ReviewScheduleService(uow)
    now = datetime.now(UTC)

    resp = await service.complete(
        review_seed["user"].id,
        review_seed["schedule"].public_id,
        outcome="good",
        now=now,
    )

    assert resp.outcome == "good"
    assert resp.next_interval_days == interval_at_step(1) == 3
    assert resp.mastery_score == 40.0
    assert resp.retained_strength == 85.0
    assert resp.review_accuracy == 100.0

    # JSONB round-trip after expiry: the DB-reloaded metadata is a plain dict.
    row = (
        await pg_session.execute(
            select(ReviewSchedule)
            .where(ReviewSchedule.id == review_seed["schedule"].id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    md = row.review_metadata
    assert md["v"] == 2
    assert md["step"] == 1
    assert md["counts"] == {"again": 0, "hard": 0, "good": 1, "easy": 0}
    assert [entry["outcome"] for entry in md["history"]] == ["good"]
    assert row.interval_days == 3
    assert row.last_reviewed_at is not None
    assert row.completed_at is not None
    assert abs((row.due_at - now).total_seconds() / 86400.0 - 3.0) < 0.01


async def test_p14_spacing_ladder_deterministic_on_pg(
    pg_session: AsyncSession, review_seed: dict[str, Any]
) -> None:
    """The full outcome -> interval ladder on PG: easy skip-ahead, good +1,
    again lapse to zero, hard hold, and the step-3 cap."""
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = ReviewScheduleService(uow)
    uid = review_seed["user"].id
    schedule_pub = review_seed["schedule"].public_id
    base = datetime.now(UTC)

    def run_then(offset_days: float) -> datetime:
        return base + timedelta(days=offset_days)

    async def complete_at(outcome: str, offset_days: float) -> Any:
        return await service.complete(uid, schedule_pub, outcome=outcome, now=run_then(offset_days))

    r1 = await complete_at("easy", 0.0)  # step 0 -> 2
    assert r1.next_interval_days == 7
    r2 = await complete_at("good", 1.0)  # step 2 -> 3
    assert r2.next_interval_days == 14
    r3 = await complete_at("again", 8.0)  # step 3 -> 0 (lapse)
    assert r3.next_interval_days == 1
    r4 = await complete_at("easy", 9.0)  # step 0 -> 2
    assert r4.next_interval_days == 7
    r5 = await complete_at("easy", 16.0)  # step 2 -> 3 (cap, not 21)
    assert r5.next_interval_days == 14
    r6 = await complete_at("hard", 30.0)  # step 3 -> 3 (hold)
    assert r6.next_interval_days == 14

    row = (
        await pg_session.execute(
            select(ReviewSchedule)
            .where(ReviewSchedule.id == review_seed["schedule"].id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    md = row.review_metadata
    assert md["step"] == 3
    assert md["counts"] == {"again": 1, "hard": 1, "good": 1, "easy": 3}
    assert [entry["outcome"] for entry in md["history"]] == [
        "easy",
        "good",
        "again",
        "easy",
        "easy",
        "hard",
    ]


async def test_p14_cross_user_complete_404_and_bad_outcome_on_pg(
    pg_session: AsyncSession, review_seed: dict[str, Any]
) -> None:
    uow = UnitOfWork(pg_session, retry_on_transient=False)
    service = ReviewScheduleService(uow)

    other = User(
        email=f"{uuid.uuid4().hex[:20]}@test.local",
        name="P14 Other Learner",
    )
    pg_session.add(other)
    await pg_session.flush()

    with pytest.raises(NotFoundError):
        await service.complete(other.id, review_seed["schedule"].public_id, outcome="good")

    with pytest.raises(ValueError, match="invalid review outcome"):
        await service.complete(
            review_seed["user"].id,
            review_seed["schedule"].public_id,
            outcome="gonzo",
        )


async def test_p14_retention_aggregation_on_migrated_schema(
    pg_session: AsyncSession,
) -> None:
    """GET /me/analytics/retention composition over migrated rows: an overdue
    weak concept, an on-track developing concept, and a never-scheduled
    mastered concept sort overdue -> on_track -> new with an honest average."""
    user = User(
        email=f"{uuid.uuid4().hex[:20]}@test.local",
        name="P14 PG Aggregation",
    )
    pg_session.add(user)
    await pg_session.flush()

    pres = Presentation(title="P14 Retention Deck", owner_id=user.id, status="published")
    pg_session.add(pres)
    await pg_session.flush()

    lesson = GeneratedLesson(
        presentation_id=pres.id,
        user_id=user.id,
        mode="slide",
        status="ready",
        title="P14 Retention Lesson",
        latest_version=1,
    )
    pg_session.add(lesson)
    await pg_session.flush()

    names = ["Logarithms", "Matrices", "Trigonometry"]
    concepts: dict[str, Concept] = {}
    for name in names:
        concept = Concept(
            name=name,
            topic="math",
            presentation_id=pres.id,
            lesson_id=lesson.id,
        )
        pg_session.add(concept)
        concepts[name] = concept
    await pg_session.flush()

    now_epoch = time.time()
    records: dict[str, dict[str, Any]] = {}
    for name in names:
        records[str(concepts[name].public_id)] = _concept_record(
            name,
            40.0,
            2,
            first_learned_at=now_epoch - 10 * _DAY,
            last_reviewed_at=now_epoch - 5 * _DAY,
        )
    records[str(concepts["Matrices"].public_id)] = _concept_record(
        "Matrices",
        60.0,
        3,
        first_learned_at=now_epoch - 20 * _DAY,
        last_reviewed_at=now_epoch - 1 * _DAY,
    )
    records[str(concepts["Trigonometry"].public_id)] = _concept_record(
        "Trigonometry",
        90.0,
        6,
        first_learned_at=now_epoch - 30 * _DAY,
        last_reviewed_at=now_epoch - 1 * _DAY,
    )
    pg_session.add(
        EducationalMemoryRecord(user_id=user.id, memory_data=_memory_blob(str(user.id), records))
    )

    now = datetime.now(UTC)

    def schedule_for(label: str, *, due_at: datetime) -> None:
        concept = concepts[label]
        pg_session.add(
            ReviewSchedule(
                user_id=user.id,
                concept_id=concept.id,
                lesson_id=lesson.id,
                topic=label,
                status="scheduled",
                scheduled_date=date.today(),
                interval_days=3,
                mastery_at_schedule=float(records[str(concept.public_id)]["mastery_score"]),
                due_at=due_at,
                last_reviewed_at=now - timedelta(days=1),
                review_metadata={
                    "step": 1,
                    "v": 2,
                    "counts": {"again": 0, "hard": 0, "good": 1, "easy": 0},
                    "history": [
                        {
                            "outcome": "good",
                            "at": (now - timedelta(days=1)).isoformat(),
                        }
                    ],
                },
            )
        )

    schedule_for("Logarithms", due_at=now - timedelta(days=1))  # overdue
    schedule_for("Matrices", due_at=now + timedelta(days=3))  # on track
    # Trigonometry intentionally has no schedule -> status "new".
    await pg_session.commit()

    uow = UnitOfWork(pg_session, retry_on_transient=False)
    retention = await LearnerAnalyticsService(uow).get_retention(user.id)

    assert retention.max == 100
    assert [c.concept_public_id for c in retention.concepts] == [
        str(concepts["Logarithms"].public_id),
        str(concepts["Matrices"].public_id),
        str(concepts["Trigonometry"].public_id),
    ]

    overdue, on_track, never = retention.concepts
    assert overdue.status == "overdue"
    assert overdue.band == "weak"
    assert overdue.mastery_score == 40.0
    assert overdue.retained_strength == round(85.0 * (1 - 5 / 30), 1)  # 70.8
    assert overdue.review_accuracy == 100.0
    assert overdue.review_count == 2
    assert overdue.deep_link_practice == (f"/frontend/player.html?lesson={lesson.public_id}")
    assert overdue.deep_link_tutor == (f"/frontend/tutor.html?concept={overdue.concept_public_id}")
    assert overdue.days_since_review == pytest.approx(5.0, abs=0.01)

    assert on_track.status == "on_track"
    assert on_track.band == "developing"
    assert on_track.retained_strength == round(85.0 * (1 - 1 / 30), 1)  # 82.2

    assert never.status == "new"
    assert never.band == "mastered"
    assert never.retained_strength is None
    assert never.review_accuracy is None
    assert never.due_at is None

    summary = retention.summary
    assert summary.on_track_count == 1
    assert summary.at_risk_count == 0
    assert summary.overdue_count == 1
    assert summary.new_count == 1
    assert summary.retention_average == round((70.8 + 82.2) / 2, 1)  # 76.5

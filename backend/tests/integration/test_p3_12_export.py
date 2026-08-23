"""P3.12 Integration tests for real analytics CSV export.

Proves: REAL DB → REAL query → REAL service → REAL CSV → REAL API response.
"""

from __future__ import annotations

import csv
import hashlib
import io
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.effectiveness_assessment import EffectivenessAssessment
from app.models.user_feedback import UserFeedback
from app.services.effectiveness_service import EffectivenessService

pytestmark = pytest.mark.asyncio

TEST_USER = uuid.UUID("aaaa0001-0000-0000-0000-000000000001")
OTHER_USER = uuid.UUID("aaaa9999-9999-9999-9999-999999999999")


async def _create_assessment(
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID,
    presentation_id: uuid.UUID,
    experiment_group: str | None = None,
    baseline_score: float | None = None,
    post_score: float | None = None,
    retention_score: float | None = None,
    total_learning_time_seconds: int | None = None,
    status: str = "in_progress",
) -> EffectivenessAssessment:
    assessment = EffectivenessAssessment(
        user_id=user_id,
        presentation_id=presentation_id,
        experiment_group=experiment_group,
        baseline_score=baseline_score,
        post_score=post_score,
        retention_score=retention_score,
        total_learning_time_seconds=total_learning_time_seconds,
        status=status,
    )
    if baseline_score is not None and post_score is not None:
        assessment.absolute_gain = post_score - baseline_score
        denom = 100.0 - baseline_score
        assessment.normalized_gain = assessment.absolute_gain / denom if denom > 0 else 0.0
    if post_score is not None and retention_score is not None:
        assessment.retention_loss = post_score - retention_score
        assessment.retention_pct = (retention_score / post_score * 100.0) if post_score > 0 else 0.0
    if status == "completed":
        from datetime import UTC, datetime
        assessment.completed_at = datetime.now(UTC)

    db_session.add(assessment)
    await db_session.flush()
    await db_session.refresh(assessment)
    return assessment


async def _create_feedback(
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID,
    assessment_id: uuid.UUID,
    perceived_understanding: int | None = None,
    confidence: int | None = None,
    usefulness: int | None = None,
    qualitative_feedback: str | None = None,
) -> UserFeedback:
    fb = UserFeedback(
        user_id=user_id,
        assessment_id=assessment_id,
        perceived_understanding=perceived_understanding,
        confidence=confidence,
        usefulness=usefulness,
        qualitative_feedback=qualitative_feedback,
    )
    db_session.add(fb)
    await db_session.flush()
    await db_session.refresh(fb)
    return fb


def _parse_csv(content: str) -> list[dict[str, str]]:
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


class TestExportServiceMethod:
    async def test_returns_real_db_data(self, db_session: AsyncSession):
        pres_id = uuid.uuid4()
        await _create_assessment(
            db_session,
            user_id=TEST_USER,
            presentation_id=pres_id,
            experiment_group="export_ref",
            baseline_score=40.0,
            post_score=80.0,
            total_learning_time_seconds=300,
            status="completed",
        )

        service = EffectivenessService(db_session)
        rows = await service.export_study_data(user_id=TEST_USER)

        assert len(rows) == 1
        row = rows[0]
        assert row["participant_id"] == hashlib.sha256(str(TEST_USER).encode()).hexdigest()[:16]
        assert row["experiment_group"] == "export_ref"
        assert row["baseline_score"] == 40.0
        assert row["post_score"] == 80.0
        assert row["absolute_gain"] == 40.0
        assert row["normalized_gain"] == pytest.approx(40.0 / 60.0)
        assert row["learning_time_seconds"] == 300
        assert row["status"] == "completed"
        assert row["retention_score"] == ""
        assert row["retention_loss"] == ""
        assert row["completed_at"] != ""

    async def test_returns_multiple_assessments(self, db_session: AsyncSession):
        for i in range(3):
            await _create_assessment(
                db_session,
                user_id=TEST_USER,
                presentation_id=uuid.uuid4(),
                baseline_score=float(i * 10),
                post_score=float(i * 10 + 20),
                status="completed",
            )

        service = EffectivenessService(db_session)
        rows = await service.export_study_data(user_id=TEST_USER)
        assert len(rows) == 3

    async def test_filters_by_experiment_group(self, db_session: AsyncSession):
        await _create_assessment(
            db_session, user_id=TEST_USER, presentation_id=uuid.uuid4(),
            experiment_group="export_ref_a", baseline_score=50.0, post_score=70.0,
        )
        await _create_assessment(
            db_session, user_id=TEST_USER, presentation_id=uuid.uuid4(),
            experiment_group="export_edu_a", baseline_score=30.0, post_score=90.0,
        )

        service = EffectivenessService(db_session)
        ref_rows = await service.export_study_data(
            user_id=TEST_USER, experiment_group="export_ref_a",
        )
        assert len(ref_rows) == 1
        assert ref_rows[0]["experiment_group"] == "export_ref_a"

        edu_rows = await service.export_study_data(
            user_id=TEST_USER, experiment_group="export_edu_a",
        )
        assert len(edu_rows) == 1
        assert edu_rows[0]["experiment_group"] == "export_edu_a"

    async def test_empty_dataset_returns_empty_list(self, db_session: AsyncSession):
        service = EffectivenessService(db_session)
        rows = await service.export_study_data(user_id=uuid.uuid4())
        assert rows == []

    async def test_includes_feedback_when_present(self, db_session: AsyncSession):
        assessment = await _create_assessment(
            db_session,
            user_id=TEST_USER,
            presentation_id=uuid.uuid4(),
            baseline_score=50.0,
            post_score=70.0,
        )
        await _create_feedback(
            db_session,
            user_id=TEST_USER,
            assessment_id=assessment.id,
            perceived_understanding=4,
            confidence=3,
            usefulness=5,
            qualitative_feedback="Great experience",
        )

        service = EffectivenessService(db_session)
        rows = await service.export_study_data(user_id=TEST_USER)
        assert len(rows) == 1
        row = rows[0]
        assert row["fb_perceived_understanding"] == 4
        assert row["fb_confidence"] == 3
        assert row["fb_usefulness"] == 5
        assert row["qualitative_feedback"] == "Great experience"

    async def test_missing_feedback_shows_empty_strings(self, db_session: AsyncSession):
        await _create_assessment(
            db_session,
            user_id=TEST_USER,
            presentation_id=uuid.uuid4(),
            baseline_score=50.0,
            post_score=70.0,
        )

        service = EffectivenessService(db_session)
        rows = await service.export_study_data(user_id=TEST_USER)
        row = rows[0]
        assert row["fb_perceived_understanding"] == ""
        assert row["fb_confidence"] == ""
        assert row["qualitative_feedback"] == ""

    async def test_pseudonymized_participant_id(self, db_session: AsyncSession):
        await _create_assessment(
            db_session,
            user_id=TEST_USER,
            presentation_id=uuid.uuid4(),
            baseline_score=50.0, post_score=70.0,
        )

        service = EffectivenessService(db_session)
        rows = await service.export_study_data(user_id=TEST_USER)
        pid = rows[0]["participant_id"]
        assert len(pid) == 16
        assert pid == hashlib.sha256(str(TEST_USER).encode()).hexdigest()[:16]
        assert str(TEST_USER) not in pid

    async def test_does_not_expose_other_users_data(self, db_session: AsyncSession):
        await _create_assessment(
            db_session,
            user_id=OTHER_USER,
            presentation_id=uuid.uuid4(),
            baseline_score=10.0, post_score=90.0,
            experiment_group="isolation_edu",
        )

        service = EffectivenessService(db_session)
        rows = await service.export_study_data(user_id=TEST_USER)
        assert rows == []

    async def test_csv_injection_prefix(self, db_session: AsyncSession):
        from app.services.effectiveness_service import _sanitize_csv_text
        assert _sanitize_csv_text("=CMD('calc')") == "'=CMD('calc')"
        assert _sanitize_csv_text("+cmd|'/C calc'!") == "'+cmd|'/C calc'!"
        assert _sanitize_csv_text("-SUM(A1:A10)") == "'-SUM(A1:A10)"
        assert _sanitize_csv_text("@SUM(A1)") == "'@SUM(A1)"
        assert _sanitize_csv_text("safe text") == "safe text"
        assert _sanitize_csv_text(None) == ""
        assert _sanitize_csv_text("") == ""

    async def test_null_scores_rendered_as_empty(self, db_session: AsyncSession):
        await _create_assessment(
            db_session,
            user_id=TEST_USER,
            presentation_id=uuid.uuid4(),
            status="in_progress",
        )

        service = EffectivenessService(db_session)
        rows = await service.export_study_data(user_id=TEST_USER)
        row = rows[0]
        assert row["baseline_score"] == ""
        assert row["post_score"] == ""
        assert row["retention_score"] == ""
        assert row["absolute_gain"] == ""
        assert row["normalized_gain"] == ""
class TestExportAPIEndpoint:
    async def _setup_user(self, client, user_id: uuid.UUID):
        from app.core.dependencies import get_current_user
        from app.models.user import User
        app_module = __import__("app.main", fromlist=["app"])
        fake_user = User(id=user_id)
        app_module.app.dependency_overrides[get_current_user] = lambda: fake_user
        return app_module

    async def _teardown_user(self, app_module):
        from app.core.dependencies import get_current_user
        app_module.app.dependency_overrides.pop(get_current_user, None)

    async def test_endpoint_returns_csv(self, client, db_session: AsyncSession):
        user_id = uuid.uuid4()
        app_module = await self._setup_user(client, user_id)
        try:
            pres_id = uuid.uuid4()
            await _create_assessment(
                db_session,
                user_id=user_id,
                presentation_id=pres_id,
                experiment_group="api_export_ref",
                baseline_score=40.0,
                post_score=80.0,
                status="completed",
            )
            await db_session.commit()

            resp = await client.get("/api/v1/effectiveness/export")
            assert resp.status_code == 200
            assert "text/csv" in resp.headers["content-type"]
            assert "eduvision_study_export_" in resp.headers["content-disposition"]

            rows = _parse_csv(resp.text)
            assert len(rows) == 1
            assert rows[0]["experiment_group"] == "api_export_ref"
            assert rows[0]["baseline_score"] == "40.0"
            assert rows[0]["post_score"] == "80.0"
        finally:
            await self._teardown_user(app_module)

    async def test_endpoint_requires_authentication(self, db_session: AsyncSession):
        import httpx

        from app.core.dependencies import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as raw_client:
            resp = await raw_client.get("/api/v1/effectiveness/export")
            assert resp.status_code in (401, 403)

    async def test_filters_by_experiment_group(self, client, db_session: AsyncSession):
        user_id = uuid.uuid4()
        app_module = await self._setup_user(client, user_id)
        try:
            await _create_assessment(
                db_session, user_id=user_id, presentation_id=uuid.uuid4(),
                experiment_group="api_filter_ref", baseline_score=50.0, post_score=70.0,
            )
            await _create_assessment(
                db_session, user_id=user_id, presentation_id=uuid.uuid4(),
                experiment_group="api_filter_edu", baseline_score=30.0, post_score=90.0,
            )
            await db_session.commit()

            resp = await client.get(
                "/api/v1/effectiveness/export",
                params={"experiment_group": "api_filter_edu"},
            )
            assert resp.status_code == 200
            rows = _parse_csv(resp.text)
            assert len(rows) == 1
            assert rows[0]["experiment_group"] == "api_filter_edu"
        finally:
            await self._teardown_user(app_module)

    async def test_empty_dataset_returns_header_only(self, client, db_session: AsyncSession):
        user_id = uuid.uuid4()
        app_module = await self._setup_user(client, user_id)
        try:
            resp = await client.get("/api/v1/effectiveness/export")
            assert resp.status_code == 200
            lines = resp.text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
            assert len(lines) == 1
        finally:
            await self._teardown_user(app_module)

    async def test_no_sensitive_data_exposed(self, client, db_session: AsyncSession):
        user_id = uuid.uuid4()
        app_module = await self._setup_user(client, user_id)
        try:
            await _create_assessment(
                db_session, user_id=user_id, presentation_id=uuid.uuid4(),
                baseline_score=50.0, post_score=70.0,
            )
            await db_session.commit()

            resp = await client.get("/api/v1/effectiveness/export")
            text = resp.text
            assert str(user_id) not in text
            assert "password" not in text.lower()
            assert "token" not in text.lower()
            assert "secret" not in text.lower()
        finally:
            await self._teardown_user(app_module)

    async def test_csv_headers_are_correct(self, client, db_session: AsyncSession):
        user_id = uuid.uuid4()
        app_module = await self._setup_user(client, user_id)
        try:
            resp = await client.get("/api/v1/effectiveness/export")
            lines = resp.text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
            headers = lines[0].split(",")
            expected = [
                "participant_id", "experiment_group", "baseline_score", "post_score",
                "retention_score", "absolute_gain", "normalized_gain",
                "retention_delay_hours", "retention_loss", "retention_pct",
                "learning_time_seconds", "status", "completed_at",
                "fb_perceived_understanding", "fb_confidence", "fb_usefulness",
                "fb_visual_usefulness", "fb_animation_usefulness",
                "fb_tutor_usefulness", "fb_recommendation_usefulness",
                "fb_overall_experience", "qualitative_feedback",
            ]
            assert headers == expected
        finally:
            await self._teardown_user(app_module)

    async def test_no_hardcoded_sample_data(self, client, db_session: AsyncSession):
        user_id = uuid.uuid4()
        app_module = await self._setup_user(client, user_id)
        try:
            await _create_assessment(
                db_session, user_id=user_id, presentation_id=uuid.uuid4(),
                baseline_score=50.0, post_score=70.0,
            )
            await db_session.commit()

            resp = await client.get("/api/v1/effectiveness/export")
            rows = _parse_csv(resp.text)
            for row in rows:
                assert "92.5" not in str(row.values())
                assert "88.0" not in str(row.values())
                assert "usr_" not in str(row.values())
        finally:
            await self._teardown_user(app_module)

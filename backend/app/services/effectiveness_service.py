"""Effectiveness Service — manage assessments, calculate learning gain, produce reports."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.effectiveness_assessment import EffectivenessAssessment
from app.models.quiz_attempt import QuizAttempt
from app.models.user_feedback import UserFeedback
from app.schemas.effectiveness import AssessmentType


class EffectivenessService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_assessment(
        self,
        *,
        user_id: uuid.UUID,
        presentation_id: uuid.UUID,
        experiment_group: str | None = None,
    ) -> EffectivenessAssessment:
        stmt = select(EffectivenessAssessment).where(
            EffectivenessAssessment.user_id == user_id,
            EffectivenessAssessment.presentation_id == presentation_id,
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        assessment = EffectivenessAssessment(
            user_id=user_id,
            presentation_id=presentation_id,
            experiment_group=experiment_group,
        )
        self._session.add(assessment)
        await self._session.flush()
        await self._session.refresh(assessment)
        return assessment

    async def start_assessment(
        self,
        *,
        user_id: uuid.UUID,
        presentation_id: uuid.UUID,
        assessment_type: str,
        experiment_group: str | None = None,
        retention_delay_hours: int | None = None,
    ) -> dict[str, Any]:
        if assessment_type not in (
            AssessmentType.BASELINE,
            AssessmentType.POST,
            AssessmentType.RETENTION,
        ):
            raise ValidationError(message=f"Invalid assessment type: {assessment_type}")

        assessment = await self.get_or_create_assessment(
            user_id=user_id,
            presentation_id=presentation_id,
            experiment_group=experiment_group,
        )

        if assessment_type == AssessmentType.BASELINE and assessment.baseline_quiz_id:
            raise ValidationError(message="Baseline assessment already completed for this presentation")
        if assessment_type == AssessmentType.POST and assessment.post_quiz_id:
            raise ValidationError(message="Post assessment already completed for this presentation")
        if assessment_type == AssessmentType.RETENTION and assessment.retention_quiz_id:
            raise ValidationError(message="Retention assessment already completed")

        if assessment_type == AssessmentType.RETENTION and retention_delay_hours:
            assessment.retention_delay_hours = retention_delay_hours

        await self._session.flush()

        return {
            "assessment_public_id": assessment.public_id,
            "assessment_type": assessment_type,
            "message": f"Assessment {assessment_type} ready. Create a quiz with assessment_type={assessment_type}.",
        }

    async def record_quiz_score(
        self,
        *,
        user_id: uuid.UUID,
        assessment_id: uuid.UUID,
        assessment_type: str,
        quiz_id: uuid.UUID,
        score: float,
        concept_scores: dict[str, float] | None = None,
    ) -> EffectivenessAssessment:
        stmt = select(EffectivenessAssessment).where(
            EffectivenessAssessment.id == assessment_id,
            EffectivenessAssessment.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        assessment = result.scalar_one_or_none()
        if assessment is None:
            raise NotFoundError(message="Assessment not found")

        if assessment_type == AssessmentType.BASELINE:
            assessment.baseline_quiz_id = quiz_id
            assessment.baseline_score = score
            assessment.baseline_concept_scores = concept_scores
        elif assessment_type == AssessmentType.POST:
            assessment.post_quiz_id = quiz_id
            assessment.post_score = score
            assessment.post_concept_scores = concept_scores
        elif assessment_type == AssessmentType.RETENTION:
            assessment.retention_quiz_id = quiz_id
            assessment.retention_score = score
            assessment.retention_concept_scores = concept_scores

        self._compute_gains(assessment)
        await self._session.flush()
        await self._session.refresh(assessment)
        return assessment

    async def record_attempt_score(
        self,
        *,
        user_id: uuid.UUID,
        assessment_id: uuid.UUID,
        assessment_type: str,
        quiz_attempt_id: uuid.UUID,
        concept_scores: dict[str, float] | None = None,
    ) -> EffectivenessAssessment:
        stmt = select(QuizAttempt).where(
            QuizAttempt.id == quiz_attempt_id,
            QuizAttempt.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        attempt = result.scalar_one_or_none()
        if attempt is None:
            raise NotFoundError(message="Quiz attempt not found")
        if attempt.percent_score is None:
            raise ValidationError(message="Quiz attempt not yet completed")

        score = float(attempt.percent_score)
        return await self.record_quiz_score(
            user_id=user_id,
            assessment_id=assessment_id,
            assessment_type=assessment_type,
            quiz_id=attempt.quiz_id,
            score=score,
            concept_scores=concept_scores,
        )

    def _compute_gains(self, assessment: EffectivenessAssessment) -> None:
        if assessment.baseline_score is not None and assessment.post_score is not None:
            assessment.absolute_gain = assessment.post_score - assessment.baseline_score
            denom = 100.0 - assessment.baseline_score
            if denom > 0:
                assessment.normalized_gain = assessment.absolute_gain / denom
            else:
                assessment.normalized_gain = 0.0

        if assessment.post_score is not None and assessment.retention_score is not None:
            assessment.retention_loss = assessment.post_score - assessment.retention_score
            if assessment.post_score > 0:
                assessment.retention_pct = (
                    assessment.retention_score / assessment.post_score
                ) * 100.0
            else:
                assessment.retention_pct = 0.0

        has_scores = (
            assessment.baseline_score is not None
            or assessment.post_score is not None
            or assessment.retention_score is not None
        )
        all_done = (
            assessment.baseline_score is not None
            and assessment.post_score is not None
        )
        if assessment.retention_quiz_id:
            all_done = all_done and assessment.retention_score is not None

        if all_done:
            assessment.status = "completed"
        elif has_scores:
            assessment.status = "in_progress"
        else:
            assessment.status = "not_started"

    async def get_assessment(
        self,
        *,
        user_id: uuid.UUID,
        presentation_id: uuid.UUID,
    ) -> EffectivenessAssessment | None:
        stmt = select(EffectivenessAssessment).where(
            EffectivenessAssessment.user_id == user_id,
            EffectivenessAssessment.presentation_id == presentation_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_assessment_by_id(
        self,
        *,
        user_id: uuid.UUID,
        assessment_id: uuid.UUID,
    ) -> EffectivenessAssessment:
        stmt = select(EffectivenessAssessment).where(
            EffectivenessAssessment.id == assessment_id,
            EffectivenessAssessment.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        assessment = result.scalar_one_or_none()
        if assessment is None:
            raise NotFoundError(message="Assessment not found")
        return assessment

    async def compute_learning_gain(
        self,
        *,
        user_id: uuid.UUID,
        presentation_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        assessment = await self.get_assessment(
            user_id=user_id,
            presentation_id=presentation_id,
        )
        if assessment is None:
            return None
        return self._format_gain(assessment)

    def _format_gain(self, assessment: EffectivenessAssessment) -> dict[str, Any]:
        concept_improvements: list[dict[str, Any]] = []
        weak: list[str] = []
        strong: list[str] = []

        if assessment.baseline_concept_scores and assessment.post_concept_scores:
            for concept, post_val in assessment.post_concept_scores.items():
                pre_val = assessment.baseline_concept_scores.get(concept, 0.0)
                improvement = post_val - pre_val
                entry = {
                    "concept": concept,
                    "pre": pre_val,
                    "post": post_val,
                    "improvement": improvement,
                }
                if assessment.retention_concept_scores:
                    entry["retention"] = assessment.retention_concept_scores.get(concept)
                concept_improvements.append(entry)

                if improvement > 0 and post_val >= 80:
                    strong.append(concept)
                elif post_val < 50:
                    weak.append(concept)

        return {
            "assessment_public_id": assessment.public_id,
            "presentation_id": str(assessment.presentation_id),
            "experiment_group": assessment.experiment_group,
            "baseline_score": assessment.baseline_score,
            "post_score": assessment.post_score,
            "absolute_gain": assessment.absolute_gain,
            "normalized_gain": assessment.normalized_gain,
            "retention_score": assessment.retention_score,
            "retention_loss": assessment.retention_loss,
            "retention_pct": assessment.retention_pct,
            "total_learning_time_seconds": assessment.total_learning_time_seconds,
            "events_summary": assessment.events_summary,
            "concept_improvements": concept_improvements,
            "weak_concepts": weak,
            "strong_concepts": strong,
            "status": assessment.status,
            "completed_at": assessment.completed_at,
        }

    async def user_summary(
        self,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        stmt = select(EffectivenessAssessment).where(
            EffectivenessAssessment.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        assessments = list(result.scalars().all())

        completed = [a for a in assessments if a.status == "completed"]
        baselines = [a.baseline_score for a in assessments if a.baseline_score is not None]
        posts = [a.post_score for a in assessments if a.post_score is not None]
        gains = [a.absolute_gain for a in assessments if a.absolute_gain is not None]
        norm_gains = [a.normalized_gain for a in assessments if a.normalized_gain is not None]
        times = [a.total_learning_time_seconds or 0 for a in assessments]
        pres_ids = {a.presentation_id for a in assessments}

        return {
            "total_assessments": len(assessments),
            "completed_assessments": len(completed),
            "avg_baseline_score": sum(baselines) / len(baselines) if baselines else None,
            "avg_post_score": sum(posts) / len(posts) if posts else None,
            "avg_absolute_gain": sum(gains) / len(gains) if gains else None,
            "avg_normalized_gain": sum(norm_gains) / len(norm_gains) if norm_gains else None,
            "total_learning_time_seconds": sum(times),
            "presentations_covered": len(pres_ids),
        }

    async def set_learning_time(
        self,
        *,
        user_id: uuid.UUID,
        presentation_id: uuid.UUID,
        seconds: int,
    ) -> None:
        assessment = await self.get_assessment(
            user_id=user_id,
            presentation_id=presentation_id,
        )
        if assessment:
            assessment.total_learning_time_seconds = seconds
            await self._session.flush()

    async def compare_groups(
        self,
        *,
        group_a: str,
        group_b: str,
    ) -> dict[str, Any]:
        stmt_a = select(EffectivenessAssessment).where(
            EffectivenessAssessment.experiment_group == group_a,
        )
        stmt_b = select(EffectivenessAssessment).where(
            EffectivenessAssessment.experiment_group == group_b,
        )
        result_a = await self._session.execute(stmt_a)
        result_b = await self._session.execute(stmt_b)
        assessments_a = list(result_a.scalars().all())
        assessments_b = list(result_b.scalars().all())

        def _aggregate(assessments: list[EffectivenessAssessment]) -> dict[str, Any]:
            baselines = [a.baseline_score for a in assessments if a.baseline_score is not None]
            posts = [a.post_score for a in assessments if a.post_score is not None]
            gains = [a.absolute_gain for a in assessments if a.absolute_gain is not None]
            norm_gains = [a.normalized_gain for a in assessments if a.normalized_gain is not None]
            retentions = [a.retention_score for a in assessments if a.retention_score is not None]
            retention_losses = [a.retention_loss for a in assessments if a.retention_loss is not None]
            retention_pcts = [a.retention_pct for a in assessments if a.retention_pct is not None]
            completed = sum(1 for a in assessments if a.status == "completed")
            return {
                "count": len(assessments),
                "completed": completed,
                "avg_baseline": sum(baselines) / len(baselines) if baselines else None,
                "avg_post": sum(posts) / len(posts) if posts else None,
                "avg_absolute_gain": sum(gains) / len(gains) if gains else None,
                "avg_normalized_gain": sum(norm_gains) / len(norm_gains) if norm_gains else None,
                "avg_retention_score": sum(retentions) / len(retentions) if retentions else None,
                "avg_retention_loss": sum(retention_losses) / len(retention_losses) if retention_losses else None,
                "avg_retention_pct": sum(retention_pcts) / len(retention_pcts) if retention_pcts else None,
            }

        agg_a = _aggregate(assessments_a)
        agg_b = _aggregate(assessments_b)

        return {
            "group_a": group_a,
            "group_b": group_b,
            "group_a_count": agg_a["count"],
            "group_b_count": agg_b["count"],
            "group_a_avg_baseline": agg_a["avg_baseline"],
            "group_b_avg_baseline": agg_b["avg_baseline"],
            "group_a_avg_post": agg_a["avg_post"],
            "group_b_avg_post": agg_b["avg_post"],
            "group_a_avg_absolute_gain": agg_a["avg_absolute_gain"],
            "group_b_avg_absolute_gain": agg_b["avg_absolute_gain"],
            "group_a_avg_normalized_gain": agg_a["avg_normalized_gain"],
            "group_b_avg_normalized_gain": agg_b["avg_normalized_gain"],
            "group_a_avg_retention_score": agg_a["avg_retention_score"],
            "group_b_avg_retention_score": agg_b["avg_retention_score"],
            "group_a_avg_retention_loss": agg_a["avg_retention_loss"],
            "group_b_avg_retention_loss": agg_b["avg_retention_loss"],
            "group_a_avg_retention_pct": agg_a["avg_retention_pct"],
            "group_b_avg_retention_pct": agg_b["avg_retention_pct"],
            "group_a_completed": agg_a["completed"],
            "group_b_completed": agg_b["completed"],
        }

    async def export_study_data(
        self,
        *,
        user_id: uuid.UUID,
        experiment_group: str | None = None,
    ) -> list[dict[str, Any]]:
        """Export real study data for the authenticated user.

        Each row represents one effectiveness assessment with joined feedback.
        Participant IDs are pseudonymized via SHA-256 hash.
        """
        fb_subq = (
            select(
                UserFeedback.assessment_id,
                func.max(UserFeedback.perceived_understanding).label("fb_understanding"),
                func.max(UserFeedback.confidence).label("fb_confidence"),
                func.max(UserFeedback.usefulness).label("fb_usefulness"),
                func.max(UserFeedback.visual_usefulness).label("fb_visual"),
                func.max(UserFeedback.animation_usefulness).label("fb_animation"),
                func.max(UserFeedback.tutor_usefulness).label("fb_tutor"),
                func.max(UserFeedback.recommendation_usefulness).label("fb_recommendation"),
                func.max(UserFeedback.overall_experience).label("fb_overall"),
                func.max(UserFeedback.qualitative_feedback).label("fb_text"),
            )
            .where(UserFeedback.user_id == user_id)
            .group_by(UserFeedback.assessment_id)
            .subquery()
        )

        stmt = select(
            EffectivenessAssessment.public_id,
            EffectivenessAssessment.user_id,
            EffectivenessAssessment.experiment_group,
            EffectivenessAssessment.baseline_score,
            EffectivenessAssessment.post_score,
            EffectivenessAssessment.retention_score,
            EffectivenessAssessment.absolute_gain,
            EffectivenessAssessment.normalized_gain,
            EffectivenessAssessment.retention_loss,
            EffectivenessAssessment.retention_pct,
            EffectivenessAssessment.retention_delay_hours,
            EffectivenessAssessment.total_learning_time_seconds,
            EffectivenessAssessment.status,
            EffectivenessAssessment.completed_at,
            EffectivenessAssessment.created_at,
            fb_subq.c.fb_understanding,
            fb_subq.c.fb_confidence,
            fb_subq.c.fb_usefulness,
            fb_subq.c.fb_visual,
            fb_subq.c.fb_animation,
            fb_subq.c.fb_tutor,
            fb_subq.c.fb_recommendation,
            fb_subq.c.fb_overall,
            fb_subq.c.fb_text,
        ).outerjoin(
            fb_subq,
            EffectivenessAssessment.id == fb_subq.c.assessment_id,
        ).where(
            EffectivenessAssessment.user_id == user_id,
        )

        if experiment_group:
            stmt = stmt.where(
                EffectivenessAssessment.experiment_group == experiment_group,
            )

        stmt = stmt.order_by(EffectivenessAssessment.created_at)

        result = await self._session.execute(stmt)
        rows = list(result.all())

        export_rows: list[dict[str, Any]] = []
        for row in rows:
            export_rows.append({
                "participant_id": hashlib.sha256(str(row.user_id).encode()).hexdigest()[:16],
                "experiment_group": row.experiment_group or "",
                "baseline_score": row.baseline_score if row.baseline_score is not None else "",
                "post_score": row.post_score if row.post_score is not None else "",
                "retention_score": row.retention_score if row.retention_score is not None else "",
                "absolute_gain": row.absolute_gain if row.absolute_gain is not None else "",
                "normalized_gain": row.normalized_gain if row.normalized_gain is not None else "",
                "retention_delay_hours": row.retention_delay_hours if row.retention_delay_hours is not None else "",
                "retention_loss": row.retention_loss if row.retention_loss is not None else "",
                "retention_pct": row.retention_pct if row.retention_pct is not None else "",
                "learning_time_seconds": row.total_learning_time_seconds if row.total_learning_time_seconds is not None else "",
                "status": row.status or "",
                "completed_at": row.completed_at.isoformat() if row.completed_at else "",
                "fb_perceived_understanding": row.fb_understanding if row.fb_understanding is not None else "",
                "fb_confidence": row.fb_confidence if row.fb_confidence is not None else "",
                "fb_usefulness": row.fb_usefulness if row.fb_usefulness is not None else "",
                "fb_visual_usefulness": row.fb_visual if row.fb_visual is not None else "",
                "fb_animation_usefulness": row.fb_animation if row.fb_animation is not None else "",
                "fb_tutor_usefulness": row.fb_tutor if row.fb_tutor is not None else "",
                "fb_recommendation_usefulness": row.fb_recommendation if row.fb_recommendation is not None else "",
                "fb_overall_experience": row.fb_overall if row.fb_overall is not None else "",
                "qualitative_feedback": _sanitize_csv_text(row.fb_text) if row.fb_text else "",
            })

        return export_rows


def _sanitize_csv_text(text: str | None) -> str:
    """Prevent CSV injection by prefixing dangerous characters.

    Spreadsheet formulas start with =, +, -, @, or tab/carriage-return.
    Prefixing with a single quote neutralizes formula interpretation
    while keeping the text readable.
    """
    if not text:
        return ""
    dangerous_prefixes = ("=", "+", "-", "@", "\t", "\r")
    if text.startswith(dangerous_prefixes):
        return "'" + text
    return text

"""Learning Effectiveness API router — assessments, learning gain, feedback, analytics."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_current_user
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.effectiveness import (
    EffectivenessReportResponse,
    FeedbackSubmitRequest,
    FeedbackSummary,
    GroupComparisonResponse,
    LearningEventCreate,
    LearningEventListResponse,
    LearningEventResponse,
    LearningGainResponse,
    RecordScoreRequest,
    StartAssessmentRequest,
    StartAssessmentResponse,
    UserEffectivenessSummary,
)
from app.services.effectiveness_service import EffectivenessService
from app.services.feedback_service import UserFeedbackService
from app.services.learning_event_service import LearningEventService

effectiveness_router = APIRouter(prefix="/effectiveness", tags=["Learning Effectiveness"])


# ── Learning Events ──────────────────────────────────────────────────────


@effectiveness_router.post(
    "/events",
    response_model=APIResponse[LearningEventResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Record a learning event",
)
async def record_learning_event(
    request: LearningEventCreate,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[LearningEventResponse]:
    pres_id = uuid.UUID(request.presentation_id) if request.presentation_id else None
    service = LearningEventService(uow.session)
    event = await service.record(
        user_id=user.id,
        event_type=request.event_type,
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        concept_id=request.concept_id,
        presentation_id=pres_id,
        metadata_json=request.metadata_json,
        occurred_at=request.occurred_at,
    )
    return APIResponse(
        data=LearningEventResponse.model_validate(event),
        message="Event recorded",
    )


@effectiveness_router.get(
    "/events",
    response_model=APIResponse[LearningEventListResponse],
    summary="List learning events for the current user",
)
async def list_learning_events(
    user: User = Depends(get_current_user),
    event_type: str | None = Query(None),
    presentation_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[LearningEventListResponse]:
    pres_id = uuid.UUID(presentation_id) if presentation_id else None
    service = LearningEventService(uow.session)
    events, total = await service.list_for_user(
        user.id,
        event_type=event_type,
        presentation_id=pres_id,
        limit=limit,
        offset=offset,
    )
    return APIResponse(
        data=LearningEventListResponse(
            events=[LearningEventResponse.model_validate(e) for e in events],
            total=total,
        ),
    )


# ── Assessments ──────────────────────────────────────────────────────────


@effectiveness_router.post(
    "/assessments/start",
    response_model=APIResponse[StartAssessmentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Start a baseline, post, or retention assessment",
)
async def start_assessment(
    request: StartAssessmentRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[StartAssessmentResponse]:
    pres_id = uuid.UUID(request.presentation_id)
    service = EffectivenessService(uow.session)
    result = await service.start_assessment(
        user_id=user.id,
        presentation_id=pres_id,
        assessment_type=request.assessment_type,
        experiment_group=request.experiment_group,
        retention_delay_hours=request.retention_delay_hours,
    )
    return APIResponse(
        data=StartAssessmentResponse(**result),
        message=f"Assessment {request.assessment_type} ready",
    )


@effectiveness_router.post(
    "/assessments/{assessment_id}/record-score",
    response_model=APIResponse[LearningGainResponse],
    summary="Record a quiz attempt score for an assessment",
)
async def record_assessment_score(
    assessment_id: uuid.UUID,
    request: RecordScoreRequest,
    assessment_type: str = Query(..., pattern="^(baseline|post|retention)$"),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[LearningGainResponse]:
    service = EffectivenessService(uow.session)
    assessment = await service.record_attempt_score(
        user_id=user.id,
        assessment_id=assessment_id,
        assessment_type=assessment_type,
        quiz_attempt_id=uuid.UUID(request.quiz_attempt_id),
        concept_scores=request.concept_scores,
    )
    return APIResponse(
        data=LearningGainResponse.model_validate(assessment),
        message="Score recorded",
    )


@effectiveness_router.get(
    "/assessments/{presentation_id}",
    response_model=APIResponse[LearningGainResponse],
    summary="Get assessment results for a presentation",
)
async def get_assessment(
    presentation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[LearningGainResponse]:
    service = EffectivenessService(uow.session)
    assessment = await service.get_assessment(
        user_id=user.id,
        presentation_id=presentation_id,
    )
    if assessment is None:
        from app.core.exceptions import NotFoundError
        raise NotFoundError(message="No assessment found for this presentation")
    return APIResponse(
        data=LearningGainResponse.model_validate(assessment),
    )


@effectiveness_router.get(
    "/learning-gain/{presentation_id}",
    response_model=APIResponse[dict],
    summary="Calculate learning gain for a presentation",
)
async def get_learning_gain(
    presentation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[dict]:
    service = EffectivenessService(uow.session)
    gain = await service.compute_learning_gain(
        user_id=user.id,
        presentation_id=presentation_id,
    )
    if gain is None:
        from app.core.exceptions import NotFoundError
        raise NotFoundError(message="No assessment data for this presentation")
    return APIResponse(data=gain)


@effectiveness_router.get(
    "/summary",
    response_model=APIResponse[UserEffectivenessSummary],
    summary="Get overall effectiveness summary for the current user",
)
async def get_user_summary(
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[UserEffectivenessSummary]:
    service = EffectivenessService(uow.session)
    summary = await service.user_summary(user.id)
    return APIResponse(data=UserEffectivenessSummary(**summary))


@effectiveness_router.get(
    "/report/{presentation_id}",
    response_model=APIResponse[EffectivenessReportResponse],
    summary="Get full effectiveness report for a presentation",
)
async def get_effectiveness_report(
    presentation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[EffectivenessReportResponse]:
    service = EffectivenessService(uow.session)
    gain = await service.compute_learning_gain(
        user_id=user.id,
        presentation_id=presentation_id,
    )
    if gain is None:
        from app.core.exceptions import NotFoundError
        raise NotFoundError(message="No assessment data for this presentation")

    pres = await service.get_owned_presentation(
        user_id=user.id,
        presentation_id=presentation_id,
    )

    return APIResponse(
        data=EffectivenessReportResponse(
            assessment_public_id=gain["assessment_public_id"],
            presentation_id=gain["presentation_id"],
            presentation_title=pres.title if pres else None,
            baseline_score=gain["baseline_score"],
            post_score=gain["post_score"],
            absolute_gain=gain["absolute_gain"],
            normalized_gain=gain["normalized_gain"],
            retention_score=gain["retention_score"],
            retention_loss=gain["retention_loss"],
            retention_pct=gain["retention_pct"],
            total_learning_time_seconds=gain["total_learning_time_seconds"],
            events_summary=gain["events_summary"],
            concept_improvements=gain["concept_improvements"],
            weak_concepts=gain["weak_concepts"],
            strong_concepts=gain["strong_concepts"],
            status=gain["status"],
            completed_at=gain["completed_at"],
        ),
    )


# ── Feedback ─────────────────────────────────────────────────────────────


@effectiveness_router.post(
    "/feedback",
    response_model=APIResponse[dict],
    status_code=status.HTTP_201_CREATED,
    summary="Submit optional learning feedback",
)
async def submit_feedback(
    request: FeedbackSubmitRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[dict]:
    pres_id = uuid.UUID(request.presentation_id) if request.presentation_id else None
    assess_id = uuid.UUID(request.assessment_id) if request.assessment_id else None
    service = UserFeedbackService(uow.session)
    feedback = await service.submit(
        user_id=user.id,
        presentation_id=pres_id,
        assessment_id=assess_id,
        perceived_understanding=request.perceived_understanding,
        confidence=request.confidence,
        usefulness=request.usefulness,
        visual_usefulness=request.visual_usefulness,
        animation_usefulness=request.animation_usefulness,
        tutor_usefulness=request.tutor_usefulness,
        recommendation_usefulness=request.recommendation_usefulness,
        overall_experience=request.overall_experience,
        qualitative_feedback=request.qualitative_feedback,
    )
    return APIResponse(
        data={"public_id": feedback.public_id},
        message="Feedback submitted",
    )


@effectiveness_router.get(
    "/feedback/summary/{presentation_id}",
    response_model=APIResponse[FeedbackSummary],
    summary="Get aggregated feedback for a presentation",
)
async def get_feedback_summary(
    presentation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[FeedbackSummary]:
    from sqlalchemy import or_ as sa_or
    from sqlalchemy import select as sa_select

    from app.core.exceptions import NotFoundError
    from app.models.presentation import Presentation

    stmt = sa_select(Presentation).where(
        sa_or(
            Presentation.id == presentation_id,
            Presentation.public_id == str(presentation_id),
        ),
        Presentation.deleted_at.is_(None),
    )
    pres = (await uow.session.execute(stmt)).scalar_one_or_none()
    if pres is None or pres.owner_id != user.id:
        raise NotFoundError("Presentation not found")
    service = UserFeedbackService(uow.session)
    summary = await service.summary_for_presentation(presentation_id)
    return APIResponse(data=FeedbackSummary(**summary))


# ── Group Comparison ────────────────────────────────────────────────────


@effectiveness_router.get(
    "/comparison",
    response_model=APIResponse[GroupComparisonResponse],
    summary="Compare learning effectiveness between two experiment groups",
)
async def compare_groups(
    group_a: str = Query(..., min_length=1, max_length=50),
    group_b: str = Query(..., min_length=1, max_length=50),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[GroupComparisonResponse]:
    service = EffectivenessService(uow.session)
    result = await service.compare_groups(group_a=group_a, group_b=group_b)
    return APIResponse(data=GroupComparisonResponse(**result))


# ── CSV Export ────────────────────────────────────────────────────────────

_STUDY_CSV_HEADERS = [
    "participant_id",
    "experiment_group",
    "baseline_score",
    "post_score",
    "retention_score",
    "absolute_gain",
    "normalized_gain",
    "retention_delay_hours",
    "retention_loss",
    "retention_pct",
    "learning_time_seconds",
    "status",
    "completed_at",
    "fb_perceived_understanding",
    "fb_confidence",
    "fb_usefulness",
    "fb_visual_usefulness",
    "fb_animation_usefulness",
    "fb_tutor_usefulness",
    "fb_recommendation_usefulness",
    "fb_overall_experience",
    "qualitative_feedback",
]


@effectiveness_router.get(
    "/export",
    summary="Export study effectiveness data as CSV",
)
async def export_study_csv(
    user: User = Depends(get_current_user),
    experiment_group: str | None = Query(None, max_length=50),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> StreamingResponse:
    service = EffectivenessService(uow.session)
    rows = await service.export_study_data(
        user_id=user.id,
        experiment_group=experiment_group,
    )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_STUDY_CSV_HEADERS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    csv_bytes = buf.getvalue().encode("utf-8")
    buf.close()

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"eduvision_study_export_{timestamp}.csv"

    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )

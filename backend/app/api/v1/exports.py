"""API Router for the live export capability (P4 WS2).

Wraps the previously-dead ``ExportService`` + ``export_generation_task`` into a
user-invocable, ownership-checked, progress-tracked flow. Ownership is enforced
at the presentation level (the natural export target) and the job rows are
scoped to the owning user so cross-user enumeration is impossible.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError, ValidationError
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.common import APIResponse, PaginatedResponse, PaginationMeta
from app.schemas.export import (
    ExportCreateRequest,
    ExportJobData,
    ExportStatusData,
)
from app.services.export_service import ExportService
from app.services.presentation_service import PresentationService
from app.utils.pagination_helpers import create_page_meta

exports_router = APIRouter(prefix="/exports", tags=["Exports"])

# Hard bound on how many active (queued/processing) jobs a single user may hold
# concurrently. Guards against unbounded task/worker accumulation per account.
ACTIVE_EXPORT_JOBS_LIMIT = 10


@exports_router.post(
    "",
    response_model=APIResponse[ExportJobData],
    status_code=status.HTTP_201_CREATED,
    summary="Create an export job for an owned presentation",
)
async def create_export(
    request: ExportCreateRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[ExportJobData]:
    if not request.target_id:
        raise ValidationError(
            message="Export target is required",
            details={"reason": "A presentation targetId must be supplied."},
        )

    # Ownership: only the owner may export a presentation. Ownerless/foreign
    # targets resolve to a uniform 404 so no cross-user resource is guessed.
    pres_service = PresentationService(uow)
    await pres_service.assert_ownership(request.target_id, owner_id=user.id)

    service = ExportService(uow=uow)
    active_count = await service.count_active_jobs(user_id=user.id)
    if active_count >= ACTIVE_EXPORT_JOBS_LIMIT:
        raise ValidationError(
            message="Too many active export jobs",
            details={
                "limit": ACTIVE_EXPORT_JOBS_LIMIT,
"active": active_count,
            },
        )

    job = await service.create_export_job(
        user_id=user.id,
        kind=request.kind,
        format=request.format,
        target_id=request.target_id,
        include_modes=request.include_modes,
        options=request.options,
        template_key=request.template_key,
    )
    # ``create_export_job`` commits its unit of work on exit, so the job row is
    # durable before dispatch: a broker hiccup never references a row the worker
    # cannot read back.
    await service.dispatch_export_job(job.public_id)

    return APIResponse(
        data=ExportJobData(
            exportId=job.public_id,
            status=job.status,
            queuedAt=job.created_at,
            progressPercentage=job.progress_percentage,
            kind=job.kind,
            format=job.format,
        ),
        message="Export job created",
    )


@exports_router.get(
    "/{export_id}",
    response_model=APIResponse[ExportStatusData],
    summary="Poll export job status for the current user",
)
async def get_export_status(
    export_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[ExportStatusData]:
    service = ExportService(uow=uow)
    try:
        data = await service.get_export_job_status(user_id=user.id, public_id=export_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found")
    return APIResponse(data=ExportStatusData(**data))


@exports_router.get(
    "",
    response_model=PaginatedResponse[ExportJobData],
    summary="List the current user's export jobs (paginated)",
)
async def list_exports(
    user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PaginatedResponse[ExportJobData]:
    service = ExportService(uow=uow)
    jobs = await service.list_user_exports(user_id=user.id, offset=offset, limit=limit)
    total = await service.count_user_exports(user_id=user.id)
    meta = PaginationMeta(**create_page_meta(offset // limit + 1, limit, total))
    return PaginatedResponse(
        data=[
            ExportJobData(
                exportId=job.public_id,
                status=job.status,
                queuedAt=job.created_at,
                progressPercentage=job.progress_percentage,
                kind=job.kind,
                format=job.format,
            )
            for job in jobs
        ],
        pagination=meta,
    )


@exports_router.delete(
    "/{export_id}",
    response_model=APIResponse[dict[str, str]],
    summary="Cancel a queued/processing export job (owner-only)",
)
async def cancel_export(
    export_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[dict[str, str]]:
    service = ExportService(uow=uow)
    try:
        await service.cancel_export_job(user_id=user.id, public_id=export_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found")
    return APIResponse(data={"exportId": export_id}, message="Export job cancelled")


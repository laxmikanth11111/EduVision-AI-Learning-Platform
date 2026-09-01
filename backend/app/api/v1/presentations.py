from __future__ import annotations

import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.common import APIResponse, PaginatedResponse, PaginationMeta
from app.schemas.content import ContentListResponse, ProcessingStatusResponse
from app.schemas.generated_lesson import (
    GeneratedLessonResponse,
    GeneratedLessonStatusResponse,
    GeneratedLessonSummary,
    GeneratedVersionDetailResponse,
    GeneratedVersionResponse,
    LessonGenerationRequest,
)
from app.schemas.presentation import (
    AutosaveRequest,
    AutosaveResponse,
    PresentationCreateRequest,
    PresentationManualRequest,
    PresentationResponse,
    PresentationSummary,
    PresentationUpdateRequest,
    PublishPresentationResponse,
    ThumbnailRegenerateResponse,
    ThumbnailResponse,
    UnpublishPresentationResponse,
    VersionComparisonResponse,
    VersionSaveRequest,
)
from app.schemas.presentation_analytics import AnalyticsResponse
from app.schemas.presentation_audit_log import AuditLogResponse
from app.schemas.presentation_version import VersionResponse
from app.schemas.topic_outline import TopicOutlineOut
from app.services.presentation_service import PresentationService
from app.utils.pagination_helpers import create_page_meta

presentations_router = APIRouter(prefix="/presentations", tags=["Presentations"])


async def _read_upload_bounded(upload: UploadFile) -> bytes:
    """Read an upload, enforcing a hard byte limit on the body.

    The request-size middleware only checks the declared ``Content-Length``
    header; it does not bound the actual streamed body. This helper caps the
    read at ``settings.UPLOAD_MAX_FILE_SIZE`` so a misdeclared or chunked
    request cannot force an unbounded read into memory.
    """
    content = await upload.read(settings.UPLOAD_MAX_FILE_SIZE + 1)
    if len(content) > settings.UPLOAD_MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Upload exceeds the maximum allowed size of {settings.UPLOAD_MAX_FILE_SIZE} bytes.",
        )
    return content


@presentations_router.get(
    "",
    response_model=PaginatedResponse[PresentationSummary],
)
async def list_presentations(
    user: User = Depends(get_current_user),
    q: str | None = Query(None, max_length=300),
    status: str | None = Query(None),
    subject_id: str | None = Query(None, max_length=100),
    grade_level: str | None = Query(None, max_length=50),
    folder_id: uuid.UUID | None = None,
    tag: str | None = Query(None, max_length=50),
    topic: str | None = Query(None, max_length=300),
    visibility: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str = Query("updated_at", max_length=50),
    descending: bool = Query(True),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PaginatedResponse[PresentationSummary]:
    service = PresentationService(uow)
    items, total = await service.list_presentations(
        owner_id=user.id,
        q=q,
        status=status,
        subject_id=subject_id,
        grade_level=grade_level,
        folder_id=folder_id,
        tag=tag,
        topic=topic,
        visibility=visibility,
        page=page,
        page_size=page_size,
        sort=sort,
        descending=descending,
    )
    return PaginatedResponse(
        data=[PresentationSummary(**item) for item in items],
        pagination=PaginationMeta(**create_page_meta(page, page_size, total)),
    )


@presentations_router.post(
    "",
    response_model=APIResponse[PresentationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_presentation(
    request: PresentationCreateRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PresentationResponse]:
    service = PresentationService(uow)
    result = await service.create_presentation(request, owner_id=user.id)
    return APIResponse(
        data=PresentationResponse(**result),
        message="Presentation created successfully",
    )


@presentations_router.post(
    "/manual",
    response_model=APIResponse[PresentationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_presentation(
    request: PresentationManualRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PresentationResponse]:
    service = PresentationService(uow)
    result = await service.create_manual_presentation(request, owner_id=user.id)
    return APIResponse(
        data=PresentationResponse(**result),
        message="Manual presentation created successfully",
    )


@presentations_router.get(
    "/{presentation_id}",
    response_model=APIResponse[PresentationResponse],
)
async def get_presentation(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PresentationResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.get_presentation(presentation_id)
    return APIResponse(data=PresentationResponse(**result))


@presentations_router.patch(
    "/{presentation_id}",
    response_model=APIResponse[PresentationResponse],
)
async def update_presentation(
    presentation_id: str,
    request: PresentationUpdateRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PresentationResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.update_presentation(presentation_id, request)
    return APIResponse(data=PresentationResponse(**result))


@presentations_router.delete(
    "/{presentation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_presentation(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Response:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    await service.delete_presentation(presentation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@presentations_router.post(
    "/{presentation_id}/publish",
    response_model=APIResponse[PublishPresentationResponse],
)
async def publish_presentation(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PublishPresentationResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.publish_presentation(presentation_id)
    return APIResponse(
        data=PublishPresentationResponse(**result),
        message="Presentation published successfully",
    )


@presentations_router.post(
    "/{presentation_id}/unpublish",
    response_model=APIResponse[UnpublishPresentationResponse],
)
async def unpublish_presentation(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[UnpublishPresentationResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.unpublish_presentation(presentation_id)
    return APIResponse(
        data=UnpublishPresentationResponse(**result),
        message="Presentation unpublished successfully",
    )


@presentations_router.post(
    "/{presentation_id}/archive",
    response_model=APIResponse[PresentationResponse],
)
async def archive_presentation(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PresentationResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.archive_presentation(presentation_id)
    return APIResponse(data=PresentationResponse(**result))


@presentations_router.post(
    "/{presentation_id}/restore",
    response_model=APIResponse[PresentationResponse],
)
async def restore_presentation(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PresentationResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.restore_presentation(presentation_id)
    return APIResponse(data=PresentationResponse(**result))


@presentations_router.post(
    "/{presentation_id}/autosave",
    response_model=APIResponse[AutosaveResponse],
)
async def autosave_presentation(
    presentation_id: str,
    request: AutosaveRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AutosaveResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.autosave(presentation_id, request)
    return APIResponse(data=AutosaveResponse(**result))


@presentations_router.get(
    "/{presentation_id}/versions",
    response_model=APIResponse[list[VersionResponse]],
)
async def list_versions(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[list[VersionResponse]]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    versions = await service.list_versions(presentation_id)
    return APIResponse(data=[VersionResponse(**version) for version in versions])


@presentations_router.post(
    "/{presentation_id}/versions",
    response_model=APIResponse[VersionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def save_version(
    presentation_id: str,
    request: VersionSaveRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[VersionResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.save_version(
        presentation_id, diff_summary=request.diff_summary
    )
    return APIResponse(
        data=VersionResponse(**result),
        message="Version saved successfully",
    )


@presentations_router.get(
    "/{presentation_id}/versions/compare",
    response_model=APIResponse[VersionComparisonResponse],
)
async def compare_versions(
    presentation_id: str,
    from_version_id: str = Query(..., description="Source version public id"),
    to_version_id: str = Query(..., description="Target version public id"),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[VersionComparisonResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.compare_versions(
        presentation_id,
        from_version_id,
        to_version_id,
    )
    return APIResponse(data=VersionComparisonResponse(**result))


@presentations_router.post(
    "/{presentation_id}/versions/{version_id}/restore",
    response_model=APIResponse[VersionResponse],
)
async def restore_version(
    presentation_id: str,
    version_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[VersionResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.restore_version(presentation_id, version_id)
    return APIResponse(
        data=VersionResponse(**result),
        message="Version restored successfully",
    )


@presentations_router.post(
    "/{presentation_id}/duplicate",
    response_model=APIResponse[PresentationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_presentation(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PresentationResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.duplicate_presentation(presentation_id, owner_id=user.id)
    return APIResponse(
        data=PresentationResponse(**result),
        message="Presentation duplicated successfully",
    )


@presentations_router.post(
    "/{presentation_id}/recover",
    response_model=APIResponse[PresentationResponse],
)
async def recover_presentation(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PresentationResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.recover_presentation(presentation_id)
    return APIResponse(
        data=PresentationResponse(**result),
        message="Presentation recovered successfully",
    )


@presentations_router.post(
    "/{presentation_id}/source",
    response_model=APIResponse[PresentationResponse],
)
async def upload_source(
    presentation_id: str,
    source: UploadFile = File(...),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[PresentationResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    content = await _read_upload_bounded(source)
    filename = source.filename or ""

    result = await service.set_source(
        presentation_id,
        content,
        filename=filename,
        content_type=source.content_type,
    )
    return APIResponse(
        data=PresentationResponse(**result),
        message="Source file uploaded successfully",
    )


@presentations_router.get(
    "/{presentation_id}/processing-status",
    response_model=APIResponse[ProcessingStatusResponse],
)
async def get_processing_status(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[ProcessingStatusResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.get_extraction_status(presentation_id)
    return APIResponse(data=ProcessingStatusResponse(**result))


@presentations_router.get(
    "/{presentation_id}/content",
    response_model=APIResponse[ContentListResponse],
)
async def get_content(
    presentation_id: str,
    include_blocks: bool = Query(True, description="Include content blocks"),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[ContentListResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.get_content(
        presentation_id,
        include_blocks=include_blocks,
    )
    return APIResponse(data=ContentListResponse(**result))


@presentations_router.get(
    "/{presentation_id}/topics",
    response_model=APIResponse[TopicOutlineOut],
)
async def get_topics(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[TopicOutlineOut]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.get_topics(presentation_id)
    return APIResponse(data=TopicOutlineOut(**result))


@presentations_router.post(
    "/{presentation_id}/topics/regenerate",
    response_model=APIResponse[TopicOutlineOut],
)
async def regenerate_topics(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[TopicOutlineOut]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.regenerate_topics(presentation_id)
    return APIResponse(data=TopicOutlineOut(**result))


@presentations_router.post(
    "/{presentation_id}/thumbnail",
    response_model=APIResponse[ThumbnailResponse],
)
async def upload_thumbnail(
    presentation_id: str,
    thumbnail: UploadFile = File(...),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[ThumbnailResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    content = await _read_upload_bounded(thumbnail)
    result = await service.set_thumbnail(
        presentation_id,
        content,
        content_type=thumbnail.content_type,
        filename=thumbnail.filename,
    )
    return APIResponse(
        data=ThumbnailResponse(**result),
        message="Thumbnail uploaded successfully",
    )


@presentations_router.delete(
    "/{presentation_id}/thumbnail",
    response_model=APIResponse[ThumbnailResponse],
)
async def delete_thumbnail(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[ThumbnailResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.delete_thumbnail(presentation_id)
    return APIResponse(
        data=ThumbnailResponse(**result),
        message="Thumbnail deleted successfully",
    )


@presentations_router.post(
    "/{presentation_id}/thumbnail/regenerate",
    response_model=APIResponse[ThumbnailRegenerateResponse],
)
async def regenerate_thumbnail(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[ThumbnailRegenerateResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.regenerate_thumbnail(presentation_id)
    return APIResponse(
        data=ThumbnailRegenerateResponse(**result),
        message="Thumbnail regeneration scheduled",
    )


@presentations_router.get(
    "/{presentation_id}/analytics",
    response_model=APIResponse[AnalyticsResponse],
)
async def get_analytics(
    presentation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AnalyticsResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.get_analytics(presentation_id)
    return APIResponse(data=AnalyticsResponse(**result) if result else None)


@presentations_router.get(
    "/{presentation_id}/audit-logs",
    response_model=APIResponse[list[AuditLogResponse]],
)
async def list_audit_logs(
    presentation_id: str,
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[list[AuditLogResponse]]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    logs = await service.list_audit_logs(presentation_id, limit=limit)
    return APIResponse(data=[AuditLogResponse(**log) for log in logs])


# ── AI lesson generation ─────────────────────────────────────────────────────


@presentations_router.post(
    "/{presentation_id}/lessons",
    response_model=APIResponse[GeneratedLessonResponse],
    status_code=status.HTTP_201_CREATED,
)
async def generate_lesson(
    presentation_id: str,
    request: LessonGenerationRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=128),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[GeneratedLessonResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.generate_lesson(
        presentation_id,
        request,
        idempotency_key=idempotency_key,
    )
    message = (
        "Lesson generation resumed" if result.get("duplicate") else "Lesson generation started"
    )
    return APIResponse(data=GeneratedLessonResponse(**result), message=message)


@presentations_router.get(
    "/{presentation_id}/lessons",
    response_model=PaginatedResponse[GeneratedLessonSummary],
)
async def list_generated_lessons(
    presentation_id: str,
    mode: str | None = Query(None, max_length=20),
    status: str | None = Query(None, max_length=20),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PaginatedResponse[GeneratedLessonSummary]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    items, total = await service.list_generated_lessons(
        presentation_id,
        page=page,
        page_size=page_size,
        mode=mode,
        status=status,
    )
    return PaginatedResponse(
        data=[GeneratedLessonSummary(**item) for item in items],
        pagination=PaginationMeta(**create_page_meta(page, page_size, total)),
    )


@presentations_router.get(
    "/{presentation_id}/lessons/{lesson_id}",
    response_model=APIResponse[GeneratedLessonResponse],
)
async def get_generated_lesson(
    presentation_id: str,
    lesson_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[GeneratedLessonResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.get_generated_lesson(presentation_id, lesson_id)
    return APIResponse(data=GeneratedLessonResponse(**result))


@presentations_router.get(
    "/{presentation_id}/lessons/{lesson_id}/status",
    response_model=APIResponse[GeneratedLessonStatusResponse],
)
async def get_generated_lesson_status(
    presentation_id: str,
    lesson_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[GeneratedLessonStatusResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.get_generated_lesson_status(presentation_id, lesson_id)
    return APIResponse(data=GeneratedLessonStatusResponse(**result))


@presentations_router.get(
    "/{presentation_id}/lessons/{lesson_id}/versions",
    response_model=APIResponse[list[GeneratedVersionResponse]],
)
async def list_generated_lesson_versions(
    presentation_id: str,
    lesson_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[list[GeneratedVersionResponse]]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    versions = await service.list_generated_lesson_versions(
        presentation_id, lesson_id
    )
    return APIResponse(data=[GeneratedVersionResponse(**version) for version in versions])


@presentations_router.get(
    "/{presentation_id}/lessons/{lesson_id}/versions/{version_id}",
    response_model=APIResponse[GeneratedVersionDetailResponse],
)
async def get_generated_lesson_version(
    presentation_id: str,
    lesson_id: str,
    version_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[GeneratedVersionDetailResponse]:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    result = await service.get_generated_lesson_version(
        presentation_id, lesson_id, version_id
    )
    return APIResponse(data=GeneratedVersionDetailResponse(**result))


@presentations_router.delete(
    "/{presentation_id}/lessons/{lesson_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_generated_lesson(
    presentation_id: str,
    lesson_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> Response:
    service = PresentationService(uow)
    await service.assert_ownership(presentation_id, user.id)
    await service.delete_generated_lesson(presentation_id, lesson_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

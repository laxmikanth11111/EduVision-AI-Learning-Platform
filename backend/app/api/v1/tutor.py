"""Mastery-Aware AI Tutor endpoints (P8).

All endpoints require authentication and are scoped to the authenticated
user. ``user_id`` always comes from ``get_current_user`` — never from the
client. Ownership is server-verified for lessons, presentations and target
concepts before any tutor state is created or read.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError, ValidationError
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.common import APIResponse, PaginatedResponse, PaginationMeta
from app.schemas.tutor import (
    TutorExchangeResponse,
    TutorMessageResponse,
    TutorMessageSendRequest,
    TutorRemediateRequest,
    TutorRemediateResponse,
    TutorSessionCreateRequest,
    TutorSessionResponse,
)
from app.services.mastery_tutor_service import MasteryTutorService

tutor_router = APIRouter(prefix="/tutor", tags=["Mastery Tutor"])


@tutor_router.post(
    "/sessions",
    response_model=APIResponse[TutorSessionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    request: TutorSessionCreateRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[TutorSessionResponse]:
    try:
        result = await MasteryTutorService(uow).create_session(user.id, request)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)
    return APIResponse(data=TutorSessionResponse(**result), message="Tutor session created")


@tutor_router.get(
    "/sessions",
    response_model=PaginatedResponse[TutorSessionResponse],
)
async def list_sessions(
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PaginatedResponse[TutorSessionResponse]:
    items, total = await MasteryTutorService(uow).list_sessions(
        user.id, page=page, page_size=page_size
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(
        data=[TutorSessionResponse(**i) for i in items],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


@tutor_router.get(
    "/sessions/{session_id}",
    response_model=APIResponse[TutorSessionResponse],
)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[TutorSessionResponse]:
    try:
        result = await MasteryTutorService(uow).get_session(user.id, session_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    return APIResponse(data=TutorSessionResponse(**result))


@tutor_router.post(
    "/sessions/{session_id}/messages",
    response_model=APIResponse[TutorExchangeResponse],
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    session_id: str,
    request: TutorMessageSendRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[TutorExchangeResponse]:
    try:
        result = await MasteryTutorService(uow).send_message(user.id, session_id, request)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)
    return APIResponse(data=TutorExchangeResponse(**result), message="Message sent")


@tutor_router.get(
    "/sessions/{session_id}/messages",
    response_model=PaginatedResponse[TutorMessageResponse],
)
async def list_session_messages(
    session_id: str,
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PaginatedResponse[TutorMessageResponse]:
    """Tutor history for a session, addressed by the session's own public id.

    Mirrors the POST above so the frontend can load history with the ``tus_``
    session id it already holds, instead of a ``tuc_`` conversation id it never
    has.
    """
    try:
        items, total = await MasteryTutorService(uow).list_session_messages(
            user.id, session_id, page=page, page_size=page_size
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(
        data=[TutorMessageResponse(**i) for i in items],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


@tutor_router.get(
    "/conversations/{conversation_id}/messages",
    response_model=PaginatedResponse[TutorMessageResponse],
)
async def list_messages(
    conversation_id: str,
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PaginatedResponse[TutorMessageResponse]:
    try:
        items, total = await MasteryTutorService(uow).list_messages(
            user.id, conversation_id, page=page, page_size=page_size
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(
        data=[TutorMessageResponse(**i) for i in items],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


@tutor_router.post(
    "/remediate",
    response_model=APIResponse[TutorRemediateResponse],
    status_code=status.HTTP_201_CREATED,
)
async def remediate(
    request: TutorRemediateRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[TutorRemediateResponse]:
    try:
        result = await MasteryTutorService(uow).remediate(user.id, request)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)
    return APIResponse(data=TutorRemediateResponse(**result), message="Remediation generated")

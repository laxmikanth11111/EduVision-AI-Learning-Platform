"""AI learning assistant endpoints (Phase 4D.6).

Provides session management, conversation lifecycle, message exchange,
and conversation summarization. All endpoints require authentication
and are scoped to the authenticated user.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError, ValidationError
from app.database.unit_of_work import UnitOfWork, get_unit_of_work
from app.models.user import User
from app.schemas.assistant import (
    AssistantConversationResponse,
    AssistantExchangeResponse,
    AssistantMessageResponse,
    AssistantSessionResponse,
    AssistantSummaryResponse,
    ConversationCreateRequest,
    MessageSendRequest,
    SessionCreateRequest,
)
from app.schemas.common import APIResponse, PaginatedResponse, PaginationMeta
from app.services.learning_assistant_service import LearningAssistantService

assistant_router = APIRouter(prefix="/assistant", tags=["AI Assistant"])


# ── Sessions ────────────────────────────────────────────────────────────────


@assistant_router.post(
    "/sessions",
    response_model=APIResponse[AssistantSessionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    request: SessionCreateRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AssistantSessionResponse]:
    try:
        result = await LearningAssistantService(uow).create_session(user.id, request)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)
    return APIResponse(data=AssistantSessionResponse(**result), message="Session created")


@assistant_router.get(
    "/sessions",
    response_model=PaginatedResponse[AssistantSessionResponse],
)
async def list_sessions(
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PaginatedResponse[AssistantSessionResponse]:
    items, total = await LearningAssistantService(uow).list_sessions(
        user.id, page=page, page_size=page_size
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(
        data=[AssistantSessionResponse(**i) for i in items],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


@assistant_router.get(
    "/sessions/{session_id}",
    response_model=APIResponse[AssistantSessionResponse],
)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AssistantSessionResponse]:
    try:
        result = await LearningAssistantService(uow).get_session(user.id, session_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    return APIResponse(data=AssistantSessionResponse(**result))


@assistant_router.post(
    "/sessions/{session_id}/close",
    response_model=APIResponse[AssistantSessionResponse],
)
async def close_session(
    session_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AssistantSessionResponse]:
    try:
        result = await LearningAssistantService(uow).close_session(user.id, session_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    return APIResponse(data=AssistantSessionResponse(**result), message="Session closed")


# ── Conversations ───────────────────────────────────────────────────────────


@assistant_router.post(
    "/conversations",
    response_model=APIResponse[AssistantConversationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    request: ConversationCreateRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AssistantConversationResponse]:
    try:
        result = await LearningAssistantService(uow).create_conversation(user.id, request)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)
    return APIResponse(data=AssistantConversationResponse(**result), message="Conversation created")


@assistant_router.get(
    "/conversations",
    response_model=PaginatedResponse[AssistantConversationResponse],
)
async def list_conversations(
    user: User = Depends(get_current_user),
    session_id: str | None = Query(None, max_length=40),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PaginatedResponse[AssistantConversationResponse]:
    items, total = await LearningAssistantService(uow).list_conversations(
        user.id, session_id=session_id, page=page, page_size=page_size
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(
        data=[AssistantConversationResponse(**i) for i in items],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


@assistant_router.get(
    "/conversations/{conversation_id}",
    response_model=APIResponse[AssistantConversationResponse],
)
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AssistantConversationResponse]:
    try:
        result = await LearningAssistantService(uow).get_conversation(user.id, conversation_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    return APIResponse(data=AssistantConversationResponse(**result))


# ── Messages ────────────────────────────────────────────────────────────────


@assistant_router.post(
    "/conversations/{conversation_id}/messages",
    response_model=APIResponse[AssistantExchangeResponse],
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: str,
    request: MessageSendRequest,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AssistantExchangeResponse]:
    try:
        result = await LearningAssistantService(uow).send_message(
            user.id, conversation_id, request
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)
    return APIResponse(data=AssistantExchangeResponse(**result), message="Message sent")


@assistant_router.get(
    "/conversations/{conversation_id}/messages",
    response_model=PaginatedResponse[AssistantMessageResponse],
)
async def list_messages(
    conversation_id: str,
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PaginatedResponse[AssistantMessageResponse]:
    try:
        items, total = await LearningAssistantService(uow).list_messages(
            user.id, conversation_id, page=page, page_size=page_size
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(
        data=[AssistantMessageResponse(**i) for i in items],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )


# ── Summaries ───────────────────────────────────────────────────────────────


@assistant_router.post(
    "/conversations/{conversation_id}/summarize",
    response_model=APIResponse[AssistantSummaryResponse],
)
async def summarize_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> APIResponse[AssistantSummaryResponse]:
    try:
        result = await LearningAssistantService(uow).summarize_conversation(
            user.id, conversation_id
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    return APIResponse(data=AssistantSummaryResponse(**result), message="Summary generated")

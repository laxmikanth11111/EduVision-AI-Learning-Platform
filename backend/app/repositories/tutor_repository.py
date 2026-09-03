from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.database.repository import BaseRepository
from app.models.tutor_conversation import TutorConversation
from app.models.tutor_message import TutorMessage
from app.models.tutor_session import TutorSession
from shared.constants import TutorConversationStatus, TutorSessionStatus


def _session_graph() -> list[Any]:
    return [selectinload(TutorSession.lesson)]


class TutorSessionRepository(BaseRepository[TutorSession]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TutorSession)

    async def get_for_user(
        self, user_id: uuid.UUID, public_id: str
    ) -> TutorSession | None:
        stmt = (
            select(TutorSession)
            .options(*_session_graph())
            .where(
                TutorSession.user_id == user_id,
                TutorSession.public_id == public_id,
                TutorSession.deleted_at.is_(None),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_user_or_raise(
        self, user_id: uuid.UUID, public_id: str
    ) -> TutorSession:
        session = await self.get_for_user(user_id, public_id)
        if session is None:
            raise NotFoundError(
                message="Tutor session not found",
                details={"session_id": public_id},
            )
        return session

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[TutorSession], int]:
        filters = [
            TutorSession.user_id == user_id,
            TutorSession.deleted_at.is_(None),
        ]
        count_stmt = select(func.count()).select_from(TutorSession).where(*filters)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            select(TutorSession)
            .options(*_session_graph())
            .where(*filters)
            .order_by(
                TutorSession.last_message_at.desc().nullslast(),
                TutorSession.updated_at.desc(),
                TutorSession.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def create_for_user(
        self,
        user_id: uuid.UUID,
        *,
        title: str = "AI Tutor",
        lesson_id: uuid.UUID | None = None,
        lesson_public_id: str | None = None,
        presentation_id: uuid.UUID | None = None,
        target_concept_id: str | None = None,
        mode: str = "interactive",
        difficulty: str | None = None,
        language: str | None = None,
        context_version: str = "1",
    ) -> TutorSession:
        return await self.create(
            user_id=user_id,
            title=title,
            lesson_id=lesson_id,
            lesson_public_id=lesson_public_id,
            presentation_id=presentation_id,
            target_concept_id=target_concept_id,
            mode=mode,
            difficulty=difficulty,
            language=language,
            context_version=context_version,
        )

    async def touch(
        self, session: TutorSession, last_message_at: datetime | None = None
    ) -> TutorSession:
        session.last_message_at = last_message_at or datetime.now()
        await self._session.flush()
        await self._session.refresh(session)
        return session

    async def archive(self, session: TutorSession) -> TutorSession:
        session.status = TutorSessionStatus.ARCHIVED.value
        await self._session.flush()
        await self._session.refresh(session)
        return session


class TutorConversationRepository(BaseRepository[TutorConversation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TutorConversation)

    async def get_for_user(
        self, user_id: uuid.UUID, public_id: str
    ) -> TutorConversation | None:
        stmt = (
            select(TutorConversation)
            .where(
                TutorConversation.user_id == user_id,
                TutorConversation.public_id == public_id,
                TutorConversation.deleted_at.is_(None),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_user_or_raise(
        self, user_id: uuid.UUID, public_id: str
    ) -> TutorConversation:
        conversation = await self.get_for_user(user_id, public_id)
        if conversation is None:
            raise NotFoundError(
                message="Tutor conversation not found",
                details={"conversation_id": public_id},
            )
        return conversation

    async def latest_for_session(
        self, session_id: uuid.UUID
    ) -> TutorConversation | None:
        stmt = (
            select(TutorConversation)
            .where(
                TutorConversation.session_id == session_id,
                TutorConversation.status == TutorConversationStatus.ACTIVE.value,
                TutorConversation.deleted_at.is_(None),
            )
            .order_by(TutorConversation.updated_at.desc(), TutorConversation.id)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def touch(
        self, conversation: TutorConversation, last_message_at: datetime | None = None
    ) -> TutorConversation:
        conversation.last_message_at = last_message_at or datetime.now()
        count_stmt = (
            select(func.count())
            .select_from(TutorMessage)
            .where(TutorMessage.conversation_id == conversation.id)
        )
        result = await self._session.execute(count_stmt)
        conversation.message_count = int(result.scalar_one() or 0)
        await self._session.flush()
        await self._session.refresh(conversation)
        return conversation


class TutorMessageRepository(BaseRepository[TutorMessage]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, TutorMessage)

    async def recent_for_conversation(
        self, conversation_id: uuid.UUID, limit: int = 50
    ) -> list[TutorMessage]:
        stmt = (
            select(TutorMessage)
            .where(TutorMessage.conversation_id == conversation_id)
            .order_by(TutorMessage.created_at.desc(), TutorMessage.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(reversed(result.scalars().all()))

    async def create_user_message(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        client_message_id: str | None = None,
    ) -> TutorMessage:
        return await self.create(
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=content,
            client_message_id=client_message_id,
            status="completed",
        )

    async def create_assistant_message(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        *,
        source_kind: str | None = None,
        attribution: str | None = None,
        confidence: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: int = 0,
        retrieval_metadata: dict[str, object] | None = None,
        answer_metadata: dict[str, object] | None = None,
    ) -> TutorMessage:
        return await self.create(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=content,
            status="completed",
            model=model,
            provider=provider,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            retrieval_metadata=retrieval_metadata,
            answer_metadata=answer_metadata,
            source_kind=source_kind,
            attribution=attribution,
            confidence=confidence,
        )

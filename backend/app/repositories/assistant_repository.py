from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.database.repository import BaseRepository
from app.models.assistant_context_snapshot import AssistantContextSnapshot
from app.models.assistant_conversation import AssistantConversation
from app.models.assistant_message import AssistantMessage
from app.models.assistant_session import AssistantSession
from shared.constants import AssistantSessionStatus


def _session_graph() -> list[Any]:
    return [selectinload(AssistantSession.lesson)]


class AssistantSessionRepository(BaseRepository[AssistantSession]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AssistantSession)

    async def get_for_user(self, user_id: uuid.UUID, public_id: str) -> AssistantSession | None:
        stmt = (
            select(AssistantSession)
            .options(*_session_graph())
            .where(
                AssistantSession.user_id == user_id,
                AssistantSession.public_id == public_id,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_user_or_raise(self, user_id: uuid.UUID, public_id: str) -> AssistantSession:
        session = await self.get_for_user(user_id, public_id)
        if session is None:
            raise NotFoundError(
                message="Assistant session not found",
                details={"session_id": public_id},
            )
        return session

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AssistantSession], int]:
        filters = [AssistantSession.user_id == user_id]
        count_stmt = select(func.count()).select_from(AssistantSession).where(*filters)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            select(AssistantSession)
            .options(*_session_graph())
            .where(*filters)
            .order_by(
                AssistantSession.last_message_at.desc().nullslast(),
                AssistantSession.updated_at.desc(),
                AssistantSession.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def list_active_for_lesson(
        self, user_id: uuid.UUID, lesson_id: uuid.UUID
    ) -> list[AssistantSession]:
        stmt = (
            select(AssistantSession)
            .where(
                AssistantSession.user_id == user_id,
                AssistantSession.lesson_id == lesson_id,
                AssistantSession.status == AssistantSessionStatus.ACTIVE.value,
            )
            .order_by(AssistantSession.updated_at.desc(), AssistantSession.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_for_user(
        self,
        user_id: uuid.UUID,
        title: str = "AI Assistant",
        lesson_id: uuid.UUID | None = None,
        session_public_id: str | None = None,
        slide_position: int = 0,
        block_position: int = 0,
        context_version: str = "1",
    ) -> AssistantSession:
        return await self.create(
            user_id=user_id,
            lesson_id=lesson_id,
            session_public_id=session_public_id,
            title=title,
            slide_position=slide_position,
            block_position=block_position,
            context_version=context_version,
        )

    async def touch(
        self, session: AssistantSession, last_message_at: datetime | None = None
    ) -> AssistantSession:
        session.last_message_at = last_message_at or datetime.now()
        await self._session.flush()
        await self._session.refresh(session)
        return session

    async def close(self, session: AssistantSession) -> AssistantSession:
        session.status = AssistantSessionStatus.ARCHIVED.value
        await self._session.flush()
        await self._session.refresh(session)
        return session


class AssistantConversationRepository(BaseRepository[AssistantConversation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AssistantConversation)

    async def get_for_user(
        self, user_id: uuid.UUID, public_id: str
    ) -> AssistantConversation | None:
        stmt = (
            select(AssistantConversation)
            .where(
                AssistantConversation.user_id == user_id,
                AssistantConversation.public_id == public_id,
                AssistantConversation.deleted_at.is_(None),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_user_or_raise(
        self, user_id: uuid.UUID, public_id: str
    ) -> AssistantConversation:
        conversation = await self.get_for_user(user_id, public_id)
        if conversation is None:
            raise NotFoundError(
                message="Assistant conversation not found",
                details={"conversation_id": public_id},
            )
        return conversation

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AssistantConversation], int]:
        filters = [
            AssistantConversation.user_id == user_id,
            AssistantConversation.deleted_at.is_(None),
        ]
        if session_id is not None:
            filters.append(AssistantConversation.session_id == session_id)
        count_stmt = select(func.count()).select_from(AssistantConversation).where(*filters)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            select(AssistantConversation)
            .where(*filters)
            .order_by(
                AssistantConversation.last_message_at.desc().nullslast(),
                AssistantConversation.updated_at.desc(),
                AssistantConversation.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def create_for_user(
        self,
        user_id: uuid.UUID,
        title: str | None = None,
        session_id: uuid.UUID | None = None,
        session_public_id: str | None = None,
        lesson_id: uuid.UUID | None = None,
        lesson_public_id: str | None = None,
        slide_position: int = 0,
        block_position: int = 0,
        context_version: str = "1",
    ) -> AssistantConversation:
        return await self.create(
            user_id=user_id,
            session_id=session_id,
            session_public_id=session_public_id,
            lesson_id=lesson_id,
            lesson_public_id=lesson_public_id,
            title=title,
            slide_position=slide_position,
            block_position=block_position,
            context_version=context_version,
        )

    async def update_summary(
        self, conversation: AssistantConversation, summary: str
    ) -> AssistantConversation:
        conversation.summary = summary
        conversation.summary_created_at = datetime.now()
        await self._session.flush()
        await self._session.refresh(conversation)
        return conversation

    async def touch(
        self, conversation: AssistantConversation, last_message_at: datetime | None = None
    ) -> AssistantConversation:
        conversation.last_message_at = last_message_at or datetime.now()
        count_stmt = (
            select(func.count())
            .select_from(AssistantMessage)
            .where(AssistantMessage.conversation_id == conversation.id)
        )
        result = await self._session.execute(count_stmt)
        conversation.message_count = int(result.scalar_one() or 0)
        await self._session.flush()
        await self._session.refresh(conversation)
        return conversation

    async def list_unsummarized(
        self,
        min_messages: int,
        limit: int = 50,
    ) -> list[AssistantConversation]:
        stmt = (
            select(AssistantConversation)
            .where(
                AssistantConversation.deleted_at.is_(None),
                AssistantConversation.summary.is_(None),
                AssistantConversation.message_count >= min_messages,
            )
            .order_by(AssistantConversation.last_message_at.asc(), AssistantConversation.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class AssistantMessageRepository(BaseRepository[AssistantMessage]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AssistantMessage)

    async def get_for_conversation(
        self, conversation_id: uuid.UUID, public_id: str
    ) -> AssistantMessage | None:
        stmt = (
            select(AssistantMessage)
            .where(
                AssistantMessage.conversation_id == conversation_id,
                AssistantMessage.public_id == public_id,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_conversation_or_raise(
        self, conversation_id: uuid.UUID, public_id: str
    ) -> AssistantMessage:
        message = await self.get_for_conversation(conversation_id, public_id)
        if message is None:
            raise NotFoundError(
                message="Assistant message not found",
                details={"message_id": public_id},
            )
        return message

    async def list_for_conversation(
        self,
        conversation_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AssistantMessage], int]:
        filters = [AssistantMessage.conversation_id == conversation_id]
        count_stmt = select(func.count()).select_from(AssistantMessage).where(*filters)
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = (
            select(AssistantMessage)
            .where(*filters)
            .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def recent_for_conversation(
        self, conversation_id: uuid.UUID, limit: int = 50
    ) -> list[AssistantMessage]:
        stmt = (
            select(AssistantMessage)
            .where(AssistantMessage.conversation_id == conversation_id)
            .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(reversed(result.scalars().all()))

    async def find_by_client_message_id(
        self, conversation_id: uuid.UUID, client_message_id: str
    ) -> AssistantMessage | None:
        stmt = (
            select(AssistantMessage)
            .where(
                AssistantMessage.conversation_id == conversation_id,
                AssistantMessage.client_message_id == client_message_id,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user_message(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        client_message_id: str | None = None,
    ) -> AssistantMessage:
        return await self.create(
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=content,
            client_message_id=client_message_id,
        )

    async def create_assistant_message(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        model: str | None = None,
        provider: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: int = 0,
        message_metadata: dict[str, object] | None = None,
    ) -> AssistantMessage:
        return await self.create(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=content,
            model=model,
            provider=provider,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            message_metadata=message_metadata,
        )

    async def mark_failed(self, message: AssistantMessage, error: str) -> AssistantMessage:
        message.status = "failed"
        message.error = error[:500]
        await self._session.flush()
        await self._session.refresh(message)
        return message


class AssistantContextSnapshotRepository(BaseRepository[AssistantContextSnapshot]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AssistantContextSnapshot)

    async def list_for_conversation(
        self,
        conversation_id: uuid.UUID,
        limit: int = 20,
    ) -> list[AssistantContextSnapshot]:
        stmt = (
            select(AssistantContextSnapshot)
            .where(AssistantContextSnapshot.conversation_id == conversation_id)
            .order_by(AssistantContextSnapshot.created_at.desc(), AssistantContextSnapshot.id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_conversation(
        self, conversation_id: uuid.UUID
    ) -> AssistantContextSnapshot | None:
        stmt = (
            select(AssistantContextSnapshot)
            .where(AssistantContextSnapshot.conversation_id == conversation_id)
            .order_by(AssistantContextSnapshot.created_at.desc(), AssistantContextSnapshot.id)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_for_conversation(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        context: dict[str, Any],
        lesson_id: uuid.UUID | None = None,
        lesson_public_id: str | None = None,
        session_public_id: str | None = None,
        slide_position: int = 0,
        block_position: int = 0,
        context_version: str = "1",
        prompt_hash: str | None = None,
    ) -> AssistantContextSnapshot:
        return await self.create(
            conversation_id=conversation_id,
            user_id=user_id,
            lesson_id=lesson_id,
            lesson_public_id=lesson_public_id,
            session_public_id=session_public_id,
            slide_position=slide_position,
            block_position=block_position,
            context_version=context_version,
            prompt_hash=prompt_hash,
            context=context,
        )

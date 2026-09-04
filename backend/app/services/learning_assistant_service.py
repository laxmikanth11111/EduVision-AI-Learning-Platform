"""AI learning assistant service (Phase 4D.6).

Orchestrates sessions, conversations, messages and context snapshots.
Persists all learning memory to the database. When an AI provider is
configured the service calls it; otherwise it returns a graceful fallback
so the full request/response cycle can be exercised end-to-end.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.retrieval import cosine_similarity
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.database.unit_of_work import UnitOfWork
from app.models.assistant_conversation import AssistantConversation
from app.models.assistant_message import AssistantMessage
from app.models.assistant_session import AssistantSession
from app.models.generated_lesson import GeneratedLesson
from app.repositories.assistant_repository import (
    AssistantContextSnapshotRepository,
    AssistantConversationRepository,
    AssistantMessageRepository,
    AssistantSessionRepository,
)
from app.schemas.assistant import (
    ConversationCreateRequest,
    MessageSendRequest,
    SessionCreateRequest,
)
from app.services.assistant_prompt_builder import AssistantPromptBuilder
from shared.constants import (
    AssistantMessageStatus,
)


def _serialize_session(s: AssistantSession) -> dict[str, Any]:
    return {
        "id": s.public_id,
        "lesson_id": None,
        "title": s.title,
        "status": s.status,
        "slide_position": s.slide_position,
        "block_position": s.block_position,
        "context_version": s.context_version,
        "last_message_at": s.last_message_at,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def _serialize_conversation(c: AssistantConversation) -> dict[str, Any]:
    return {
        "id": c.public_id,
        "session_id": None,
        "lesson_id": None,
        "title": c.title,
        "status": c.status,
        "slide_position": c.slide_position,
        "block_position": c.block_position,
        "context_version": c.context_version,
        "message_count": c.message_count,
        "summary": c.summary,
        "summary_created_at": c.summary_created_at,
        "last_message_at": c.last_message_at,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def _serialize_message(m: AssistantMessage) -> dict[str, Any]:
    return {
        "id": m.public_id,
        "role": m.role,
        "content": m.content,
        "status": m.status,
        "client_message_id": m.client_message_id,
        "model": m.model,
        "provider": m.provider,
        "tokens_in": m.tokens_in,
        "tokens_out": m.tokens_out,
        "latency_ms": m.latency_ms,
        "error": m.error,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


def _serialize_exchange(
    user_msg: AssistantMessage | None,
    assistant_msg: AssistantMessage | None,
    prompt_hash: str | None = None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    return {
        "user_message": _serialize_message(user_msg) if user_msg else None,
        "assistant_message": _serialize_message(assistant_msg) if assistant_msg else None,
        "prompt_hash": prompt_hash,
        "conversation_id": conversation_id,
    }


class LearningAssistantService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._prompt_builder = AssistantPromptBuilder()

    @property
    def _session_repo(self) -> AssistantSessionRepository:
        return AssistantSessionRepository(self._uow.session)

    @property
    def _conversation_repo(self) -> AssistantConversationRepository:
        return AssistantConversationRepository(self._uow.session)

    @property
    def _message_repo(self) -> AssistantMessageRepository:
        return AssistantMessageRepository(self._uow.session)

    @property
    def _context_repo(self) -> AssistantContextSnapshotRepository:
        return AssistantContextSnapshotRepository(self._uow.session)

    # ── Sessions ────────────────────────────────────────────────────────────

    async def create_session(
        self,
        user_id: uuid.UUID,
        request: SessionCreateRequest,
    ) -> dict[str, Any]:
        lesson_id = await self._resolve_lesson_id(request.lesson_id)
        session = await self._session_repo.create_for_user(
            user_id=user_id,
            title=request.title,
            lesson_id=lesson_id,
            slide_position=request.slide_position,
            block_position=request.block_position,
        )
        await self._uow.flush()
        return _serialize_session(session)

    async def get_session(
        self,
        user_id: uuid.UUID,
        session_public_id: str,
    ) -> dict[str, Any]:
        session = await self._session_repo.get_for_user_or_raise(user_id, session_public_id)
        return _serialize_session(session)

    async def list_sessions(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        items, total = await self._session_repo.list_for_user(user_id, page, page_size)
        return [_serialize_session(s) for s in items], total

    async def close_session(
        self,
        user_id: uuid.UUID,
        session_public_id: str,
    ) -> dict[str, Any]:
        session = await self._session_repo.get_for_user_or_raise(user_id, session_public_id)
        session = await self._session_repo.close(session)
        return _serialize_session(session)

    # ── Conversations ───────────────────────────────────────────────────────

    async def create_conversation(
        self,
        user_id: uuid.UUID,
        request: ConversationCreateRequest,
    ) -> dict[str, Any]:
        session_id = None
        session_public_id = None
        if request.session_id:
            sess = await self._session_repo.get_for_user(user_id, request.session_id)
            if sess is None:
                raise NotFoundError(
                    message="Session not found",
                    details={"session_id": request.session_id},
                )
            session_id = sess.id
            session_public_id = sess.public_id

        lesson_id = await self._resolve_lesson_id(request.lesson_id)
        conversation = await self._conversation_repo.create_for_user(
            user_id=user_id,
            title=request.title,
            session_id=session_id,
            session_public_id=session_public_id,
            lesson_id=lesson_id,
            slide_position=request.slide_position or 0,
            block_position=request.block_position or 0,
        )
        await self._uow.flush()
        return _serialize_conversation(conversation)

    async def get_conversation(
        self,
        user_id: uuid.UUID,
        conversation_public_id: str,
    ) -> dict[str, Any]:
        conv = await self._conversation_repo.get_for_user_or_raise(user_id, conversation_public_id)
        return _serialize_conversation(conv)

    async def list_conversations(
        self,
        user_id: uuid.UUID,
        session_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        resolved_session_id = None
        if session_id:
            sess = await self._session_repo.get_for_user(user_id, session_id)
            if sess:
                resolved_session_id = sess.id
        items, total = await self._conversation_repo.list_for_user(
            user_id, session_id=resolved_session_id, page=page, page_size=page_size
        )
        return [_serialize_conversation(c) for c in items], total

    # ── Messages ────────────────────────────────────────────────────────────

    async def send_message(
        self,
        user_id: uuid.UUID,
        conversation_public_id: str,
        request: MessageSendRequest,
    ) -> dict[str, Any]:
        conv = await self._conversation_repo.get_for_user_or_raise(user_id, conversation_public_id)

        # Idempotency: check for existing client_message_id
        if request.client_message_id:
            existing = await self._message_repo.find_by_client_message_id(
                conv.id, request.client_message_id
            )
            if existing:
                # Find the assistant reply to this user message
                msgs, _ = await self._message_repo.list_for_conversation(conv.id, page_size=100)
                assistant_reply = None
                found_user = False
                for m in msgs:
                    if m.id == existing.id:
                        found_user = True
                    elif found_user and m.role == "assistant":
                        assistant_reply = m
                        break
                return _serialize_exchange(existing, assistant_reply, conversation_id=conv.public_id)

        # Persist user message
        user_msg = await self._message_repo.create_user_message(
            conversation_id=conv.id,
            user_id=user_id,
            content=request.content,
            client_message_id=request.client_message_id,
        )
        await self._uow.flush()

        # Build context for AI
        context_text = await self._build_context_text(conv)
        history = await self._load_history(conv.id)

        # Snapshot context
        prompt_hash = self._prompt_builder.prompt_hash(
            context_text=context_text,
            history_count=len(history),
            user_message=request.content,
        )
        await self._context_repo.create_for_conversation(
            conversation_id=conv.id,
            user_id=user_id,
            context={
                "lesson_id": str(conv.lesson_id) if conv.lesson_id else None,
                "slide_position": conv.slide_position,
                "block_position": conv.block_position,
                "context_version": conv.context_version,
            },
            lesson_id=conv.lesson_id,
            prompt_hash=prompt_hash,
        )

        # Attempt AI generation (fallback to echo if no provider)
        start = time.monotonic()
        assistant_content = await self._generate_response(
            context_text=context_text,
            history=history,
            user_message=request.content,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        # Persist assistant message
        assistant_msg = await self._message_repo.create_assistant_message(
            conversation_id=conv.id,
            user_id=user_id,
            content=assistant_content,
            tokens_in=len(request.content.split()),
            tokens_out=len(assistant_content.split()),
            latency_ms=latency_ms,
        )
        await self._uow.flush()

        # Touch conversation and session timestamps
        await self._conversation_repo.touch(conv)
        if conv.session_id:
            sess = await self._session_repo.get_for_user(user_id, conv.session_public_id or "")
            if sess:
                await self._session_repo.touch(sess)

        return _serialize_exchange(
            user_msg, assistant_msg,
            prompt_hash=prompt_hash,
            conversation_id=conv.public_id,
        )

    async def list_messages(
        self,
        user_id: uuid.UUID,
        conversation_public_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        conv = await self._conversation_repo.get_for_user_or_raise(user_id, conversation_public_id)
        items, total = await self._message_repo.list_for_conversation(
            conv.id, page=page, page_size=page_size
        )
        return [_serialize_message(m) for m in items], total

    # ── Summaries ───────────────────────────────────────────────────────────

    async def summarize_conversation(
        self,
        user_id: uuid.UUID,
        conversation_public_id: str,
    ) -> dict[str, Any]:
        conv = await self._conversation_repo.get_for_user_or_raise(user_id, conversation_public_id)

        # Gather messages for summary
        msgs, _ = await self._message_repo.list_for_conversation(conv.id, page_size=100)
        if not msgs:
            return {
                "conversation_id": conv.public_id,
                "summary": None,
                "dispatched": False,
            }

        # Build a simple extractive summary from conversation
        user_msgs = [m for m in msgs if m.role == "user"]
        topics = [m.content[:100] for m in user_msgs[:5]]
        summary = f"Discussion covering: {'; '.join(topics)}"

        await self._conversation_repo.update_summary(conv, summary)
        return {
            "conversation_id": conv.public_id,
            "summary": summary,
            "dispatched": False,
        }

    # ── Internal helpers ────────────────────────────────────────────────────

    async def _resolve_lesson_id(self, lesson_public_id: str | None) -> uuid.UUID | None:
        if not lesson_public_id:
            return None
        stmt = select(GeneratedLesson).where(GeneratedLesson.public_id == lesson_public_id)
        result = await self._uow.session.execute(stmt)
        lesson = result.scalar_one_or_none()
        return lesson.id if lesson else None

    async def _build_context_text(self, conv: AssistantConversation) -> str:
        parts = []
        if conv.lesson_id:
            stmt = (
                select(GeneratedLesson)
                .where(GeneratedLesson.id == conv.lesson_id)
            )
            result = await self._uow.session.execute(stmt)
            lesson = result.scalar_one_or_none()
            if lesson:
                parts.append(f"Lesson: {lesson.title}")
                parts.append(f"Mode: {lesson.mode}")

                # Load latest version blocks for actual content context
                from app.models.generated_block import GeneratedBlock
                from app.models.generated_lesson_version import GeneratedLessonVersion

                ver_stmt = (
                    select(GeneratedLessonVersion)
                    .where(GeneratedLessonVersion.lesson_id == lesson.id)
                    .order_by(GeneratedLessonVersion.version.desc())
                    .limit(1)
                )
                ver_result = await self._uow.session.execute(ver_stmt)
                version = ver_result.scalar_one_or_none()
                if version:
                    block_stmt = (
                        select(GeneratedBlock)
                        .where(GeneratedBlock.lesson_version_id == version.id)
                        .order_by(GeneratedBlock.position)
                    )
                    block_result = await self._uow.session.execute(block_stmt)
                    blocks = block_result.scalars().all()
                    if blocks:
                        # Include block content around the current slide position
                        pos = conv.slide_position or 0
                        start = max(0, pos - 1)
                        end = min(len(blocks), pos + 3)
                        parts.append("\n--- LESSON CONTENT ---")
                        for b in blocks[start:end]:
                            heading = b.heading or ""
                            content = (b.content or "")[:800]
                            parts.append(f"[{b.block_type}] {heading}\n{content}")
                        parts.append("--- END LESSON CONTENT ---")

        # Load source material chunks for RAG context
        rag_chunks = await self._retrieve_relevant_chunks(
            user_query=conv.title or "",
            lesson_id=conv.lesson_id,
            limit=3,
        )
        if rag_chunks:
            parts.append("\n--- RELEVANT SOURCE MATERIAL ---")
            for chunk in rag_chunks:
                parts.append(chunk)
            parts.append("--- END SOURCE MATERIAL ---")

        # Load educational memory for personalization
        try:
            from app.services.educational_memory_service import educational_memory_service
            from app.services.recommendation_engine import generate_recommendations
            user_str = str(conv.user_id) if conv.user_id else None
            if user_str:
                memory = await educational_memory_service.load_from_db(self._uow.session, user_str)
                has_data = (
                    memory.weak_concepts
                    or memory.mastered_concepts
                    or memory.developing_concepts
                    or memory.concept_records
                )
                if has_data:
                    parts.append("\n--- LEARNER PROFILE ---")
                if memory.weak_concepts:
                    weak_names = _concept_ids_to_names(memory.weak_concepts, memory, limit=5)
                    parts.append(f"Weak concepts: {weak_names}")
                if memory.developing_concepts:
                    dev_names = _concept_ids_to_names(memory.developing_concepts, memory, limit=5)
                    parts.append(f"Developing concepts: {dev_names}")
                if memory.mastered_concepts:
                    mastered_names = _concept_ids_to_names(memory.mastered_concepts, memory, limit=5)
                    parts.append(f"Mastered concepts: {mastered_names}")
                # Per-concept mastery scores
                if memory.concept_records:
                    parts.append("Per-concept mastery:")
                    for _cid, record in memory.concept_records.items():
                        trend = f" ({record.trend})" if record.trend != "stable" else ""
                        parts.append(
                            f"  - {record.concept_name}: {record.mastery_score:.0f}%"
                            f" (reviews: {record.review_count}){trend}"
                        )
                if memory.profile.average_mastery is not None and memory.profile.average_mastery > 0:
                    parts.append(f"Overall mastery: {memory.profile.average_mastery}%")
                # Structured recommendations
                try:
                    recommendation = generate_recommendations(user_str, memory, max_actions=3)
                    if recommendation.actions:
                        parts.append("Recommended next actions:")
                        for action in recommendation.actions:
                            parts.append(
                                f"  - [{action.action_type.value}] {action.title}"
                                f" (priority: {action.priority.value})"
                            )
                        parts.append(f"Summary: {recommendation.summary}")
                except Exception:
                    pass
                if has_data:
                    parts.append("--- END LEARNER PROFILE ---")
        except Exception:
            pass

        parts.append(f"Slide position: {conv.slide_position}")
        parts.append(f"Block position: {conv.block_position}")
        return "\n".join(parts) or "(no lesson context)"

    async def _retrieve_relevant_chunks(
        self,
        user_query: str,
        lesson_id: uuid.UUID | None,
        limit: int = 3,
        *,
        provider: EmbeddingProvider | None = None,
    ) -> list[str]:
        """Retrieve relevant source material chunks for the current lesson.

        Primary path is vector semantic retrieval: the query is embedded and
        ranked by application-side cosine similarity against the persisted
        ``ChunkEmbedding.vector`` values (symmetric with the chunk pipeline's
        provider/model). When embeddings are unavailable, the query cannot be
        embedded, or nothing passes the similarity floor, a deterministic
        positional fallback (``DocumentChunk.position``) is used instead.
        """
        if not lesson_id:
            return []
        try:
            from app.models.generated_lesson import GeneratedLesson

            # Resolve presentation_id from lesson
            lesson_stmt = select(GeneratedLesson).where(GeneratedLesson.id == lesson_id)
            lesson_result = await self._uow.session.execute(lesson_stmt)
            lesson = lesson_result.scalar_one_or_none()
            if not lesson:
                return []

            # Get chunks linked to this presentation's content units
            from app.models.content_unit import ContentUnit
            cu_stmt = select(ContentUnit.id).where(
                ContentUnit.presentation_id == lesson.presentation_id
            )
            cu_result = await self._uow.session.execute(cu_stmt)
            cu_ids = [row[0] for row in cu_result.all()]
            if not cu_ids:
                return []

            # Resolve an embedding provider for semantic retrieval. An explicit
            # provider (tests) wins; otherwise use the configured singleton,
            # degrading to the positional fallback when none is configured.
            if provider is None:
                try:
                    from app.ai.embeddings.factory import get_embedding_provider
                    provider = get_embedding_provider()
                except Exception:
                    provider = None

            if provider is not None and user_query and user_query.strip():
                semantic_chunks = await self._retrieve_relevant_chunks_semantic(
                    user_query=user_query,
                    content_unit_ids=cu_ids,
                    limit=limit,
                    provider=provider,
                )
                if semantic_chunks:
                    return semantic_chunks

            return await self._retrieve_relevant_chunks_positional(
                content_unit_ids=cu_ids,
                limit=limit,
            )
        except Exception:
            return []

    async def _retrieve_relevant_chunks_semantic(
        self,
        *,
        user_query: str,
        content_unit_ids: list[uuid.UUID],
        limit: int,
        provider: EmbeddingProvider,
    ) -> list[str]:
        """Attempt vector semantic retrieval; returns ``[]`` to trigger fallback."""
        try:
            response = await provider.embed([user_query])
            if not response.vectors:
                return []
            query_vector = response.vectors[0]

            from app.repositories.rag_repository import DocumentChunkRepository
            pairs = await DocumentChunkRepository(self._uow.session).list_embedded_pairs_for_content_units(
                content_unit_ids=content_unit_ids,
                provider=provider.name or provider.config.provider,
                model=provider.model,
                limit=settings.TUTOR_EMBEDDING_SEARCH_LIMIT,
            )

            scored: list[tuple[float, int, uuid.UUID, str]] = []
            for chunk, embedding in pairs:
                chunk_vector = embedding.vector
                similarity = cosine_similarity(query_vector, chunk_vector)
                if similarity is None:
                    continue
                if similarity < settings.TUTOR_RETRIEVAL_SIMILARITY_THRESHOLD:
                    continue
                scored.append(
                    (similarity, chunk.position, chunk.id, (chunk.content or "")[:500])
                )

            # Deterministic: similarity desc, then position asc, then chunk id.
            scored.sort(key=lambda item: (-item[0], item[1], item[2]))
            return [content for _, _, _, content in scored[:limit]]
        except Exception:
            return []

    async def _retrieve_relevant_chunks_positional(
        self,
        *,
        content_unit_ids: list[uuid.UUID],
        limit: int,
    ) -> list[str]:
        """Deterministic positional fallback (original RAG behavior)."""
        from app.models.document_chunk import DocumentChunk
        chunk_stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.content_unit_id.in_(content_unit_ids))
            .where(DocumentChunk.content.isnot(None))
            .where(DocumentChunk.content != "")
            .where(DocumentChunk.deleted_at.is_(None))
            .order_by(DocumentChunk.position, DocumentChunk.id)
            .limit(limit)
        )
        chunk_result = await self._uow.session.execute(chunk_stmt)
        chunks = chunk_result.scalars().all()
        return [c.content[:500] for c in chunks if c.content]

    async def _load_history(self, conversation_id: uuid.UUID) -> list:
        msgs = await self._message_repo.recent_for_conversation(conversation_id, limit=20)
        from app.ai.models import AIMessage
        return [
            AIMessage(role=m.role, content=m.content)
            for m in msgs
            if m.status == AssistantMessageStatus.COMPLETED.value
        ]

    async def _generate_response(
        self,
        context_text: str,
        history: list,
        user_message: str,
    ) -> str:
        """Try AI provider; fall back to contextual answer if unavailable."""
        try:
            from app.ai.service import get_ai_content_service

            provider = get_ai_content_service()
            request = self._prompt_builder.build_ai_request(
                context_text=context_text,
                history=history,
                user_message=user_message,
                metadata={},
                max_tokens=2048,
            )
            response = await provider.generate(request)
            if response.success and response.text:
                return response.text
        except Exception:
            pass

        # Graceful fallback: provide a contextual answer using the lesson content
        context_snippet = context_text[:1000] if context_text else ""
        return (
            f"Based on the learning material:\n\n"
            f"{context_snippet}\n\n"
            f"Regarding your question: **{user_message}**\n\n"
            f"To get a more detailed AI-powered answer, please ensure "
            f"the AI provider is properly configured."
        )


def _concept_ids_to_names(
    concept_ids: list[str],
    memory: Any,
    limit: int = 5,
) -> str:
    """Convert concept IDs to human-readable names using the memory's concept records."""
    names = []
    for cid in concept_ids[:limit]:
        record = memory.concept_records.get(cid)
        if record and record.concept_name:
            names.append(record.concept_name)
        else:
            names.append(cid)
    return ", ".join(names)

"""Mastery-Aware AI Tutor service (P8).

Grounds every tutor answer in the learner's own content and mastery state:

* Sessions and conversations are learner-scoped (``user_id`` derived from the
  authenticated user — never from the client).
* Context assembly binds educational memory (mastery scores, weak concepts),
  bounded recent quiz attempts, and RAG chunks retrieved *only* from content
  units that belong to the learner's presentations.
* Answers are produced through ``AIContentService`` (the mandatory AI path).
  When AI is disabled/unavailable/RAG is cold/times out, a fully deterministic,
  memory-driven response is produced with ``source_kind="deterministic"`` so the
  learner always gets grounded, attributed, confident output — never fabricated
  AI content.
* Attribution and confidence are written truthfully on every assistant message.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.concept import Concept
from app.models.content_unit import ContentUnit
from app.models.generated_lesson import GeneratedLesson
from app.models.presentation import Presentation
from app.models.quiz_attempt import QuizAttempt
from app.models.tutor_message import TutorMessage
from app.models.tutor_session import TutorSession
from app.repositories.tutor_repository import (
    TutorConversationRepository,
    TutorMessageRepository,
    TutorSessionRepository,
)
from app.schemas.tutor import (
    TutorMessageSendRequest,
    TutorRemediateRequest,
    TutorSessionCreateRequest,
)
from app.services.educational_memory_service import educational_memory_service
from app.services.recommendation_engine import generate_recommendations
from shared.constants import (
    TutorConfidenceLevel,
    TutorMessageStatus,
    TutorSourceKind,
)

logger = get_logger(__name__)

_SYSTEM_BEHAVIOR = (
    "You are the Mastery-Aware AI Tutor inside EduVision AI. You answer clearly "
    "and concisely using ONLY the learner's own material and mastery state "
    "provided in the context. You never invent facts, numbers, or source "
    "material that is not present in the context. If the learner's material does "
    "not cover something, say so plainly rather than guessing. Succeed the "
    "answer with an attribution line naming the source you drew from."
)


def _serialize_session(s: TutorSession) -> dict[str, Any]:
    return {
        "id": s.public_id,
        "lesson_id": s.lesson_public_id,
        "presentation_id": str(s.presentation_id) if s.presentation_id else None,
        "target_concept_id": s.target_concept_id,
        "title": s.title,
        "status": s.status,
        "mode": s.mode,
        "difficulty": s.difficulty,
        "language": s.language,
        "context_version": s.context_version,
        "message_count": s.message_count,
        "last_message_at": s.last_message_at,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def _serialize_message(m: TutorMessage) -> dict[str, Any]:
    return {
        "id": m.public_id,
        "role": m.role,
        "content": m.content,
        "status": m.status,
        "source_kind": m.source_kind,
        "attribution": m.attribution,
        "confidence": m.confidence,
        "model": m.model,
        "provider": m.provider,
        "tokens_in": m.tokens_in,
        "tokens_out": m.tokens_out,
        "latency_ms": m.latency_ms,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


def _serialize_exchange(
    user_msg: TutorMessage | None,
    assistant_msg: TutorMessage | None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    return {
        "user_message": _serialize_message(user_msg) if user_msg else None,
        "assistant_message": _serialize_message(assistant_msg) if assistant_msg else None,
        "conversation_id": conversation_id,
    }


class MasteryTutorService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    @property
    def _session_repo(self) -> TutorSessionRepository:
        return TutorSessionRepository(self._uow.session)

    @property
    def _conversation_repo(self) -> TutorConversationRepository:
        return TutorConversationRepository(self._uow.session)

    @property
    def _message_repo(self) -> TutorMessageRepository:
        return TutorMessageRepository(self._uow.session)

    # ── Sessions ────────────────────────────────────────────────────────────

    async def create_session(
        self,
        user_id: uuid.UUID,
        request: TutorSessionCreateRequest,
    ) -> dict[str, Any]:
        lesson = None
        lesson_id: uuid.UUID | None = None
        lesson_public_id: str | None = None
        presentation_id: uuid.UUID | None = None

        if request.lesson_id:
            lesson = await self._get_owned_lesson(user_id, request.lesson_id)
            lesson_id = lesson.id
            lesson_public_id = lesson.public_id
            presentation_id = lesson.presentation_id
        elif request.presentation_id:
            presentation_id = await self._verify_presentation_owner(
                user_id, request.presentation_id
            )

        target_concept_id = None
        if request.target_concept_id:
            await self._verify_concept_ownership(user_id, request.target_concept_id)
            target_concept_id = request.target_concept_id

        session = await self._session_repo.create_for_user(
            user_id=user_id,
            title=request.title,
            lesson_id=lesson_id,
            lesson_public_id=lesson_public_id,
            presentation_id=presentation_id,
            target_concept_id=target_concept_id,
            mode=request.mode,
            difficulty=request.difficulty,
            language=request.language,
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

    # ── Messages ────────────────────────────────────────────────────────────

    async def send_message(
        self,
        user_id: uuid.UUID,
        session_public_id: str,
        request: TutorMessageSendRequest,
    ) -> dict[str, Any]:
        session = await self._session_repo.get_for_user_or_raise(user_id, session_public_id)
        conversation = await self._conversation_repo.latest_for_session(session.id)
        if conversation is None:
            conversation = await self._conversation_repo.create(
                user_id=user_id,
                session_id=session.id,
                session_public_id=session.public_id,
                lesson_id=session.lesson_id,
                lesson_public_id=session.lesson_public_id,
                title=session.title,
            )
            session.message_count += 1
            await self._uow.flush()

        # Idempotency: replay protection for a repeated client_message_id.
        if request.client_message_id:
            existing = await self._find_user_message(conversation.id, request.client_message_id)
            if existing:
                reply = await self._find_assistant_reply(conversation.id, existing)
                return _serialize_exchange(existing, reply, conversation_id=conversation.public_id)

        # Persist the sanitized user turn.
        user_msg = await self._message_repo.create_user_message(
            conversation_id=conversation.id,
            user_id=user_id,
            content=request.content,
            client_message_id=request.client_message_id,
        )
        await self._uow.flush()

        # Build a bounded, learner-grounded context.
        context = await self._build_context(
            user_id=user_id,
            lesson_id=conversation.lesson_id,
            target_concept_id=session.target_concept_id,
            user_message=request.content,
        )

        # Produce the answer (AIContentService path, else deterministic fallback).
        start = time.monotonic()
        content, source_kind, attribution, confidence, model, provider, answer_meta = (
            await self._produce_answer(
                user_id=user_id,
                user_message=request.content,
                context=context,
                history=await self._load_history(conversation.id),
            )
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        assistant_msg = await self._message_repo.create_assistant_message(
            conversation_id=conversation.id,
            user_id=user_id,
            content=content,
            source_kind=source_kind,
            attribution=attribution,
            confidence=confidence,
            model=model,
            provider=provider,
            tokens_in=len(request.content.split()),
            tokens_out=len(content.split()),
            latency_ms=latency_ms,
            retrieval_metadata=context.get("retrieval"),
            answer_metadata=answer_meta,
        )
        await self._uow.flush()

        await self._conversation_repo.touch(conversation)
        await self._session_repo.touch(session)

        return _serialize_exchange(user_msg, assistant_msg, conversation_id=conversation.public_id)

    async def list_messages(
        self,
        user_id: uuid.UUID,
        conversation_public_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        conversation = await self._conversation_repo.get_for_user_or_raise(
            user_id, conversation_public_id
        )
        filters = [TutorMessage.conversation_id == conversation.id]
        count_stmt = (
            select(func.count())
            .select_from(TutorMessage)
            .where(*filters)
        )
        total = (await self._uow.session.execute(count_stmt)).scalar_one()
        stmt = (
            select(TutorMessage)
            .where(*filters)
            .order_by(TutorMessage.created_at.desc(), TutorMessage.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._uow.session.execute(stmt)
        items = list(result.scalars().all())
        return [_serialize_message(m) for m in items], int(total)

    # ── Remediation ─────────────────────────────────────────────────────────

    async def remediate(
        self,
        user_id: uuid.UUID,
        request: TutorRemediateRequest,
    ) -> dict[str, Any]:
        concept = await self._verify_concept_ownership(user_id, request.target_concept_id)

        lesson = None
        if request.lesson_id:
            lesson = await self._get_owned_lesson(user_id, request.lesson_id)

        memory = await educational_memory_service.load_from_db(
            self._uow.session, str(user_id)
        )
        record = memory.concept_records.get(concept.public_id)
        mastery = record.mastery_score if record else None
        confidence = (
            TutorConfidenceLevel.HIGH.value
            if record and record.confidence_score >= 0.7
            else TutorConfidenceLevel.MEDIUM.value
        )

        response_text = self._deterministic_explanation(
            concept_name=concept.name,
            concept_description=concept.description,
            mastery=mastery,
            context=await self._build_context(
                user_id=user_id,
                lesson_id=lesson.id if lesson else None,
                target_concept_id=concept.public_id,
                user_message=f"Help me remediate {concept.name}",
            ),
        )

        session = None
        conversation = None
        message_id = None
        try:
            session = await self._session_repo.create_for_user(
                user_id=user_id,
                title=f"Remediate {concept.name}",
                lesson_id=lesson.id if lesson else None,
                lesson_public_id=lesson.public_id if lesson else None,
                presentation_id=concept.presentation_id,
                target_concept_id=concept.public_id,
                mode="remediation",
            )
            conversation = await self._conversation_repo.create(
                user_id=user_id,
                session_id=session.id,
                session_public_id=session.public_id,
                lesson_id=session.lesson_id,
                lesson_public_id=session.lesson_public_id,
                title=f"Remediate {concept.name}",
            )
            await self._message_repo.create_user_message(
                conversation_id=conversation.id,
                user_id=user_id,
                content=f"Please help me understand {concept.name} better.",
            )
            await self._uow.flush()
            assistant_msg = await self._message_repo.create_assistant_message(
                conversation_id=conversation.id,
                user_id=user_id,
                content=response_text,
                source_kind=TutorSourceKind.DETERMINISTIC.value,
                attribution=concept.name,
                confidence=confidence,
                tokens_out=len(response_text.split()),
            )
            await self._uow.flush()
            message_id = assistant_msg.public_id
        except Exception:
            logger.warning("tutor_remediation_persist_failed", error="remediation_persist")

        return {
            "target_concept_id": concept.public_id,
            "target_concept_name": concept.name,
            "mastery_score": mastery,
            "source_kind": TutorSourceKind.DETERMINISTIC.value,
            "attribution": concept.name,
            "confidence": confidence,
            "response": response_text,
            "session_id": session.public_id if session else None,
            "conversation_id": conversation.public_id if conversation else None,
            "message_id": message_id,
            "metadata": {
                "mastery": mastery,
                "reviews": record.review_count if record else 0,
                "difficulty": concept.difficulty_level,
            },
        }

    # ── Internal helpers ────────────────────────────────────────────────────

    async def _produce_answer(
        self,
        *,
        user_id: uuid.UUID,
        user_message: str,
        context: dict[str, Any],
        history: list[Any],
    ) -> tuple[str, str, str | None, str, str | None, str | None, dict[str, Any] | None]:
        """Produce a grounded answer with truthful attribution + confidence.

        Returns ``(content, source_kind, attribution, confidence, model, provider,
        answer_metadata)``. Tries the AI path via ``AIContentService``; on any
        failure (disabled/unavailable/cold RAG/timeout) falls back to a fully
        deterministic, memory-grounded reply with ``source_kind="deterministic"``.
        """
        # Deterministic path first when there is no learner grounding at all.
        baseline = self._deterministic_explanation(
            concept_name=context.get("weak_concept_name"),
            concept_description=None,
            mastery=context.get("weak_mastery"),
            context=context,
        )
        baseline_conf = _confidence_from_mastery(context.get("weak_mastery"))

        try:
            from app.ai.models import AIRequest, AIResponseFormat
            from app.ai.service import get_ai_content_service

            rag_chunks = context.get("rag_chunks") or []
            if not rag_chunks:
                # RAG is cold: only a deterministic answer can be grounded.
                return (
                    baseline,
                    TutorSourceKind.DETERMINISTIC.value,
                    context.get("attribution"),
                    baseline_conf,
                    None,
                    None,
                    {"deterministic_reason": "no_retrieval_context"},
                )

            service = get_ai_content_service()
            audit_prompt = self._build_ai_prompt(
                context_text=context.get("context_text") or "",
                history=history,
                user_message=user_message,
            )
            request = AIRequest(
                user_prompt=audit_prompt,
                system_prompt=_SYSTEM_BEHAVIOR,
                messages=history,
                response_format=AIResponseFormat.MARKDOWN,
                max_tokens=settings.TUTOR_MAX_RESPONSE_TOKENS,
                metadata={"resource_type": "tutor"},
            )
            response = await service.generate(request)
            if response.success and response.text:
                return (
                    self._with_attribution(response.text, context.get("attribution")),
                    TutorSourceKind.RAG.value,
                    context.get("attribution"),
                    _confidence_from_rag(rag_chunks),
                    response.model,
                    response.provider,
                    None,
                )
        except Exception as exc:
            logger.warning(
                "tutor_ai_fallback",
                error=str(exc),
                fallback="deterministic",
            )

        # Deterministic fallback keeps the reply grounded and truthful.
        return (
            baseline,
            TutorSourceKind.DETERMINISTIC.value,
            context.get("attribution"),
            baseline_conf,
            None,
            None,
            {"deterministic_reason": "ai_unavailable"},
        )

    async def _build_context(
        self,
        *,
        user_id: uuid.UUID,
        lesson_id: uuid.UUID | None,
        target_concept_id: str | None,
        user_message: str,
    ) -> dict[str, Any]:
        parts: list[str] = []

        # 1) Educational memory (mastery, weak concepts).
        memory = await educational_memory_service.load_from_db(self._uow.session, str(user_id))
        weak_concept_id = None
        weak_concept_name = None
        weak_mastery = None
        if memory.weak_concepts:
            first = memory.weak_concepts[0]
            weak_concept_id = first
            rec = memory.concept_records.get(first)
            if rec:
                weak_concept_name = rec.concept_name
                weak_mastery = rec.mastery_score
        if target_concept_id:
            rec = memory.concept_records.get(target_concept_id)
            if rec:
                weak_concept_id = target_concept_id
                weak_concept_name = rec.concept_name
                weak_mastery = rec.mastery_score
        if memory.concept_records:
            parts.append("--- LEARNER MASTERY ---")
            for _cid, record in memory.concept_records.items():
                trend = f" ({record.trend})" if record.trend != "stable" else ""
                parts.append(
                    f"{record.concept_name}: {record.mastery_score:.0f}%"
                    f" ({record.review_count} reviews){trend}"
                )
            if memory.profile.average_mastery and memory.profile.average_mastery > 0:
                parts.append(f"Overall mastery: {memory.profile.average_mastery:.0f}%")
            if memory.weak_concepts:
                weak_names = _concept_ids_to_names(memory.weak_concepts, memory, limit=5)
                parts.append(f"Weak: {weak_names}")
            parts.append("--- END LEARNER MASTERY ---")

        # 2) Bounded recent attempts (learner-scoped).
        attempts = await self._load_recent_attempts(user_id, limit=5)
        if attempts:
            parts.append("--- RECENT ATTEMPTS ---")
            for attempt in attempts:
                quiz_title = attempt.get("quiz_title") or "Quiz"
                pct = attempt.get("percent_score")
                pct_txt = f"{pct:.0f}%" if pct is not None else "n/a"
                parts.append(f"{quiz_title}: {pct_txt}")
            parts.append("--- END RECENT ATTEMPTS ---")

        # 3) RAG chunks scoped to the learner's content units.
        rag_chunks = await self._retrieve_learner_chunks(
            user_query=user_message,
            lesson_id=lesson_id,
            limit=settings.TUTOR_RETRIEVAL_TOP_K,
        )
        attribution = None
        if rag_chunks:
            parts.append("--- SOURCE MATERIAL (learner-owned) ---")
            for chunk in rag_chunks:
                parts.append(chunk)
                if attribution is None and chunk:
                    attribution = chunk[:120]
                if attribution is not None:
                    attribution = attribution + " (source material)"
                    break
            parts.append("--- END SOURCE MATERIAL ---")

        # 4) Recommendations (deterministic).
        recommendation_summary = None
        try:
            recommendation = generate_recommendations(str(user_id), memory, max_actions=3)
            if recommendation.actions:
                parts.append("--- RECOMMENDED NEXT STEPS ---")
                for action in recommendation.actions:
                    parts.append(f"- {action.title}")
            if recommendation.summary:
                parts.append(f"Summary: {recommendation.summary}")
                recommendation_summary = recommendation.summary
        except Exception:
            pass

        # 5) Lesson anchor.
        if lesson_id:
            lesson = await self._uow.session.execute(
                select(GeneratedLesson).where(GeneratedLesson.id == lesson_id)
            )
            lesson_row = lesson.scalar_one_or_none()
            if lesson_row and lesson_row.title:
                parts.append(f"Lesson: {lesson_row.title}")

        context_text = "\n".join(parts) or "(no learner context)"
        context_text = context_text[: settings.TUTOR_MAX_CONTEXT_CHARS]

        return {
            "context_text": context_text,
            "rag_chunks": rag_chunks,
            "weak_concept_id": weak_concept_id,
            "weak_concept_name": weak_concept_name,
            "weak_mastery": weak_mastery,
            "attribution": attribution,
            "recommendation_summary": recommendation_summary,
            "retrieval": {
                "source_kind": "rag" if rag_chunks else "none",
                "chunk_count": len(rag_chunks),
            },
        }

    async def _retrieve_learner_chunks(
        self,
        *,
        user_query: str,
        lesson_id: uuid.UUID | None,
        limit: int,
    ) -> list[str]:
        """Retrieve RAG chunks exclusively from the learner's content units."""
        try:
            from app.ai.embeddings.factory import get_embedding_provider
            from app.models.document_chunk import DocumentChunk
            from app.repositories.rag_repository import DocumentChunkRepository

            content_unit_ids: list[uuid.UUID] = []
            if lesson_id:
                lesson = (
                    await self._uow.session.execute(
                        select(GeneratedLesson).where(GeneratedLesson.id == lesson_id)
                    )
                ).scalar_one_or_none()
                if lesson:
                    cu_result = await self._uow.session.execute(
                        select(ContentUnit.id).where(
                            ContentUnit.presentation_id == lesson.presentation_id
                        )
                    )
                    content_unit_ids = [row[0] for row in cu_result.all()]

            if not content_unit_ids:
                return []

            provider = get_embedding_provider()
            if provider is not None and user_query and user_query.strip():
                pairs = await DocumentChunkRepository(self._uow.session).list_embedded_pairs_for_content_units(
                    content_unit_ids=content_unit_ids,
                    provider=provider.name or provider.config.provider,
                    model=provider.model,
                    limit=settings.TUTOR_EMBEDDING_SEARCH_LIMIT,
                )
                if pairs:
                    return [
                        c.content[:500]
                        for c, _ in pairs
                        if c.content
                    ][:limit]

            # Positional, learner-scoped fallback.
            stmt = (
                select(DocumentChunk)
                .where(DocumentChunk.content_unit_id.in_(content_unit_ids))
                .where(DocumentChunk.content.isnot(None))
                .where(DocumentChunk.content != "")
                .where(DocumentChunk.deleted_at.is_(None))
                .order_by(DocumentChunk.position, DocumentChunk.id)
                .limit(limit)
            )
            chunks = (await self._uow.session.execute(stmt)).scalars().all()
            return [c.content[:500] for c in chunks if c.content]
        except Exception:
            return []

    async def _load_recent_attempts(
        self, user_id: uuid.UUID, limit: int = 5
    ) -> list[dict[str, Any]]:
        try:
            from app.models.quiz import Quiz

            stmt = (
                select(QuizAttempt, Quiz)
                .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
                .where(QuizAttempt.user_id == user_id)
                .order_by(
                    QuizAttempt.completed_at.desc().nulls_last(),
                    QuizAttempt.created_at.desc(),
                )
                .limit(limit)
            )
            rows = (await self._uow.session.execute(stmt)).all()
            return [
                {
                    "quiz_title": quiz.title if quiz else None,
                    "percent_score": attempt.percent_score,
                }
                for attempt, quiz in rows
            ]
        except Exception:
            return []

    async def _load_history(self, conversation_id: uuid.UUID) -> list[Any]:
        msgs = await self._message_repo.recent_for_conversation(conversation_id, limit=20)
        from typing import cast

        from app.ai.models import AIMessage, RoleName

        completed: list[Any] = []
        for m in msgs:
            if m.status != TutorMessageStatus.COMPLETED.value:
                continue
            completed.append(AIMessage(role=cast(RoleName, m.role), content=m.content))
        return completed

    def _build_ai_prompt(
        self,
        *,
        context_text: str,
        history: list[Any],
        user_message: str,
    ) -> str:
        history_text = "\n".join(f"[{m.role}] {m.content}" for m in history) if history else "(none)"
        return (
            f"--- LEARNER-GROUNDED CONTEXT (frozen, do not infer outside it) ---\n"
            f"{context_text or '(empty context)'}\n"
            f"--- END CONTEXT ---\n\n"
            f"--- CONVERSATION SO FAR ---\n{history_text}\n--- END CONVERSATION ---\n\n"
            f"Learner question:\n{user_message}"
        )

    def _deterministic_explanation(
        self,
        *,
        concept_name: str | None,
        concept_description: str | None,
        mastery: float | None,
        context: dict[str, Any],
    ) -> str:
        """Build a deterministic, grounded explanation from learner state.

        Never invents material: it reports the concept name, the learner's
        measured mastery, the strongest recommendation from the deterministic
        engine, and (when available) an excerpt of the learner's own source
        material. It is attributed as ``deterministic``.
        """
        name = concept_name or (context.get("weak_concept_name") or "this concept")
        mastery_txt = f"{mastery:.0f}%" if mastery is not None else "not yet measured"

        lines = [
            f"Here's a focused summary on **{name}**.",
            f"Your current mastery is **{mastery_txt}**.",
        ]
        if concept_description:
            lines.append(f"Overview: {concept_description[:400]}")

        recommendation = context.get("recommendation_summary")
        if recommendation:
            lines.append(f"Suggested next step: {recommendation}")

        if not context.get("rag_chunks"):
            lines.append(
                "There is no rich source material in your library matched to "
                "this question yet, so this answer is generated from your mastery "
                "data rather than a document."
            )

        return "\n\n".join(lines)

    def _with_attribution(self, text: str, attribution: str | None) -> str:
        if attribution and not text.strip().endswith(attribution):
            return f"{text}\n\n_Source: {attribution}_"
        return text

    # ── Ownership verification ──────────────────────────────────────────────

    async def _verify_presentation_owner(
        self, user_id: uuid.UUID, presentation_public_id: str
    ) -> uuid.UUID | None:
        stmt = select(Presentation).where(Presentation.public_id == presentation_public_id)
        result = await self._uow.session.execute(stmt)
        presentation = result.scalar_one_or_none()
        if (
            presentation is None
            or presentation.deleted_at is not None
            or presentation.owner_id is None
            or str(presentation.owner_id) != str(user_id)
        ):
            # 404-equalized: do not leak whether the resource exists.
            raise NotFoundError(
                message="Presentation not found",
                details={"presentation_id": presentation_public_id},
            )
        return presentation.id

    async def _get_owned_lesson(
        self, user_id: uuid.UUID, lesson_public_id: str
    ) -> GeneratedLesson:
        stmt = select(GeneratedLesson).where(GeneratedLesson.public_id == lesson_public_id)
        result = await self._uow.session.execute(stmt)
        lesson = result.scalar_one_or_none()
        if lesson is None:
            raise NotFoundError(
                message="Lesson not found",
                details={"lesson_id": lesson_public_id},
            )
        # A lesson is owner-validated through its presentation owner (the single
        # ownership unit) OR its direct user_id, mirroring assert_quiz_ownership.
        owned_via_presentation = False
        if lesson.presentation_id:
            pres = (
                await self._uow.session.execute(
                    select(Presentation).where(Presentation.id == lesson.presentation_id)
                )
            ).scalar_one_or_none()
            owned_via_presentation = bool(
                pres
                and pres.owner_id is not None
                and str(pres.owner_id) == str(user_id)
                and pres.deleted_at is None
            )
        owned_via_user = bool(lesson.user_id is not None and str(lesson.user_id) == str(user_id))
        if not (owned_via_presentation or owned_via_user):
            raise NotFoundError(
                message="Lesson not found",
                details={"lesson_id": lesson_public_id},
            )
        return lesson

    async def _verify_concept_ownership(
        self, user_id: uuid.UUID, concept_public_id: str
    ) -> Concept:
        stmt = select(Concept).where(Concept.public_id == concept_public_id)
        result = await self._uow.session.execute(stmt)
        concept = result.scalar_one_or_none()
        if concept is None or concept.presentation_id is None:
            raise NotFoundError(
                message="Concept not found",
                details={"concept_id": concept_public_id},
            )
        # Ownership flows through concept -> presentation.owner_id (single unit).
        pres = (
            await self._uow.session.execute(
                select(Presentation).where(Presentation.id == concept.presentation_id)
            )
        ).scalar_one_or_none()
        if (
            pres is None
            or pres.owner_id is None
            or str(pres.owner_id) != str(user_id)
            or pres.deleted_at is not None
        ):
            raise NotFoundError(
                message="Concept not found",
                details={"concept_id": concept_public_id},
            )
        return concept

    async def _find_user_message(
        self, conversation_id: uuid.UUID, client_message_id: str
    ) -> TutorMessage | None:
        stmt = (
            select(TutorMessage)
            .where(
                TutorMessage.conversation_id == conversation_id,
                TutorMessage.client_message_id == client_message_id,
                TutorMessage.role == "user",
            )
            .limit(1)
        )
        result = await self._uow.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_assistant_reply(
        self, conversation_id: uuid.UUID, user_message: TutorMessage
    ) -> TutorMessage | None:
        """Find the assistant reply created immediately after ``user_message``.

        Relies on created_at ordering (the two turns are written in the same
        transaction) rather than UUID magnitude, which is not guaranteed to
        reflect insertion order.
        """
        stmt = (
            select(TutorMessage)
            .where(
                TutorMessage.conversation_id == conversation_id,
                TutorMessage.role == "assistant",
                TutorMessage.created_at >= user_message.created_at,
            )
            .order_by(TutorMessage.created_at, TutorMessage.id)
            .limit(1)
        )
        result = await self._uow.session.execute(stmt)
        return result.scalar_one_or_none()


def _confidence_from_mastery(mastery: float | None) -> str:
    if mastery is None:
        return TutorConfidenceLevel.LOW.value
    if mastery < 50.0:
        return TutorConfidenceLevel.LOW.value
    if mastery < 85.0:
        return TutorConfidenceLevel.MEDIUM.value
    return TutorConfidenceLevel.HIGH.value


def _confidence_from_rag(chunks: list[str]) -> str:
    if not chunks:
        return TutorConfidenceLevel.LOW.value
    return TutorConfidenceLevel.MEDIUM.value


def _concept_ids_to_names(
    concept_ids: list[str],
    memory: Any,
    limit: int = 5,
) -> str:
    names = []
    for cid in concept_ids[:limit]:
        record = memory.concept_records.get(cid)
        if record and record.concept_name:
            names.append(record.concept_name)
        else:
            names.append(cid)
    return ", ".join(names)

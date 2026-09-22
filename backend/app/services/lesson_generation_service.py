"""Lesson generation orchestration.

Coordinates content extraction state, AI generation (via ``AIContentService``),
safety validation hooks, version persistence and the lesson lifecycle state
machine with distinct retry state. The worker entrypoint is
``run_generation``; API-facing methods receive an already-authorized
``Presentation`` (authorization lives in ``PresentationService``).

Structured logs never include prompt content, API keys or raw model output.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.errors import AIError, AITruncationError
from app.ai.service import AIContentService
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.generated_block import GeneratedBlock
from app.models.generated_lesson import GeneratedLesson
from app.models.presentation import Presentation
from app.repositories.content_repository import ContentUnitRepository
from app.repositories.generated_lesson_repository import (
    GeneratedLessonRepository,
    GeneratedLessonVersionRepository,
)
from app.repositories.presentation_repository import PresentationRepository
from app.repositories.topic_outline_repository import TopicOutlineRepository
from app.schemas.generated_lesson import (
    LessonBlockPayload,
    LessonGenerationRequest,
    LessonPayload,
)
from app.services.lesson_prompt_builder import (
    PAYLOAD_SCHEMA_VERSION,
    PROMPT_VERSION,
    LessonPromptBuilder,
    SourceTopic,
)
from app.services.lesson_safety import (
    LessonSafetyError,
    LessonSafetyValidator,
    build_safety_validator,
)
from shared.constants import (
    DIALECTS_SUPPORTED,
    LearningMode,
    LessonRetryState,
    LessonStatus,
    LessonVersionStatus,
)

logger = get_logger(__name__)

ERROR_SOURCE_EMPTY = "source_empty"
ERROR_PAYLOAD_INVALID = "payload_invalid"
ERROR_SAFETY_REJECTED = "safety_rejected"


class LessonGenerationSourceError(Exception):
    pass


class LessonGenerationParseError(Exception):
    pass


class LessonGenerationService:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        ai_service: Any | None = None,
        safety_validator: LessonSafetyValidator | None = None,
        builder: LessonPromptBuilder | None = None,
    ) -> None:
        self._uow = uow
        session: AsyncSession = uow.session
        self._repo = GeneratedLessonRepository(session)
        self._version_repo = GeneratedLessonVersionRepository(session)
        self._content_repo = ContentUnitRepository(session)
        self._presentation_repo = PresentationRepository(session)
        self._outline_repo = TopicOutlineRepository(session)
        self._ai = ai_service if ai_service is not None else AIContentService(uow=uow)
        self._safety = (
            safety_validator
            if safety_validator is not None
            else build_safety_validator(
                settings.AI_LESSON_SAFETY_VALIDATOR,
                ai_service=self._ai,
            )
        )
        self._builder = builder if builder is not None else LessonPromptBuilder()

    # ── Public API ────────────────────────────────────────────────────────────

    async def create_lesson(
        self,
        presentation: Presentation,
        request: LessonGenerationRequest,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        units = await self._content_repo.list_for_presentation(
            presentation.id, include_blocks=True
        )
        if not units:
            raise ConflictError(
                message="Presentation has no extracted content to generate from",
                details={"presentation_id": presentation.public_id},
            )

        if request.language and request.language not in DIALECTS_SUPPORTED:
            raise ValidationError(
                message="Unsupported language for lesson generation",
                details={"language": request.language},
            )

        if idempotency_key:
            existing = await self._repo.find_by_idempotency_key(
                None, idempotency_key
            )
            if existing is not None and existing.presentation_id == presentation.id:
                logger.info(
                    "lesson_idempotent_replayed",
                    lesson_id=existing.public_id,
                    presentation_id=presentation.public_id,
                    idempotency_key=idempotency_key,
                )
                summary = self._serialize_summary(existing, presentation.public_id)
                summary["duplicate"] = True
                return summary

        source_context = self._builder.build_source_context(
            units,
            max_units=settings.AI_LESSON_MAX_SOURCE_UNITS,
            max_chars=settings.AI_LESSON_MAX_SOURCE_CHARS,
            topics=await self._get_stored_topics(presentation.id),
        )
        lesson_request = self._to_request(lesson=None, request=request)
        await self._safety.validate_input(
            source_context=source_context,
            request=lesson_request,
            presentation_id=presentation.public_id,
        )

        # Stamp the generating user (the presentation owner) so ownership-scoped
        # lookups and the (user_id, idempotency_key) uniqueness constraint are
        # meaningful; a presentation without an owner keeps user_id NULL.
        lesson = await self._repo.create(
            presentation_id=presentation.id,
            user_id=presentation.owner_id,
            idempotency_key=idempotency_key,
            mode=request.mode.value,
            status=LessonStatus.QUEUED.value,
            title=request.title,
            language=request.language,
            difficulty=(
                request.difficulty.value if request.difficulty is not None else None
            ),
            model_override=request.model,
            latest_version=0,
            attempt_count=0,
            max_attempts=settings.AI_LESSON_MAX_ATTEMPTS,
            retry_state=LessonRetryState.NONE.value,
        )
        await self._uow.flush()

        logger.info(
            "lesson_created",
            lesson_id=lesson.public_id,
            presentation_id=presentation.public_id,
            mode=request.mode.value,
            difficulty=lesson.difficulty,
            language=lesson.language,
            idempotent=bool(idempotency_key),
        )
        return self._serialize_summary(lesson, presentation.public_id)

    async def run_generation(self, lesson_public_id: str) -> dict[str, Any]:
        lesson = await self._repo.get_by_public_id(lesson_public_id)
        if lesson is None:
            raise NotFoundError(
                message="Generated lesson not found",
                details={"lesson_id": lesson_public_id},
            )

        # Atomically claim the lesson for this attempt. A plain status check
        # races a concurrent dispatch (both sessions read QUEUED from their
        # own snapshot); the conditional UPDATE serializes on the write lock.
        claim = await self._uow.session.execute(
            update(GeneratedLesson)
            .where(
                GeneratedLesson.id == lesson.id,
                GeneratedLesson.status != LessonStatus.PROCESSING.value,
            )
            .values(
                status=LessonStatus.PROCESSING.value,
                attempt_count=GeneratedLesson.attempt_count + 1,
                retry_state=LessonRetryState.NONE.value,
                next_retry_at=None,
            )
        )
        await self._uow.flush()
        if claim.rowcount == 0:
            # Another generation attempt is already in flight (e.g. eager
            # dispatch racing an explicit retry). Never create a duplicate
            # version for the same attempt.
            logger.info(
                "lesson_generation_skipped_already_processing",
                lesson_id=lesson.public_id,
            )
            return {
                "id": lesson.public_id,
                "status": LessonStatus.PROCESSING.value,
                "skipped": True,
            }
        await self._uow.session.refresh(lesson)

        started_at = datetime.now(UTC)
        logger.info(
            "lesson_generation_started",
            lesson_id=lesson.public_id,
            attempt=lesson.attempt_count,
            max_attempts=lesson.max_attempts,
        )

        try:
            return await self._attempt_generation(lesson, started_at)
        except (
            LessonSafetyError,
            LessonGenerationParseError,
            LessonGenerationSourceError,
        ) as exc:
            error_code = self._error_code(exc)
            transient = (
                bool(getattr(exc, "retryable", False))
                or isinstance(exc, AITruncationError)
            ) and (lesson.attempt_count < lesson.max_attempts)
            await self._record_failed_version(
                lesson,
                started_at=started_at,
                error_code=error_code,
                error_message=self._friendly_error_message(exc),
            )
            if transient:
                retry_delay = float(
                    getattr(exc, "retry_after", 0) or settings.CELERY_TASK_RETRY_DELAY
                )
                lesson.status = LessonStatus.QUEUED.value
                lesson.next_retry_at = datetime.now(UTC) + timedelta(
                    seconds=retry_delay
                )
                lesson.retry_state = LessonRetryState.SCHEDULED.value
                await self._uow.flush()
                await self._uow.commit()
                logger.warning(
                    "lesson_retry_scheduled",
                    lesson_id=lesson.public_id,
                    attempt=lesson.attempt_count,
                    max_attempts=lesson.max_attempts,
                    next_retry_at=lesson.next_retry_at.isoformat()
                    if lesson.next_retry_at
                    else None,
                    error_code=error_code,
                )
                raise
            lesson.status = LessonStatus.FAILED.value
            lesson.mark_failed_permanent()
            await self._uow.flush()
            await self._uow.commit()
            logger.error(
                "lesson_generation_failed",
                lesson_id=lesson.public_id,
                attempt=lesson.attempt_count,
                error_code=error_code,
            )
            raise

    async def list_lessons(
        self,
        presentation: Presentation,
        *,
        page: int,
        page_size: int,
        mode: str | None,
        status: str | None,
    ) -> tuple[list[dict[str, Any]], int]:
        lessons, total = await self._repo.list_for_presentation(
            presentation.id,
            page=page,
            page_size=page_size,
            mode=mode,
            status=status,
        )
        return [
            self._serialize_summary(lesson, presentation.public_id)
            for lesson in lessons
        ], total

    async def get_lesson(
        self,
        presentation: Presentation,
        lesson_public_id: str,
    ) -> dict[str, Any]:
        lesson = await self._repo.get_by_public_id_for_presentation_or_raise(
            presentation.id, lesson_public_id
        )
        latest = await self._version_repo.get_latest_succeeded_for_lesson(lesson.id)
        data = self._serialize_detail(lesson, presentation.public_id)
        data["version"] = (
            self._serialize_version(latest, include_blocks=True) if latest else None
        )
        return data

    async def get_status(
        self,
        presentation: Presentation,
        lesson_public_id: str,
    ) -> dict[str, Any]:
        lesson = await self._repo.get_by_public_id_for_presentation_or_raise(
            presentation.id, lesson_public_id
        )
        error_code: str | None = None
        error_message: str | None = None
        if lesson.status == LessonStatus.FAILED.value:
            latest = await self._version_repo.get_by_lesson_and_version(
                lesson.id, lesson.latest_version
            )
            if latest is not None:
                error_code = latest.error_code
                error_message = latest.error_message
        return {
            "id": lesson.public_id,
            "presentation_id": presentation.public_id,
            "status": lesson.status_enum.value,
            "retry_state": lesson.retry_state_enum.value,
            "attempt_count": lesson.attempt_count,
            "max_attempts": lesson.max_attempts,
            "next_retry_at": lesson.next_retry_at,
            "error_code": error_code,
            "error_message": error_message,
            "latest_version": lesson.latest_version,
            "duplicate": False,
        }

    async def list_versions(
        self,
        presentation: Presentation,
        lesson_public_id: str,
    ) -> list[dict[str, Any]]:
        lesson = await self._repo.get_by_public_id_for_presentation_or_raise(
            presentation.id, lesson_public_id
        )
        versions = await self._version_repo.list_for_lesson(lesson.id)
        return [
            self._serialize_version(version, include_blocks=False)
            for version in versions
        ]

    async def get_version(
        self,
        presentation: Presentation,
        lesson_public_id: str,
        version_public_id: str,
    ) -> dict[str, Any]:
        lesson = await self._repo.get_by_public_id_for_presentation_or_raise(
            presentation.id, lesson_public_id
        )
        version = await self._version_repo.get_by_public_id_for_lesson_or_raise(
            lesson.id, version_public_id
        )
        logger.info(
            "lesson_version_viewed",
            lesson_id=lesson.public_id,
            version_id=version.public_id,
            version=version.version,
        )
        return self._serialize_version(version, include_blocks=True)

    async def delete_lesson(
        self,
        presentation: Presentation,
        lesson_public_id: str,
    ) -> None:
        lesson = await self._repo.get_by_public_id_for_presentation_or_raise(
            presentation.id, lesson_public_id
        )
        await self._repo.delete(lesson.id, hard=True)
        await self._uow.flush()
        logger.info(
            "lesson_deleted",
            lesson_id=lesson.public_id,
            presentation_id=presentation.public_id,
        )

    # ── Generation internals ──────────────────────────────────────────────────

    async def _get_stored_topics(
        self, presentation_id: Any
    ) -> list[SourceTopic] | None:
        """Return stored outline topics, or ``None`` when none exist."""
        outline = await self._outline_repo.get_by_presentation_id(presentation_id)
        if outline is None or outline.status != "succeeded":
            return None
        topics: list[SourceTopic] = []
        for topic in outline.topics or []:
            try:
                topics.append(
                    SourceTopic(
                        title=str(topic["title"]),
                        slide_ranges=[int(v) for v in topic["slide_ranges"]],
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return topics or None

    async def _attempt_generation(
        self,
        lesson: GeneratedLesson,
        started_at: datetime,
    ) -> dict[str, Any]:
        presentation = await self._presentation_repo.get(lesson.presentation_id)
        presentation_public_id = (
            presentation.public_id if presentation is not None else str(lesson.presentation_id)
        )
        units = await self._content_repo.list_for_presentation(
            lesson.presentation_id, include_blocks=True
        )
        if not units:
            raise LessonGenerationSourceError(
                "presentation has no extracted content to generate from"
            )

        mode = LearningMode(lesson.mode)
        source_context = self._builder.build_source_context(
            units,
            max_units=settings.AI_LESSON_MAX_SOURCE_UNITS,
            max_chars=settings.AI_LESSON_MAX_SOURCE_CHARS,
            topics=await self._get_stored_topics(lesson.presentation_id),
        )
        lesson_request = self._to_request(lesson=lesson, request=None)
        await self._safety.validate_input(
            source_context=source_context,
            request=lesson_request,
            presentation_id=presentation_public_id,
        )

        request = self._builder.build_ai_request(
            mode=mode,
            difficulty=lesson.difficulty,
            language=lesson.language,
            title_override=lesson.title,
            source_context=source_context,
            metadata={
                "resource_type": "generated_lesson",
                "resource_id": lesson.public_id,
                "presentation_id": presentation_public_id,
            },
            model_override=lesson.model_override,
            attempt=lesson.attempt_count,
        )
        prompt_hash = self._builder.prompt_hash(
            mode=mode,
            difficulty=lesson.difficulty,
            language=lesson.language,
            source_context=source_context,
            attempt=lesson.attempt_count,
        )

        ai_failed = False
        response = None
        grounding_report: dict[str, Any] | None = None
        try:
            response = await self._ai.generate(request)
        except AIError as exc:
            logger.warning(
                "lesson_generation_ai_failed_using_heuristic",
                lesson_id=lesson.public_id,
                error=str(exc),
                error_code=exc.code.value if hasattr(exc, "code") else "unknown",
            )
            ai_failed = True

        generation_method = "ai"

        if ai_failed or response is None:
            try:
                payload = self._build_heuristic_payload(lesson, units)
            except Exception as h_exc:
                logger.error(
                    "lesson_generation_heuristic_failed",
                    lesson_id=lesson.public_id,
                    error=str(h_exc),
                )
                raise LessonGenerationParseError(
                    f"Heuristic fallback failed: {h_exc}"
                ) from h_exc
            generation_method = "heuristic"
        else:
            try:
                payload = LessonPayload.model_validate_json(response.text)
            except Exception as exc:
                raise LessonGenerationParseError(
                    f"model returned an unparsable payload: {exc}"
                ) from exc

            await self._safety.validate_output(
                payload=payload,
                source_context=source_context,
                request=lesson_request,
            )
            grounding_report = getattr(self._safety, "grounding_report", None)

        version = await self._version_repo.create(
            lesson_id=lesson.id,
            version=lesson.latest_version + 1,
            status=LessonVersionStatus.SUCCEEDED.value,
            title=payload.title or lesson.title,
            summary=payload.summary,
            language=payload.language or lesson.language,
            difficulty=(
                payload.difficulty.value
                if payload.difficulty is not None
                else lesson.difficulty
            ),
            provider=response.provider if response else None,
            model=response.model if response else None,
            request_id=response.request_id if response and request else None,
            correlation_id=response.correlation_id if response and request else None,
            prompt_version=PROMPT_VERSION,
            payload_schema_version=PAYLOAD_SCHEMA_VERSION,
            generation_metadata={
                "generation_method": generation_method,
                "finish_reason": (
                    response.finish_reason.value
                    if response and response.finish_reason
                    else None
                ),
                "source_units_count": len(units),
                "source_chars": source_context.total_chars,
                "truncated_units": source_context.truncated_units,
                "truncated_chars": source_context.truncated_chars,
                "safety_checks": [self._safety.name],
                "language": request.language,
                "difficulty": request.difficulty,
                "idempotency_key": lesson.idempotency_key,
                "grounding": grounding_report,
            },
            input_tokens=response.usage.input_tokens if response else 0,
            output_tokens=response.usage.output_tokens if response else 0,
            total_tokens=response.usage.total_tokens if response else 0,
            estimated_cost=response.usage.estimated_cost if response else None,
            currency=response.usage.currency if response else None,
            latency_ms=response.latency_ms if response else None,
            provider_retry_count=response.retry_count if response else None,
            prompt_hash=prompt_hash,
            payload_hash=payload.payload_hash(),
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )

        for position, topic_desc in enumerate(payload.topics):
            self._uow.session.add(
                GeneratedBlock(
                    lesson_version_id=version.id,
                    block_type="paragraph",
                    position=position,
                    heading=topic_desc.topic,
                    content=topic_desc.description,
                    meta={},
                )
            )
        await self._uow.flush()

        lesson.status = LessonStatus.READY.value
        lesson.latest_version = version.version
        lesson.retry_state = LessonRetryState.NONE.value
        lesson.next_retry_at = None
        await self._uow.flush()
        await self._uow.session.refresh(lesson)

        log_fn = logger.info if generation_method == "ai" else logger.warning
        log_fn(
            "lesson_generation_succeeded",
            lesson_id=lesson.public_id,
            presentation_id=presentation_public_id,
            version=version.version,
            generation_method=generation_method,
            provider=response.provider if response else None,
            model=response.model if response else None,
            total_tokens=response.usage.total_tokens if response else 0,
            estimated_cost=str(response.usage.estimated_cost) if response else None,
            prompt_version=PROMPT_VERSION,
        )
        return self._serialize_detail(lesson, presentation_public_id)

    async def _record_failed_version(
        self,
        lesson: GeneratedLesson,
        *,
        started_at: datetime,
        error_code: str,
        error_message: str,
    ) -> None:
        version = await self._version_repo.create(
            lesson_id=lesson.id,
            version=lesson.latest_version + 1,
            status=LessonVersionStatus.FAILED.value,
            title=lesson.title,
            error_code=error_code,
            error_message=error_message[:1000],
            prompt_version=PROMPT_VERSION,
            payload_schema_version=PAYLOAD_SCHEMA_VERSION,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        lesson.latest_version = version.version
        await self._uow.flush()

    # ── Heuristic fallback ────────────────────────────────────────────────

    @staticmethod
    def _build_heuristic_payload(
        lesson: GeneratedLesson,
        units: list[Any],
    ) -> LessonPayload:
        """Build a LessonPayload from source content units without calling the AI.

        Extracts the most substantive sentences per content unit as topic
        descriptions — the same approach used by the canvas component
        discovery heuristic.
        """
        title = lesson.title or "Lesson"
        blocks: list[LessonBlockPayload] = []

        for idx, unit in enumerate(units):
            topic_title = getattr(unit, "title", None) or f"Topic {idx + 1}"

            raw = getattr(unit, "raw_text", "") or ""
            block_texts = []
            for blk in getattr(unit, "blocks", []) or []:
                content = getattr(blk, "content", "") or ""
                if content.strip():
                    block_texts.append(content.strip())

            combined = block_texts if block_texts else [raw]
            sentences: list[str] = []
            for text in combined:
                sentences.extend(
                    s.strip()
                    for s in re.split(r"[.!?\n]+\s*", text)
                    if len(s.strip()) > 15
                )

            if sentences:
                best = sorted(sentences, key=len, reverse=True)[:3]
                description = ". ".join(best)
                if len(description) > 400:
                    description = description[:397] + "..."
            else:
                description = f"Overview of {topic_title}."

            blocks.append(
                LessonBlockPayload(topic=topic_title, description=description)
            )

        if not blocks:
            blocks.append(
                LessonBlockPayload(
                    topic=title,
                    description=f"Overview of {title}.",
                )
            )

        return LessonPayload(title=title, topics=blocks)

    @staticmethod
    def _error_code(exc: Exception) -> str:
        if isinstance(exc, LessonSafetyError):
            return ERROR_SAFETY_REJECTED
        if isinstance(exc, LessonGenerationParseError):
            return ERROR_PAYLOAD_INVALID
        if isinstance(exc, LessonGenerationSourceError):
            return ERROR_SOURCE_EMPTY
        if isinstance(exc, AIError):
            return exc.code.value.lower()
        return "internal_error"

    @staticmethod
    def _friendly_error_message(exc: Exception) -> str:
        if isinstance(exc, LessonGenerationParseError):
            return (
                "Lesson generation failed: the AI output could not be parsed. "
                "The source content may be too large for the model's output "
                "limit. Please retry."
            )
        if isinstance(exc, AITruncationError):
            return (
                "Lesson generation failed: the AI model hit its output limit "
                "before finishing. The source content may be too large. "
                "Please retry."
            )
        return str(exc)[:1000]

    def _to_request(
        self,
        *,
        lesson: GeneratedLesson | None,
        request: LessonGenerationRequest | None,
    ) -> LessonGenerationRequest:
        if request is not None:
            return request
        if lesson is None:
            raise ValueError("either lesson or request must be provided")
        return LessonGenerationRequest(
            mode=LearningMode(lesson.mode),
            title=lesson.title,
            language=lesson.language,
            difficulty=lesson.difficulty_enum,
            model=lesson.model_override,
        )

    # ── Serialization ─────────────────────────────────────────────────────────

    @staticmethod
    def _serialize_block(block: GeneratedBlock) -> dict[str, Any]:
        return {
            "id": block.public_id,
            "position": block.position,
            "topic": block.heading,
            "description": block.content,
        }

    def _serialize_version(
        self,
        version: Any,
        *,
        include_blocks: bool,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": version.public_id,
            "version": version.version,
            "status": version.status_enum.value,
            "title": version.title,
            "summary": version.summary,
            "language": version.language,
            "difficulty": version.difficulty,
            "provider": version.provider,
            "model": version.model,
            "prompt_version": version.prompt_version,
            "payload_schema_version": version.payload_schema_version,
            "generation_metadata": version.generation_metadata or {},
            "usage": {
                "input_tokens": version.input_tokens,
                "output_tokens": version.output_tokens,
                "total_tokens": version.total_tokens,
                "estimated_cost": version.estimated_cost,
                "currency": version.currency,
                "latency_ms": version.latency_ms,
                "retry_count": version.provider_retry_count or 0,
            },
            "error_code": version.error_code,
            "error_message": version.error_message,
            "quality": {
                "score": version.quality_score,
                "issues": version.quality_issues or [],
                "checked_at": version.quality_checked_at,
                "version": version.quality_version,
            },
            "started_at": version.started_at,
            "completed_at": version.completed_at,
            "created_at": version.created_at,
        }
        if include_blocks:
            data["blocks"] = [
                self._serialize_block(block) for block in version.blocks
            ]
        return data

    def _serialize_summary(
        self,
        lesson: GeneratedLesson,
        presentation_public_id: str,
    ) -> dict[str, Any]:
        return {
            "id": lesson.public_id,
            "presentation_id": presentation_public_id,
            "mode": lesson.mode_enum.value,
            "status": lesson.status_enum.value,
            "title": lesson.title,
            "language": lesson.language,
            "difficulty": (
                lesson.difficulty_enum.value if lesson.difficulty_enum else None
            ),
            "model_override": lesson.model_override,
            "latest_version": lesson.latest_version,
            "retry_state": lesson.retry_state_enum.value,
            "duplicate": False,
            "created_at": lesson.created_at,
            "updated_at": lesson.updated_at,
        }

    def _serialize_detail(
        self,
        lesson: GeneratedLesson,
        presentation_public_id: str,
    ) -> dict[str, Any]:
        data = self._serialize_summary(lesson, presentation_public_id)
        data.update(
            {
                "attempt_count": lesson.attempt_count,
                "max_attempts": lesson.max_attempts,
                "next_retry_at": lesson.next_retry_at,
                "version": None,
            }
        )
        return data

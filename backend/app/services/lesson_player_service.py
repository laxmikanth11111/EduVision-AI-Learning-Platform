"""Interactive lesson player — reads a lesson and tracks persistent progress.

Reads the generated lesson and its versions and manages the learner's
position via an existing persistent ``LearningSession`` row (per authenticated
user + lesson, migration 0009), so progress survives refresh and is strictly
user-scoped. Assessment checkpoints (a ``Quiz`` bound to the lesson) and the
learner's mastery + next learning action are surfaced through the same
service, reusing the existing quiz attempt, ``educational_memory_service``
and ``recommendation_engine`` machinery.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.models.generated_lesson import GeneratedLesson
from app.models.generated_lesson_version import GeneratedLessonVersion
from app.models.presentation import Presentation
from app.repositories.generated_lesson_repository import (
    GeneratedLessonRepository,
    GeneratedLessonVersionRepository,
)
from app.repositories.quiz_repository import QuizAttemptRepository, QuizRepository
from app.services.learning_session_service import LearningSessionService
from app.utils.bounded_cache import BoundedCache
from shared.constants import PlayerMode

logger = get_logger(__name__)

# Transient in-memory session state for the anonymous/tooling player path
# (session_id -> state). Bounded + TTL'd (WS4 contract). Authenticated users
# otherwise persist their position through the ``learning_sessions`` table via
# ``LearningSessionService``, so this cache never holds per-user progress.
_SESSIONS: BoundedCache[str, dict[str, Any]] = BoundedCache(
    max_size=2048,
    ttl=3600,
)


class LessonPlayerService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        session = uow.session
        self._lesson_repo = GeneratedLessonRepository(session)
        self._version_repo = GeneratedLessonVersionRepository(session)
        self._progress = LearningSessionService(uow)

    async def _assert_lesson_ownership(
        self, lesson_public_id: str, owner_id: str
    ) -> GeneratedLesson:
        """Load a lesson and verify the user owns its presentation."""
        return await self._load_accessible_lesson(lesson_public_id, owner_id)

    async def _load_accessible_lesson(
        self,
        lesson_public_id: str,
        owner_id: str | None,
    ) -> GeneratedLesson:
        """Load a lesson, enforcing ownership when ``owner_id`` is given."""
        lesson = await self._lesson_repo.get_by_public_id(lesson_public_id)
        if lesson is None:
            raise ValueError(f"Lesson {lesson_public_id} not found")
        if owner_id is not None:
            result = await self._uow.session.execute(
                select(Presentation).where(Presentation.id == lesson.presentation_id)
            )
            presentation = result.scalar_one_or_none()
            if presentation is None or str(presentation.owner_id) != owner_id:
                raise PermissionError("You do not have access to this lesson")
            lesson.presentation = presentation
        else:
            result = await self._uow.session.execute(
                select(Presentation).where(Presentation.id == lesson.presentation_id)
            )
            presentation = result.scalar_one_or_none()
            if presentation is not None:
                lesson.presentation = presentation
        return lesson

    async def _load_source_units(self, presentation_id: uuid.UUID | None) -> list[dict[str, Any]]:
        if not presentation_id:
            return []
        from app.repositories.content_repository import ContentUnitRepository
        from app.services.content_extraction_service import ContentExtractionService

        repo = ContentUnitRepository(self._uow.session)
        units = await repo.list_for_presentation(presentation_id, include_blocks=True)
        return [ContentExtractionService._serialize_unit(u, include_blocks=True) for u in units]

    async def _load_learning_structure(
        self, presentation_id: uuid.UUID | None, presentation: Presentation | None
    ) -> dict[str, Any] | None:
        if not presentation_id:
            return None
        from app.repositories.topic_outline_repository import TopicOutlineRepository
        from app.schemas.topic_outline import build_outline_response

        repo = TopicOutlineRepository(self._uow.session)
        outline = await repo.get_by_presentation_id(presentation_id)
        if outline is None:
            return None
        pres_public_id = getattr(presentation, "public_id", "") if presentation else ""
        return build_outline_response(
            presentation_public_id=pres_public_id,
            outline=outline,
        )

    def _serialize_presentation_info(
        self, presentation: Presentation | None, slide_count: int
    ) -> dict[str, Any] | None:
        if presentation is None:
            return None
        f_name = getattr(presentation, "file_name", None) or ""
        ext = f_name.split(".")[-1] if "." in f_name else "document"
        return {
            "id": presentation.public_id,
            "title": presentation.title,
            "file_name": getattr(presentation, "file_name", None),
            "source_type": getattr(presentation, "source_type", None) or ext,
            "slide_count": slide_count,
        }

    async def get_state(
        self,
        lesson_public_id: str,
        *,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        lesson = await self._load_accessible_lesson(lesson_public_id, owner_id)
        version = await self._resolve_version(lesson)
        source_units = await self._load_source_units(lesson.presentation_id)
        learning_structure = await self._load_learning_structure(
            lesson.presentation_id, getattr(lesson, "presentation", None)
        )
        topic_visuals = await self._load_topic_visuals(lesson.presentation_id)
        topic_animations = await self._load_topic_animations(lesson.presentation_id)
        topics = self._extract_topics(
            version,
            learning_structure=learning_structure,
            topic_visuals=topic_visuals,
            topic_animations=topic_animations,
        )
        presentation_info = self._serialize_presentation_info(
            getattr(lesson, "presentation", None), len(source_units)
        )
        total_topics = len(topics) if len(topics) > 0 else len(source_units)

        active_session = None
        if owner_id:
            session = await self._progress.find_for_lesson(user_id=owner_id, lesson_id=lesson.id)
            if session is not None:
                mode = session.player_mode or PlayerMode.LEARNING.value
                session_total_slides = self._session_total_slides(
                    mode, len(source_units), total_topics
                )
                active_session = self._progress.to_player_session(
                    session,
                    total_topics,
                    lesson_public_id=lesson.public_id,
                    total_slides=session_total_slides,
                )
                resumed_slide = int(active_session.get("slide_index") or 0)
                if resumed_slide > 0:
                    logger.info(
                        "lesson_resume_restored",
                        lesson=lesson.public_id,
                        slide_index=resumed_slide,
                        total_slides=session_total_slides,
                        player_mode=mode,
                    )
        else:
            # Anonymous path: surface an existing transient session for this lesson.
            for _sid, state in _SESSIONS.items():
                if str(state.get("lesson_id")) == str(lesson.public_id):
                    if state.get("owner_id") not in (None, ""):
                        continue
                    active_session = state
                    break

        return {
            "lesson": self._serialize_lesson(lesson),
            "version": self._serialize_version(version, lesson.public_id) if version else None,
            "topics": topics,
            "source_units": source_units,
            "presentation": presentation_info,
            "learning_structure": learning_structure,
            "session": active_session,
        }

    async def start(
        self,
        lesson_public_id: str,
        *,
        owner_id: str | None = None,
        device_id: str | None = None,
        client_metadata: dict[str, Any] | None = None,
        player_mode: str = PlayerMode.LEARNING.value,
    ) -> dict[str, Any]:
        lesson = await self._load_accessible_lesson(lesson_public_id, owner_id)
        version = await self._resolve_version(lesson)
        source_units = await self._load_source_units(lesson.presentation_id)
        learning_structure = await self._load_learning_structure(
            lesson.presentation_id, getattr(lesson, "presentation", None)
        )
        topic_visuals = await self._load_topic_visuals(lesson.presentation_id)
        topic_animations = await self._load_topic_animations(lesson.presentation_id)
        topics = self._extract_topics(
            version,
            learning_structure=learning_structure,
            topic_visuals=topic_visuals,
            topic_animations=topic_animations,
        )
        presentation_info = self._serialize_presentation_info(
            getattr(lesson, "presentation", None), len(source_units)
        )
        total_topics = len(topics) if len(topics) > 0 else len(source_units)

        if owner_id:
            # Idempotent resume: same owner + lesson -> same persistent session,
            # restoring its saved position.
            session = await self._progress.get_or_create(
                user_id=owner_id,
                lesson_id=lesson.id,
                lesson_version_id=version.id if version else None,
                topic_index=0,
                total_topics=total_topics,
                device_id=device_id,
                client_metadata=client_metadata,
                player_mode=player_mode,
            )
        else:
            # Anonymous/tooling path: a short-lived, bound in-memory session.
            session_id = str(uuid.uuid4())
            session_state = {
                "session_id": session_id,
                "lesson_id": lesson.public_id,
                "topic_index": 0,
                "slide_index": 0,
                "total_topics": total_topics,
                "status": "active",
                "player_mode": player_mode,
                "completion_percentage": (
                    round(((0 + 1) / total_topics) * 100.0, 1) if total_topics > 0 else 0.0
                ),
            }
            _SESSIONS.set(session_id, session_state)
            return {
                "lesson": self._serialize_lesson(lesson),
                "version": self._serialize_version(version, lesson.public_id) if version else None,
                "topics": topics,
                "source_units": source_units,
                "presentation": presentation_info,
                "learning_structure": learning_structure,
                "session": session_state,
            }

        session_total_slides = self._session_total_slides(
            session.player_mode or PlayerMode.LEARNING.value, len(source_units), total_topics
        )
        return {
            "lesson": self._serialize_lesson(lesson),
            "version": self._serialize_version(version, lesson.public_id) if version else None,
            "topics": topics,
            "source_units": source_units,
            "presentation": presentation_info,
            "learning_structure": learning_structure,
            "session": self._progress.to_player_session(
                session,
                total_topics,
                lesson_public_id=lesson.public_id,
                total_slides=session_total_slides,
            ),
        }

    async def set_position(
        self,
        session_id: str,
        slide_index: int,
        *,
        owner_id: str | None = None,
        player_mode: str = PlayerMode.LEARNING.value,
    ) -> dict[str, Any] | None:
        """Set the user's absolute slide position in a persistent session.

        Mode-aware slide-accurate resume:
        - ``learning``: slide_index = topic_index * 2 (+0 | +1)
        - ``source``: slide_index counts against the uploaded source deck and
          is mapped onto topics via the topic outline so the final source slide
          reaches 100%.

        Returns None when the session is absent or belongs to another user.
        """
        if owner_id is None:
            return None
        lesson_id = await self._lesson_id_for_session(session_id, owner_id)
        if lesson_id is None:
            return None
        total = await self._topic_count_for_lesson(lesson_id)
        mode = player_mode or PlayerMode.LEARNING.value
        source_units = []
        source_topic_map: list[int] | None = None
        learning_structure = None
        if mode == PlayerMode.SOURCE.value:
            lesson = await self._lesson_repo.get(lesson_id)
            if lesson and lesson.presentation_id:
                source_units = await self._load_source_units(lesson.presentation_id)
                # The outline is (re)loaded by presentation id; the presentation
                # row itself is not needed for the source topic mapping (avoiding
                # a lazy relationship load on the async session).
                learning_structure = await self._load_learning_structure(
                    lesson.presentation_id, None
                )
                source_topic_map = self._build_source_topic_map(
                    source_units, learning_structure, total
                )
        total_slides = self._session_total_slides(mode, len(source_units), total)
        updated = await self._progress.set_slide_position(
            session_id=session_id,
            user_id=owner_id,
            slide_index=slide_index,
            total_slides=total_slides,
            player_mode=mode,
            source_topic_map=source_topic_map,
        )
        if updated is None:
            return None
        return self._progress.to_player_session(updated, total, total_slides=total_slides)

    async def advance_topic(
        self,
        session_id: str,
        *,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        # Every path either returns a session payload or raises ValueError, so
        # this never returns None. Callers may safely splat the result.
        if owner_id:
            lesson_id = await self._lesson_id_for_session(session_id, owner_id)
            if lesson_id is None:
                raise ValueError(f"Session {session_id} not found")
            total = await self._topic_count_for_lesson(lesson_id)
            updated = await self._progress.advance(
                session_id=session_id,
                user_id=owner_id,
                total_topics=total,
            )
            if updated is None:
                raise ValueError(f"Session {session_id} not found")
            return self._progress.to_player_session(updated, total, total_slides=total * 2)

        # Anonymous path: mutate in-memory transient session
        state = _SESSIONS.get(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")
        idx = state.get("topic_index", 0) + 1
        total = state.get("total_topics", 0)
        capped = max(0, min(idx, max(0, total - 1)))
        state["topic_index"] = capped
        state["completion_percentage"] = (
            round(((capped + 1) / total) * 100.0, 1) if total > 0 else 0.0
        )
        state["status"] = "completed" if total > 0 and capped >= total - 1 else "active"
        _SESSIONS.set(session_id, state)
        return state

    async def set_topic(
        self,
        session_id: str,
        topic_index: int,
        *,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        if owner_id:
            lesson_id = await self._lesson_id_for_session(session_id, owner_id)
            if lesson_id is None:
                raise ValueError(f"Session {session_id} not found")
            total = await self._topic_count_for_lesson(lesson_id)
            updated = await self._progress.set_topic(
                session_id=session_id,
                user_id=owner_id,
                topic_index=topic_index,
                total_topics=total,
            )
            if updated is None:
                raise ValueError(f"Session {session_id} not found")
            return self._progress.to_player_session(updated, total, total_slides=total * 2)

        # Anonymous path: mutate in-memory transient session
        state = _SESSIONS.get(session_id)
        if state is None:
            raise ValueError(f"Session {session_id} not found")
        total = state.get("total_topics", 0)
        capped = max(0, min(topic_index, max(0, total - 1)))
        state["topic_index"] = capped
        state["completion_percentage"] = (
            round(((capped + 1) / total) * 100.0, 1) if total > 0 else 0.0
        )
        state["status"] = "completed" if total > 0 and capped >= total - 1 else "active"
        _SESSIONS.set(session_id, state)
        return state

    # ── Assessment checkpoint ─────────────────────────────────────────────────

    async def get_checkpoint(
        self,
        lesson_public_id: str,
        *,
        owner_id: str,
    ) -> dict[str, Any]:
        """Return the assessment checkpoint for a lesson, if one exists.

        The checkpoint is the existing ``Quiz`` bound to the lesson (``lesson_id``).
        Ownership of the lesson is asserted first; the learner's own attempt
        history (scoped to ``owner_id``) is aggregated to report completion
        without exposing another user's attempts.
        """
        lesson = await self._assert_lesson_ownership(lesson_public_id, owner_id)
        quiz_repo = QuizRepository(self._uow.session)
        quizzes = await quiz_repo.list_by_lesson(lesson.id)
        if not quizzes:
            return {
                "has_checkpoint": False,
                "quiz": None,
                "completed": False,
                "latest_attempt": None,
                "available_attempts": 0,
            }

        quiz = quizzes[0]
        attempt_repo = QuizAttemptRepository(self._uow.session)
        attempts = await attempt_repo.list_by_quiz_and_user(quiz.id, uuid.UUID(str(owner_id)))
        completed = [a for a in attempts if a.status == "completed"]
        latest = completed[0] if completed else None
        latest_summary = None
        if latest is not None:
            passing = quiz.passing_score
            percent = float(latest.percent_score) if latest.percent_score is not None else None
            passed = None
            if passing is not None and percent is not None:
                passed = percent >= float(passing)
            latest_summary = {
                "attempt_id": latest.public_id,
                "attempt_number": latest.attempt_number,
                "percent_score": percent,
                "passed": passed,
                "score": float(latest.score) if latest.score is not None else None,
                "max_score": float(latest.max_score) if latest.max_score is not None else None,
                "completed_at": latest.completed_at,
            }

        return {
            "has_checkpoint": True,
            "quiz": {
                "id": quiz.public_id,
                "title": quiz.title,
                "description": quiz.description,
                "mode": quiz.mode,
                "status": quiz.status,
                "question_count": quiz.question_count,
                "passing_score": float(quiz.passing_score) if quiz.passing_score else None,
                "max_attempts_per_user": quiz.max_attempts_per_user,
            },
            "completed": len(completed) > 0,
            "latest_attempt": latest_summary,
            "available_attempts": max(0, (quiz.max_attempts_per_user or 0) - len(attempts)),
        }

    # ── Mastery + next learning action ───────────────────────────────────────

    async def get_mastery_and_next_action(
        self,
        lesson_public_id: str,
        *,
        owner_id: str,
    ) -> dict[str, Any]:
        """Surface the learner's mastery and a deterministic next action.

        Reuses ``educational_memory_service`` (DB-backed concept mastery) and
        ``recommendation_engine.generate_recommendations`` (deterministic,
        mastery-driven NextAction) — no new algorithm is introduced.
        """
        await self._assert_lesson_ownership(lesson_public_id, owner_id)

        from app.services.educational_memory_service import (
            educational_memory_service,
        )
        from app.services.recommendation_engine import generate_recommendations

        user_str = str(owner_id)
        memory = await educational_memory_service.load_from_db(self._uow.session, user_str)
        recommendation = generate_recommendations(user_str, memory)

        top_action = recommendation.actions[0] if recommendation.actions else None
        return {
            "average_mastery": memory.profile.average_mastery,
            "mastered_count": len(recommendation.mastered_concepts),
            "developing_count": len(recommendation.developing_concepts),
            "weak_count": len(recommendation.weak_concepts),
            "concept_mastery": recommendation.concept_mastery,
            "summary": recommendation.summary,
            "next_action": (
                {
                    "action_type": top_action.action_type.value,
                    "concept_id": top_action.concept_id,
                    "concept_name": top_action.concept_name,
                    "title": top_action.title,
                    "description": top_action.description,
                    "reason": top_action.reason,
                    "activity_type": top_action.activity_type.value,
                    "priority": top_action.priority.value,
                }
                if top_action is not None
                else None
            ),
        }

    # ── Internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _session_total_slides(
        player_mode: str, source_count: int, total_topics: int
    ) -> int:
        """Slide count of the deck a mode-relative position is indexed against."""
        if (player_mode or PlayerMode.LEARNING.value) == PlayerMode.SOURCE.value:
            return max(source_count, 1)
        # Learning deck is exactly one concept + one visual slide per topic.
        # Source-unit count is irrelevant to learning-mode completion: inflating
        # the denominator with uploaded-source length would cap completion below
        # 100% whenever source slides outnumber 2 * topics.
        return max(total_topics * 2, 1)

    def _build_source_topic_map(
        self,
        source_units: list[dict[str, Any]],
        learning_structure: dict[str, Any] | None,
        total_topics: int,
    ) -> list[int]:
        """Map each source slide (in deck order) onto a topic index.

        Uses the topic outline's 1-based ``slide_ranges`` matched against each
        source unit's ``position`` where available, so a contiguous multi-slide
        topic keeps its slides until the topic's last slide; otherwise falls
        back to an even split. Either way the FINAL source slide is pinned to
        the last topic so source-mode completion reaches 100%.
        """
        if not source_units or total_topics <= 0:
            return []
        ranges: list[tuple[int, int]] = []
        outline_topics = (learning_structure.get("topics") or []) if learning_structure else []
        for topic in outline_topics:
            if not isinstance(topic, dict):
                continue
            sr = topic.get("slide_ranges")
            if isinstance(sr, (list, tuple)) and len(sr) >= 2:
                try:
                    ranges.append((int(sr[0]), int(sr[1])))
                except (TypeError, ValueError):
                    continue

        mapping: list[int] = []
        for idx, unit in enumerate(source_units):
            raw_pos = unit.get("position")
            try:
                # A missing position falls back to the ordinal, matching the
                # original `int(None)` -> TypeError behaviour explicitly.
                pos = int(raw_pos) if raw_pos is not None else idx + 1
            except (TypeError, ValueError):
                pos = idx + 1
            topic_index = next(
                (ti for ti, (start, end) in enumerate(ranges) if start <= pos <= end),
                None,
            )
            if topic_index is None:
                break
            mapping.append(topic_index)

        if len(mapping) != len(source_units):
            size = len(source_units)
            mapping = [min(int(i * total_topics / size), total_topics - 1) for i in range(size)]
        if mapping:
            mapping[-1] = total_topics - 1
        return mapping

    async def _lesson_id_for_session(self, session_id: str, owner_id: str) -> uuid.UUID | None:
        session = await self._progress.find_by_public_id(session_id, user_id=owner_id)
        if session is None:
            return None
        return session.lesson_id

    async def _topic_count_for_lesson(self, lesson_id: uuid.UUID) -> int:
        version = await self._version_repo.get_latest_succeeded_for_lesson(lesson_id)
        if version is not None and len(version.blocks) > 0:
            return len(version.blocks)
        lesson = await self._lesson_repo.get(lesson_id)
        if lesson and lesson.presentation_id:
            from app.repositories.content_repository import ContentUnitRepository

            repo = ContentUnitRepository(self._uow.session)
            return await repo.count_for_presentation(lesson.presentation_id)
        return 0

    async def _resolve_version(self, lesson: GeneratedLesson) -> GeneratedLessonVersion | None:
        version = await self._version_repo.get_latest_succeeded_for_lesson(lesson.id)
        if version is None and lesson.latest_version > 0:
            version = await self._version_repo.get_by_lesson_and_version(
                lesson.id, lesson.latest_version
            )
        return version

    def _extract_topics(
        self,
        version: GeneratedLessonVersion | None,
        learning_structure: dict[str, Any] | None = None,
        topic_visuals: dict[str, list[dict[str, Any]]] | None = None,
        topic_animations: dict[str, list[dict[str, Any]]] | None = None,
    ) -> list[dict[str, Any]]:
        outline_topics = (learning_structure.get("topics") or []) if learning_structure else []
        outline_map = {
            t["title"].lower(): t for t in outline_topics if isinstance(t, dict) and "title" in t
        }
        topic_visuals = topic_visuals or {}
        topic_animations = topic_animations or {}

        topics = []
        if version and version.blocks:
            for idx, block in enumerate(version.blocks):
                heading = block.heading or f"Topic {block.position + 1}"
                outline_match = outline_map.get(heading.lower()) or (
                    outline_topics[idx] if idx < len(outline_topics) else None
                )
                topic_dict = {
                    "index": block.position,
                    "title": heading,
                    "description": block.content or "",
                    "block_id": block.public_id,
                }
                if outline_match and isinstance(outline_match, dict):
                    topic_dict["section"] = outline_match.get("section")
                    topic_dict["subtopics"] = outline_match.get("subtopics") or []
                    topic_dict["concepts"] = outline_match.get("concepts") or []
                    topic_dict["learning_objectives"] = (
                        outline_match.get("learning_objectives") or []
                    )
                    topic_dict["source_references"] = outline_match.get("source_references") or []
                outline_title = (
                    str(outline_match.get("title") or "")
                    if outline_match and isinstance(outline_match, dict)
                    else ""
                )
                topic_dict["outline_title"] = outline_title or heading
                topic_dict["visuals"] = topic_visuals.get((outline_title or heading).lower(), [])
                topic_dict["animations"] = topic_animations.get(
                    (outline_title or heading).lower(), []
                )
                topics.append(topic_dict)
        elif outline_topics:
            for idx, ot in enumerate(outline_topics):
                if isinstance(ot, dict):
                    key = str(ot.get("title", "")).lower()
                    topics.append(
                        {
                            "index": idx,
                            "title": ot.get("title", f"Topic {idx + 1}"),
                            "description": ", ".join(
                                c.get("name", "") for c in (ot.get("concepts") or [])[:3]
                            ),
                            "block_id": None,
                            "section": ot.get("section"),
                            "subtopics": ot.get("subtopics") or [],
                            "concepts": ot.get("concepts") or [],
                            "learning_objectives": ot.get("learning_objectives") or [],
                            "source_references": ot.get("source_references") or [],
                            "visuals": topic_visuals.get(key, []),
                            "animations": topic_animations.get(key, []),
                        }
                    )
        return topics

    async def _load_topic_visuals(
        self, presentation_id: uuid.UUID | None
    ) -> dict[str, list[dict[str, Any]]]:
        """Map ready C3 visuals to player topics by topic title (case-insensitive)."""
        if not presentation_id:
            return {}
        from app.repositories.topic_visual_asset_repository import (
            TopicVisualAssetRepository,
        )

        repo = TopicVisualAssetRepository(self._uow.session)
        assets = await repo.get_ready_assets_for_presentation(presentation_id)

        by_topic: dict[str, list[dict[str, Any]]] = {}
        for asset in assets:
            key = str(asset.topic_title or "").lower()
            by_topic.setdefault(key, []).append(self._serialize_visual_for_player(asset))
        for values in by_topic.values():
            values.sort(key=lambda v: str(v.get("title") or ""))
        return by_topic

    @staticmethod
    def _serialize_visual_for_player(asset: Any) -> dict[str, Any]:
        concept_ids = asset.concept_ids or []
        prefix = f"{asset.topic_id or ''}:"
        concepts = [cid[len(prefix) :] if cid.startswith(prefix) else cid for cid in concept_ids]
        return {
            "visual_id": str(asset.id),
            "public_id": asset.public_id,
            "visual_type": asset.visual_type,
            "title": asset.title,
            "purpose": asset.purpose or "",
            "learning_objective": asset.learning_objective or "",
            "asset_format": asset.asset_format,
            "topic_id": asset.topic_id,
            "topic_title": asset.topic_title,
            "subtopic_id": asset.subtopic_id,
            "subtopic_title": asset.subtopic_title,
            "provenance": asset.provenance,
            "concepts": concepts,
            "concept_ids": concept_ids,
            "explanation": asset.explanation or {},
            "svg_content": asset.asset_content,
        }

    async def _load_topic_animations(
        self, presentation_id: uuid.UUID | None
    ) -> dict[str, list[dict[str, Any]]]:
        """Map ready C4 animations to player topics by topic title."""
        if not presentation_id:
            return {}
        from app.repositories.topic_animation_asset_repository import (
            TopicAnimationAssetRepository,
        )

        repo = TopicAnimationAssetRepository(self._uow.session)
        assets = await repo.get_ready_assets_for_presentation(presentation_id)

        by_topic: dict[str, list[dict[str, Any]]] = {}
        for asset in assets:
            key = str(asset.topic_title or "").lower()
            by_topic.setdefault(key, []).append(self._serialize_animation_for_player(asset))
        for values in by_topic.values():
            values.sort(key=lambda v: str(v.get("title") or ""))
        return by_topic

    @staticmethod
    def _serialize_animation_for_player(asset: Any) -> dict[str, Any]:
        concept_ids = asset.concept_ids or []
        prefix = f"{asset.topic_id or ''}:"
        concepts = [cid[len(prefix) :] if cid.startswith(prefix) else cid for cid in concept_ids]
        spec = asset.specification or {}
        return {
            "animation_id": str(asset.id),
            "asset_id": str(asset.id),
            "public_id": asset.public_id,
            "animation_type": asset.animation_type,
            "title": asset.title,
            "purpose": asset.purpose or "",
            "learning_objective": asset.learning_objective or "",
            "asset_format": asset.asset_format,
            "topic_id": asset.topic_id,
            "topic_title": asset.topic_title,
            "subtopic_id": asset.subtopic_id,
            "subtopic_title": asset.subtopic_title,
            "provenance": asset.provenance,
            "confidence": asset.confidence,
            "concepts": concepts,
            "concept_ids": concept_ids,
            "explanation": asset.explanation or {},
            "specification": spec,
            "source_references": asset.source_references or [],
            "package_content": asset.package_content or "",
            "pedagogical_rationale": spec.get("pedagogical_rationale") or "",
        }

    def _serialize_lesson(self, lesson: GeneratedLesson) -> dict[str, Any]:
        pres_public_id = None
        if hasattr(lesson, "presentation") and lesson.presentation is not None:
            pres_public_id = getattr(lesson.presentation, "public_id", None)
        return {
            "id": lesson.public_id,
            "presentation_id": pres_public_id,
            "mode": lesson.mode,
            "status": lesson.status,
            "title": lesson.title,
            "language": lesson.language,
            "difficulty": lesson.difficulty,
            "latest_version": lesson.latest_version,
        }

    def _serialize_version(
        self, version: GeneratedLessonVersion, lesson_public_id: str
    ) -> dict[str, Any]:
        return {
            "id": version.public_id,
            "lesson_id": lesson_public_id,
            "version": version.version,
            "status": version.status,
            "title": version.title,
            "summary": version.summary,
            "language": version.language,
            "difficulty": version.difficulty,
            "model": version.model,
            "completed_at": version.completed_at,
        }

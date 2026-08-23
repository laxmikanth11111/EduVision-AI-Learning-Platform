"""Learning Context Manager Service.

Centralized state manager serving as the single source of truth for learner sessions.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.schemas.learning_context import (
    ContextEvent,
    LearningContext,
    LearningState,
)

logger = get_logger(__name__)


class LearningContextService:

    def __init__(self) -> None:
        self._contexts: dict[str, LearningContext] = {}

    def create_session(
        self,
        topic: str,
        user_id: str | None = None,
        course_id: str | None = None,
        lesson_id: str | None = None,
        canvas_id: str | None = None,
    ) -> LearningContext:
        session_id = f"ctxsess_{uuid.uuid4().hex[:16]}"
        now = time.time()

        context = LearningContext(
            session_id=session_id,
            user_id=user_id,
            course_id=course_id,
            lesson_id=lesson_id,
            topic=topic,
            canvas_id=canvas_id,
            active_state=LearningState.NOT_STARTED,
            created_at=now,
            updated_at=now,
            timeline=[
                ContextEvent(
                    event_id=f"evt_{uuid.uuid4().hex[:8]}",
                    event_type="session_created",
                    timestamp=now,
                    state=LearningState.NOT_STARTED,
                    step_name="Lesson Initialization",
                    details={"topic": topic},
                )
            ],
        )

        self._contexts[session_id] = context
        logger.info("learning_context_session_created", session_id=session_id, topic=topic)
        return context

    def get_session(self, session_id: str) -> LearningContext:
        context = self._contexts.get(session_id)
        if not context:
            raise NotFoundError(
                message="Learning context session not found",
                details={"session_id": session_id},
            )
        return context

    def update_context(
        self, session_id: str, updates: dict[str, Any]
    ) -> LearningContext:
        context = self.get_session(session_id)

        # Merge updates
        for field, value in updates.items():
            if hasattr(context, field) and field not in ("session_id", "created_at", "timeline"):
                setattr(context, field, value)

        context.updated_at = time.time()
        return context

    def transition_state(
        self, session_id: str, new_state: LearningState, step_name: str | None = None
    ) -> LearningContext:
        context = self.get_session(session_id)
        old_state = context.active_state

        context.active_state = new_state
        context.updated_at = time.time()

        self.publish_event(
            session_id=session_id,
            event_type="state_transition",
            step_name=step_name or new_state.value,
            details={"from_state": old_state.value, "to_state": new_state.value},
        )

        return context

    def publish_event(
        self,
        session_id: str,
        event_type: str,
        step_name: str | None = None,
        component_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> LearningContext:
        context = self.get_session(session_id)
        now = time.time()

        evt = ContextEvent(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            event_type=event_type,
            timestamp=now,
            state=context.active_state,
            step_name=step_name,
            component_id=component_id or context.selected_component_id,
            details=details or {},
        )

        context.timeline.append(evt)
        context.updated_at = now

        # Update explored components if component event
        if component_id and component_id not in context.explored_components:
            context.explored_components.append(component_id)

        return context

    def export_context(self, session_id: str) -> dict[str, Any]:
        context = self.get_session(session_id)
        return context.model_dump()

    def import_context(self, snapshot: dict[str, Any]) -> LearningContext:
        context = LearningContext(**snapshot)
        self._contexts[context.session_id] = context
        return context


learning_context_service = LearningContextService()

"""Pluggable AI safety validation hooks for lesson generation.

The default implementation is a no-op. Production deployments can provide a
concrete validator (e.g. wired via ``AI_LESSON_SAFETY_VALIDATOR``) that checks
source content before generation and model output after generation. Results of
the applied checks are recorded in the version ``generation_metadata``.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.core.error_codes import ErrorCode
from app.core.exceptions import EduVisionError


class LessonSafetyError(EduVisionError):
    def __init__(
        self,
        message: str = "Content did not pass safety validation",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.SAFETY_ERROR,
            status_code=422,
            details=details,
        )


class LessonSafetyValidator(Protocol):
    """Validates input source content and generated output.

    Implementations should be stateless or inject dependencies via __init__.
    Raising ``LessonSafetyError`` blocks the generation (input) or fails the
    version with ``error_code="safety_rejected"`` (output).
    """

    name: str

    async def validate_input(
        self,
        *,
        source_context: Any,
        request: Any,
        presentation_id: str,
    ) -> None:
        """Raise LessonSafetyError to reject generation for unsafe source."""
        ...

    async def validate_output(
        self,
        *,
        payload: Any,
        source_context: Any,
        request: Any,
    ) -> None:
        """Raise LessonSafetyError to reject generated output."""
        ...


class NoopLessonSafetyValidator:
    """Default validator: accepts everything. Extension point for production."""

    name = "noop"

    async def validate_input(
        self,
        *,
        source_context: Any,
        request: Any,
        presentation_id: str,
    ) -> None:
        return None

    async def validate_output(
        self,
        *,
        payload: Any,
        source_context: Any,
        request: Any,
    ) -> None:
        return None


def build_safety_validator(name: str) -> LessonSafetyValidator:
    """Resolve a validator by name; unknown names fall back to no-op."""
    if not name or name == "noop":
        return NoopLessonSafetyValidator()
    return NoopLessonSafetyValidator()

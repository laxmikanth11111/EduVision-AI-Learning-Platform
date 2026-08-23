"""Validation Layer for Phase 4I.2 Visual Intelligence Engine.

Validates input content and intermediate visual models for empty text, insufficient
detail, missing components, unconnected graphs, or ambiguous content.
"""

from __future__ import annotations

from app.schemas.visual_intelligence import (
    VisualLearningModel,
    VisualValidationError,
    VisualValidationResult,
)


class VisualValidationService:

    def validate_content(self, content: str, title: str | None = None) -> VisualValidationResult:
        """Validate raw input content before sending to visual intelligence pipeline."""
        errors: list[VisualValidationError] = []
        warnings: list[str] = []

        cleaned = content.strip() if content else ""

        if not cleaned:
            errors.append(
                VisualValidationError(
                    code="EMPTY_CONTENT",
                    message="Content cannot be empty or whitespace-only.",
                    details={"content_length": 0},
                )
            )
            return VisualValidationResult(is_valid=False, errors=errors)

        if len(cleaned) < 20:
            errors.append(
                VisualValidationError(
                    code="CONTENT_TOO_SHORT",
                    message="Content is too short to generate a meaningful visual learning model (minimum 20 characters).",
                    details={"content_length": len(cleaned)},
                )
            )

        if len(cleaned) > 100000:
            warnings.append("Content exceeds 100,000 characters; text will be truncated for visual intelligence analysis.")

        return VisualValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_model(self, model: VisualLearningModel) -> VisualValidationResult:
        """Validate the generated VisualLearningModel for structural completeness."""
        errors: list[VisualValidationError] = []
        warnings: list[str] = []

        if not model.components:
            errors.append(
                VisualValidationError(
                    code="MISSING_COMPONENTS",
                    message="Generated visual model contains zero components.",
                    details={"topic": model.topic},
                )
            )

        if len(model.components) > 1 and not model.relationships:
            warnings.append("Multi-component graph has no detected relationships; falling back to sequential chain.")

        if not model.visual_nodes:
            errors.append(
                VisualValidationError(
                    code="MISSING_VISUAL_NODES",
                    message="Generated visual model contains no visual node schemas for rendering.",
                    details={"topic": model.topic},
                )
            )

        return VisualValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

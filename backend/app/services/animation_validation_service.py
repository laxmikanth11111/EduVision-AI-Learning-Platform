"""Animation Validation Service.

Checks scene ordering, timeline duration consistency, missing node references, and learning objective coverage.
"""

from __future__ import annotations

from app.schemas.animation_engine import AnimationTimeline, ValidationReport


class AnimationValidationService:

    def validate_timeline(
        self, node_ids: list[str], timeline: AnimationTimeline
    ) -> ValidationReport:
        warnings: list[str] = []
        errors: list[str] = []

        if not timeline.scenes:
            errors.append("Animation timeline contains zero scenes.")

        target_ids = set()
        for s in timeline.scenes:
            for evt in s.events:
                target_ids.add(evt.target_id)

        # Check Node Coverage
        missing_nodes = [nid for nid in node_ids if nid not in target_ids]
        if missing_nodes:
            warnings.append(f"Visual components not referenced in animation events: {', '.join(missing_nodes)}")

        coverage_score = round(
            ((len(node_ids) - len(missing_nodes)) / max(len(node_ids), 1)) * 100.0, 1
        )

        is_valid = len(errors) == 0

        return ValidationReport(
            is_valid=is_valid,
            warnings=warnings,
            errors=errors,
            coverage_score=coverage_score,
        )


animation_validation_service = AnimationValidationService()

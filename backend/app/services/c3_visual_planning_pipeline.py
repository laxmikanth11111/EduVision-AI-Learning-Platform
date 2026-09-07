"""C3 Visual Planning Pipeline — orchestrates topic-level visual generation.

Connects the C2 topic outline hierarchy with visual need analysis,
specification generation, SVG rendering, validation, persistence,
and lifecycle management.

Pipeline: C2 Topics → Visual Need → Specification → Rendering → Validation → Storage
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.core.logging import get_logger
from app.repositories.topic_visual_asset_repository import TopicVisualAssetRepository
from app.schemas.c3_visual_intelligence import (
    C3VisualType,
    PresentationVisualPlan,
    TopicVisualPlan,
    VisualAsset,
    VisualExplanation,
    VisualSourceProvenance,
    VisualSpecification,
    VisualStatus,
    compute_visual_fingerprint,
)
from app.schemas.topic_outline import OutlineTopic, Subtopic
from app.services.c3_svg_renderer import render_visual
from app.services.c3_visual_need_analyzer import analyze_visual_need
from app.services.c3_visual_spec_generator import generate_visual_specification

logger = get_logger(__name__)

# Maximum visuals to generate per presentation (bounded concurrency)
MAX_VISUALS_PER_PRESENTATION = 50


class C3VisualPlanningPipeline:
    """Orchestrates the complete C3 visual generation pipeline."""

    def __init__(self, asset_repo: TopicVisualAssetRepository | None = None) -> None:
        self._repo = asset_repo

    async def plan_presentation_visuals(
        self,
        presentation_id: str,
        user_id: uuid.UUID,
        topics: list[OutlineTopic],
        *,
        force_regenerate: bool = False,
    ) -> PresentationVisualPlan:
        """Plan and generate visuals for all topics in a presentation.

        This is the main entry point for C3 visual generation.
        Called after C2 topic outline generation completes.
        """
        start_time = time.monotonic()
        pres_id = presentation_id

        topic_plans: list[TopicVisualPlan] = []
        visuals_planned = 0
        visuals_skipped = 0
        total_subtopics = 0

        for topic in topics:
            # Plan visuals for subtopics
            if topic.subtopics:
                for subtopic in topic.subtopics:
                    total_subtopics += 1

                    if visuals_planned >= MAX_VISUALS_PER_PRESENTATION:
                        logger.warning(
                            "c3_visual_limit_reached",
                            presentation_id=pres_id,
                            limit=MAX_VISUALS_PER_PRESENTATION,
                        )
                        break

                    plan = await self._plan_single_visual(
                        presentation_id=pres_id,
                        user_id=user_id,
                        topic=topic,
                        subtopic=subtopic,
                        force_regenerate=force_regenerate,
                    )
                    topic_plans.append(plan)

                    if plan.visual_needed:
                        visuals_planned += 1
                    else:
                        visuals_skipped += 1
            else:
                # No subtopics — plan for the topic itself
                total_subtopics += 1

                if visuals_planned >= MAX_VISUALS_PER_PRESENTATION:
                    logger.warning(
                        "c3_visual_limit_reached",
                        presentation_id=pres_id,
                        limit=MAX_VISUALS_PER_PRESENTATION,
                    )
                    continue

                plan = await self._plan_single_visual(
                    presentation_id=pres_id,
                    user_id=user_id,
                    topic=topic,
                    subtopic=None,
                    force_regenerate=force_regenerate,
                )
                topic_plans.append(plan)

                if plan.visual_needed:
                    visuals_planned += 1
                else:
                    visuals_skipped += 1

        duration_ms = int((time.monotonic() - start_time) * 1000)

        result = PresentationVisualPlan(
            presentation_id=pres_id,
            total_topics=len(topics),
            total_subtopics=total_subtopics,
            visuals_planned=visuals_planned,
            visuals_skipped=visuals_skipped,
            topic_plans=topic_plans,
            generation_metadata={
                "duration_ms": duration_ms,
                "max_per_presentation": MAX_VISUALS_PER_PRESENTATION,
            },
        )

        logger.info(
            "c3_visual_planning_completed",
            presentation_id=pres_id,
            visuals_planned=visuals_planned,
            visuals_skipped=visuals_skipped,
            duration_ms=duration_ms,
        )

        return result

    async def generate_and_persist_visual(
        self,
        plan: TopicVisualPlan,
        presentation_id: str,
        user_id: uuid.UUID,
        *,
        force_regenerate: bool = False,
    ) -> VisualAsset | None:
        """Generate a single visual from a plan and persist it.

        Returns the generated VisualAsset, or None if skipped.
        """
        if not plan.visual_needed or not plan.specification:
            return None

        start_time = time.monotonic()
        pres_uuid = (
            uuid.UUID(presentation_id) if isinstance(presentation_id, str) else presentation_id
        )

        # Check for existing ready asset (deduplication)
        if not force_regenerate and self._repo:
            fingerprint = compute_visual_fingerprint(
                presentation_id,
                plan.topic_id,
                plan.subtopic_id,
                plan.concept_ids,
            )
            existing = await self._repo.get_ready_by_fingerprint(fingerprint)
            if existing:
                logger.info("c3_visual_cache_hit", fingerprint=fingerprint)
                return self._model_to_asset(existing)

        # Update status to generating
        if plan.specification:
            plan.status = VisualStatus.GENERATING

        # Render the visual
        try:
            svg_content = render_visual(plan.specification)
            asset_format = "svg"
        except Exception as exc:
            logger.error("c3_visual_render_failed", error=str(exc))
            plan.status = VisualStatus.FAILED
            plan.error_message = str(exc)
            return None

        # Validate the rendered output
        validation = self._validate_rendered_output(svg_content, plan.specification)
        if not validation["valid"]:
            logger.warning("c3_visual_validation_failed", errors=validation["errors"])
            plan.status = VisualStatus.FAILED
            plan.error_message = "; ".join(validation["errors"])
            return None

        plan.status = VisualStatus.VALIDATING

        # Build explanation
        explanation = self._build_explanation(plan.specification, plan)

        # Compute fingerprint
        fingerprint = compute_visual_fingerprint(
            presentation_id,
            plan.topic_id,
            plan.subtopic_id,
            plan.concept_ids,
        )

        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Persist to database
        asset_id = str(uuid.uuid4())
        if self._repo:
            # Create DB record
            asset = await self._repo.create(
                presentation_id=pres_uuid,
                user_id=user_id,
                topic_id=plan.topic_id,
                topic_title=plan.topic_title,
                subtopic_id=plan.subtopic_id,
                subtopic_title=plan.subtopic_title,
                visual_type=plan.visual_type.value
                if plan.visual_type
                else C3VisualType.CONCEPT_MAP.value,
                status="ready",
                version=1,
                fingerprint=fingerprint,
                asset_format=asset_format,
                asset_content=svg_content,
                title=plan.specification.title,
                purpose=plan.specification.purpose,
                learning_objective=plan.specification.learning_objective,
                provenance=plan.provenance.value,
                confidence=plan.confidence,
                specification=plan.specification.model_dump(mode="json"),
                explanation=explanation.model_dump(mode="json"),
                source_references=plan.source_references,
                concept_ids=plan.concept_ids,
                generation_metadata={
                    "duration_ms": duration_ms,
                    "provider": "deterministic_svg",
                    "renderer": "c3_svg_engine",
                },
            )
            asset_id = str(asset.id)

            # Supersede old versions
            await self._repo.supersede_old_version(fingerprint, asset.id)

            logger.info(
                "c3_visual_generated",
                asset_id=asset_id,
                visual_type=plan.visual_type.value if plan.visual_type else "unknown",
                duration_ms=duration_ms,
            )

            return self._model_to_asset(asset)

        # Fallback: return in-memory asset if no repo
        return VisualAsset(
            id=asset_id,
            visual_type=plan.visual_type or C3VisualType.CONCEPT_MAP,
            title=plan.specification.title,
            status=VisualStatus.READY,
            asset_format="svg",
            asset_content=svg_content,
            specification=plan.specification,
            explanation=explanation,
            provenance=plan.provenance,
            source_references=plan.source_references,
            concept_ids=plan.concept_ids,
            presentation_id=presentation_id,
            topic_id=plan.topic_id,
            subtopic_id=plan.subtopic_id,
            version=1,
            fingerprint=fingerprint,
            generation_duration_ms=duration_ms,
            provider="deterministic_svg",
        )

    # ── Private Helpers ────────────────────────────────────────────────────

    async def _plan_single_visual(
        self,
        presentation_id: str,
        user_id: uuid.UUID,
        topic: OutlineTopic,
        subtopic: Subtopic | None,
        *,
        force_regenerate: bool = False,
    ) -> TopicVisualPlan:
        """Plan a single visual for a topic/subtopic."""
        target = subtopic or topic
        content = _build_content_string(target)

        # Analyze visual need
        concepts_dicts = [
            {"name": c.name, "description": c.description}
            for c in (subtopic.concepts if subtopic else topic.concepts)
        ]

        need_decision = analyze_visual_need(
            topic_title=topic.title,
            topic_content=content,
            subtopic_title=subtopic.title if subtopic else None,
            subtopic_content=content,
            concepts=concepts_dicts,
            source_references=[
                {"slide_number": ref.slide_number, "preview": ref.preview}
                for ref in target.source_references
            ]
            if hasattr(target, "source_references")
            else None,
        )

        concept_ids = [
            f"{topic.title}:{c.name}" for c in (subtopic.concepts if subtopic else topic.concepts)
        ]

        source_refs = [
            {"slide_number": ref.slide_number, "preview": ref.preview}
            for ref in (target.source_references if hasattr(target, "source_references") else [])
        ]

        if not need_decision.visual_needed:
            return TopicVisualPlan(
                topic_id=topic.title,
                topic_title=topic.title,
                subtopic_id=subtopic.title if subtopic else None,
                subtopic_title=subtopic.title if subtopic else None,
                visual_needed=False,
                confidence=need_decision.confidence,
                source_references=source_refs,
                concept_ids=concept_ids,
                status=VisualStatus.PLANNED,
            )

        # Generate specification
        visual_type = need_decision.suggested_type or C3VisualType.CONCEPT_MAP
        specification = generate_visual_specification(
            topic=topic,
            subtopic=subtopic,
            visual_type=visual_type,
        )

        # Generate explanation
        explanation = self._build_explanation_for_plan(specification, topic, subtopic)

        return TopicVisualPlan(
            topic_id=topic.title,
            topic_title=topic.title,
            subtopic_id=subtopic.title if subtopic else None,
            subtopic_title=subtopic.title if subtopic else None,
            visual_needed=True,
            visual_type=visual_type,
            specification=specification,
            explanation=explanation,
            source_references=source_refs,
            concept_ids=concept_ids,
            confidence=need_decision.confidence,
            provenance=VisualSourceProvenance.AI_EXPLAINED,
            status=VisualStatus.PLANNED,
        )

    @staticmethod
    def _validate_rendered_output(
        svg_content: str,
        spec: VisualSpecification,
    ) -> dict[str, Any]:
        """Validate the rendered SVG output."""
        errors: list[str] = []

        if not svg_content or len(svg_content) < 50:
            errors.append("Rendered output is too short or empty")

        if not svg_content.strip().startswith("<svg"):
            errors.append("Output is not valid SVG")

        if "font-family" not in svg_content:
            errors.append("SVG missing font-family declaration")

        # Check node count matches
        node_count = svg_content.count("<rect") + svg_content.count("<circle")
        if len(spec.nodes) > 0 and node_count < len(spec.nodes):
            errors.append(f"Expected at least {len(spec.nodes)} shapes, found {node_count}")

        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def _build_explanation(
        spec: VisualSpecification,
        plan: TopicVisualPlan,
    ) -> VisualExplanation:
        """Build a student-friendly explanation for a generated visual."""
        what = f"This diagram focuses on {spec.title}."
        how = "Read from top to bottom (or left to right) following the arrows."
        key = ""
        if spec.steps:
            key = f"The key steps are: {', '.join(s.title for s in spec.steps[:3])}."
        elif spec.nodes:
            key = f"The key elements are: {', '.join(n.label for n in spec.nodes[:3])}."

        return VisualExplanation(
            what_you_see=what,
            how_to_read=how,
            key_takeaway=key,
            real_world_example="",
            common_mistake="",
        )

    @staticmethod
    def _build_explanation_for_plan(
        spec: VisualSpecification,
        topic: OutlineTopic,
        subtopic: Subtopic | None,
    ) -> VisualExplanation:
        """Build explanation for a visual plan."""
        title = subtopic.title if subtopic else topic.title
        concepts = subtopic.concepts if subtopic else topic.concepts

        what = f"This {spec.visual_type.value.replace('_', ' ')} shows the structure and relationships in {title}."
        how = (
            f"Start from the center/top and follow the connections to understand how {title} works."
        )
        key = ""
        if concepts:
            key = f"Key concepts: {', '.join(c.name for c in concepts[:4])}."

        example = ""
        misconceptions = subtopic.misconceptions if subtopic else topic.misconceptions
        if misconceptions:
            example = f"Common mistake: {misconceptions[0].correction}"

        return VisualExplanation(
            what_you_see=what,
            how_to_read=how,
            key_takeaway=key,
            real_world_example="",
            common_mistake=example,
        )

    @staticmethod
    def _model_to_asset(model: Any) -> VisualAsset:
        """Convert a database model to a VisualAsset schema."""
        return VisualAsset(
            id=str(model.id),
            visual_type=C3VisualType(model.visual_type),
            title=model.title,
            status=VisualStatus(model.status),
            asset_format=model.asset_format,
            asset_url=model.asset_url,
            asset_key=model.asset_key,
            asset_content=getattr(model, "asset_content", None),
            specification=VisualSpecification(**model.specification)
            if model.specification
            else VisualSpecification(
                visual_type=C3VisualType.CONCEPT_MAP,
                title=model.title,
                purpose="",
            ),
            explanation=VisualExplanation(**model.explanation) if model.explanation else None,
            provenance=VisualSourceProvenance(model.provenance),
            source_references=model.source_references or [],
            concept_ids=model.concept_ids or [],
            presentation_id=str(model.presentation_id),
            topic_id=model.topic_id,
            subtopic_id=model.subtopic_id,
            version=model.version,
            fingerprint=model.fingerprint,
            created_at=model.created_at.isoformat() if model.created_at else None,
            generation_duration_ms=(model.generation_metadata or {}).get("duration_ms"),
            provider=(model.generation_metadata or {}).get("provider"),
            model=(model.generation_metadata or {}).get("model"),
        )


def _build_content_string(target: Any) -> str:
    """Build a text representation of a topic/subtopic for analysis."""
    parts: list[str] = []
    if hasattr(target, "title"):
        parts.append(target.title)
    if hasattr(target, "concepts"):
        for c in target.concepts:
            parts.append(c.name if hasattr(c, "name") else str(c))
            parts.append(c.description if hasattr(c, "description") else "")
    if hasattr(target, "learning_objectives"):
        parts.extend(target.learning_objectives)
    if hasattr(target, "examples"):
        for ex in target.examples:
            parts.append(ex.content if hasattr(ex, "content") else str(ex))
    return " ".join(parts)

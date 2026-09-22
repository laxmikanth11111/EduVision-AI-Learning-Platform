"""C4 Animation Planning Pipeline — orchestrates animation generation.

Connects ready C3 visual assets (the static foundation) with animation need
analysis, specification generation, package rendering, validation,
persistence, and lifecycle management.

Pipeline: C3 Visuals → Animation Need → Specification → Package → Validation →
Storage

Animations are always derived from an existing C3 visual foundation; a topic
without a ready visual asset is honestly skipped (nothing to animate).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.core.logging import get_logger
from app.repositories.topic_animation_asset_repository import (
    TopicAnimationAssetRepository,
)
from app.repositories.topic_visual_asset_repository import TopicVisualAssetRepository
from app.schemas.c3_visual_intelligence import C3VisualType
from app.schemas.c4_animation_intelligence import (
    AnimationAsset,
    AnimationSourceProvenance,
    AnimationSpecification,
    AnimationStatus,
    C4AnimationType,
    PresentationAnimationPlan,
    TopicAnimationPlan,
    compute_animation_fingerprint,
)
from app.schemas.topic_outline import OutlineTopic, Subtopic
from app.services.c3_visual_planning_pipeline import _build_content_string
from app.services.c4_animation_need_analyzer import analyze_animation_need
from app.services.c4_animation_renderer import render_animation_package
from app.services.c4_animation_spec_generator import (
    build_animation_explanation,
    generate_animation_specification,
)

logger = get_logger(__name__)

MAX_ANIMATIONS_PER_PRESENTATION = 16


class C4AnimationPlanningPipeline:
    """Orchestrates the complete C4 animation generation pipeline."""

    def __init__(
        self,
        asset_repo: TopicAnimationAssetRepository | None = None,
        c3_repo: TopicVisualAssetRepository | None = None,
    ) -> None:
        self._repo = asset_repo
        self._c3_repo = c3_repo

    async def plan_presentation_animations(
        self,
        presentation_id: str,
        user_id: uuid.UUID,
        topics: list[OutlineTopic],
        *,
        force_regenerate: bool = False,
    ) -> PresentationAnimationPlan:
        """Plan animations for all topics with ready C3 visual assets."""
        start_time = time.monotonic()
        pres_uuid = (
            uuid.UUID(presentation_id) if isinstance(presentation_id, str) else presentation_id
        )

        c3_lookup: dict[tuple[str, str], Any] = {}
        if self._c3_repo:
            try:
                assets, _ = await self._c3_repo.list_by_presentation(
                    pres_uuid, status="ready", page_size=500
                )
                for asset in assets:
                    c3_lookup[(asset.topic_id, asset.subtopic_id or "")] = asset
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("c4_c3_assets_load_failed", error=str(exc))

        topic_plans: list[TopicAnimationPlan] = []
        animations_planned = 0
        animations_skipped = 0
        total_subtopics = 0

        for topic in topics:
            if topic.subtopics:
                for subtopic in topic.subtopics:
                    total_subtopics += 1
                    if animations_planned >= MAX_ANIMATIONS_PER_PRESENTATION:
                        break
                    c3_asset = c3_lookup.get((topic.title, subtopic.title))
                    plan = self._plan_single_animation(
                        presentation_id=pres_uuid,
                        user_id=user_id,
                        topic=topic,
                        subtopic=subtopic,
                        c3_asset=c3_asset,
                        force_regenerate=force_regenerate,
                    )
                    topic_plans.append(plan)
                    if plan.animation_needed:
                        animations_planned += 1
                    else:
                        animations_skipped += 1
            else:
                total_subtopics += 1
                if animations_planned >= MAX_ANIMATIONS_PER_PRESENTATION:
                    continue
                c3_asset = c3_lookup.get((topic.title, ""))
                plan = self._plan_single_animation(
                    presentation_id=pres_uuid,
                    user_id=user_id,
                    topic=topic,
                    subtopic=None,
                    c3_asset=c3_asset,
                    force_regenerate=force_regenerate,
                )
                topic_plans.append(plan)
                if plan.animation_needed:
                    animations_planned += 1
                else:
                    animations_skipped += 1

        duration_ms = int((time.monotonic() - start_time) * 1000)
        result = PresentationAnimationPlan(
            presentation_id=presentation_id,
            total_topics=len(topics),
            animations_planned=animations_planned,
            animations_skipped=animations_skipped,
            topic_plans=topic_plans,
            generation_metadata={
                "duration_ms": duration_ms,
                "max_per_presentation": MAX_ANIMATIONS_PER_PRESENTATION,
                "foundation": "c3_visual_assets",
            },
        )
        logger.info(
            "c4_animation_planning_completed",
            presentation_id=presentation_id,
            animations_planned=animations_planned,
            animations_skipped=animations_skipped,
            duration_ms=duration_ms,
        )
        return result

    async def generate_and_persist_animation(
        self,
        plan: TopicAnimationPlan,
        presentation_id: str,
        user_id: uuid.UUID,
        *,
        force_regenerate: bool = False,
    ) -> AnimationAsset | None:
        """Generate a single animation from a plan and persist it."""
        if not plan.animation_needed or not plan.specification:
            return None

        start_time = time.monotonic()
        pres_uuid = (
            uuid.UUID(presentation_id) if isinstance(presentation_id, str) else presentation_id
        )

        fingerprint = compute_animation_fingerprint(
            presentation_id,
            plan.topic_id,
            plan.subtopic_id,
            plan.concept_ids,
        )

        spec = plan.specification
        specification = spec.model_dump(mode="json")
        version = 1
        persisted = None
        if self._repo:
            await self._repo.lock_generation(pres_uuid, user_id)
            existing = await self._repo.get_ready_by_fingerprint(fingerprint)
            if (not force_regenerate and existing
                    and existing.specification == specification):
                return self._model_to_asset(existing)
            version = await self._repo.next_version(fingerprint)
            persisted = await self._repo.create(
                presentation_id=pres_uuid, user_id=user_id,
                topic_id=plan.topic_id, topic_title=plan.topic_title,
                subtopic_id=plan.subtopic_id, subtopic_title=plan.subtopic_title,
                animation_type=spec.animation_type.value, status="generating",
                version=version, fingerprint=fingerprint, asset_format="html",
                title=spec.title, purpose=spec.purpose,
                learning_objective=spec.learning_objective,
                provenance=plan.provenance.value, confidence=plan.confidence,
                specification=specification, explanation={},
                source_references=plan.source_references, concept_ids=plan.concept_ids,
                generation_metadata={"progress": 0},
            )
        plan.status = AnimationStatus.GENERATING
        explanation = build_animation_explanation(spec.animation_type, spec, plan.topic_title)
        try:
            package_content = render_animation_package(
                spec, title=spec.title, topic_title=plan.topic_title, explanation=explanation,
            )
            validation = self._validate_animation_output(package_content, spec)
            if not validation["valid"]:
                raise ValueError("; ".join(validation["errors"]))
        except Exception:
            logger.exception("c4_animation_render_failed", topic=plan.topic_title)
            plan.status = AnimationStatus.FAILED
            plan.error_message = "We couldn't prepare this animation. Please try again."
            if self._repo and persisted:
                await self._repo.update(
                    persisted.id, status="failed", error_message=plan.error_message,
                    generation_metadata={"progress": 0, "stage": "render_or_validation"},
                )
            return None

        duration_ms = int((time.monotonic() - start_time) * 1000)
        plan.status = AnimationStatus.READY
        asset_id = str(uuid.uuid4())
        if self._repo and persisted:
            asset = await self._repo.update(
                persisted.id, status="ready", package_content=package_content,
                explanation=explanation,
                generation_metadata={
                    "duration_ms": duration_ms, "progress": 100,
                    "provider": "deterministic_package", "renderer": "c4_animation_renderer",
                },
            )
            await self._repo.supersede_old_version(fingerprint, asset.id)
            return self._model_to_asset(asset)
        return AnimationAsset(
            id=asset_id,
            animation_type=spec.animation_type,
            title=spec.title,
            status=AnimationStatus.READY,
            asset_format="html",
            package_content=package_content,
            specification=spec,
            pedagogical_rationale=spec.pedagogical_rationale,
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
        )

    # ── Private Helpers ────────────────────────────────────────────────────

    def _plan_single_animation(
        self,
        presentation_id: uuid.UUID,
        user_id: uuid.UUID,
        topic: OutlineTopic,
        subtopic: Subtopic | None,
        c3_asset: Any,
        *,
        force_regenerate: bool = False,
    ) -> TopicAnimationPlan:
        """Plan one animation for a topic/subtopic with a C3 foundation."""
        del presentation_id, user_id, force_regenerate
        target = subtopic or topic
        content = _build_content_string(target)

        source_refs = [
            ref.model_dump(mode="json", exclude_none=True)
            for ref in (target.source_references if hasattr(target, "source_references") else [])
        ]
        concepts = subtopic.concepts if subtopic else topic.concepts
        concepts_dicts = [{"name": c.name, "description": c.description} for c in concepts]
        concept_ids = [f"{topic.title}:{c.name}" for c in concepts]

        no_foundation_plan = TopicAnimationPlan(
            topic_id=topic.title,
            topic_title=topic.title,
            subtopic_id=subtopic.title if subtopic else None,
            subtopic_title=subtopic.title if subtopic else None,
            animation_needed=False,
            confidence=0.9,
            source_references=source_refs,
            concept_ids=concept_ids,
            status=AnimationStatus.PLANNED,
            error_message="No ready C3 visual foundation to animate",
        )
        if c3_asset is None:
            return no_foundation_plan

        base_visual_type = None
        try:
            base_visual_type = C3VisualType(c3_asset.visual_type)
        except ValueError:
            base_visual_type = None
        base_spec: dict[str, Any] = dict(c3_asset.specification or {})

        need = analyze_animation_need(
            topic_title=topic.title,
            topic_content=content,
            subtopic_title=subtopic.title if subtopic else None,
            subtopic_content=content,
            base_visual_type=base_visual_type,
            concepts=concepts_dicts,
            source_references=source_refs,
        )

        if not need.animation_needed:
            return TopicAnimationPlan(
                topic_id=topic.title,
                topic_title=topic.title,
                subtopic_id=subtopic.title if subtopic else None,
                subtopic_title=subtopic.title if subtopic else None,
                animation_needed=False,
                confidence=need.confidence,
                source_references=source_refs,
                concept_ids=concept_ids,
                status=AnimationStatus.PLANNED,
                error_message=need.skip_reason,
            )

        animation_type = need.suggested_type or C4AnimationType.PROCESS_SEQUENCE
        base_visual_type = need.base_visual_type or base_visual_type
        try:
            specification = generate_animation_specification(
                base_spec,
                animation_type,
                topic.title,
                purpose="",
                learning_objective="; ".join(target.learning_objectives)[:2000],
                source_visual_id=getattr(c3_asset, "public_id", None),
                base_visual_type=base_visual_type,
                source_references=source_refs,
                concept_ids=concept_ids,
                provenance=AnimationSourceProvenance.AI_EXPLAINED,
            )
        except Exception as exc:
            logger.error("c4_animation_spec_failed", topic=topic.title, error=str(exc))
            return TopicAnimationPlan(
                topic_id=topic.title,
                topic_title=topic.title,
                subtopic_id=subtopic.title if subtopic else None,
                subtopic_title=subtopic.title if subtopic else None,
                animation_needed=True,
                animation_type=animation_type,
                base_visual_type=base_visual_type,
                confidence=need.confidence,
                source_references=source_refs,
                concept_ids=concept_ids,
                status=AnimationStatus.FAILED,
                error_message=str(exc),
            )

        return TopicAnimationPlan(
            topic_id=topic.title,
            topic_title=topic.title,
            subtopic_id=subtopic.title if subtopic else None,
            subtopic_title=subtopic.title if subtopic else None,
            animation_needed=True,
            animation_type=animation_type,
            base_visual_type=base_visual_type,
            specification=specification,
            source_references=source_refs,
            concept_ids=concept_ids,
            confidence=need.confidence,
            provenance=AnimationSourceProvenance.AI_EXPLAINED,
            status=AnimationStatus.SPECIFYING,
        )

    @staticmethod
    def _validate_animation_output(
        package_content: str,
        spec: AnimationSpecification,
    ) -> dict[str, Any]:
        """Validate the rendered animation package output."""
        errors: list[str] = []
        if not package_content or len(package_content) < 500:
            errors.append("Rendered package is too short or empty")
        if "<svg" not in package_content or 'id="c4-svg"' not in package_content:
            errors.append("Package is missing its animation SVG stage")
        if package_content.count("</script>") != 1:
            errors.append("Package must contain exactly one script block")
        if 'id="c4-hud"' not in package_content:
            errors.append("Package is missing the playback HUD")
        if f'"animationType":"{spec.animation_type.value}"' not in package_content:
            errors.append("Package payload is missing the animation type")
        for scene in spec.scenes:
            for step in scene.steps:
                for node_id in step.node_ids:
                    if f'data-id="{node_id}"' not in package_content:
                        errors.append(f"Package missing node '{node_id}'")
                        break
        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def _model_to_asset(model: Any) -> AnimationAsset:
        """Convert a database model to an AnimationAsset schema."""
        spec = None
        try:
            if model.specification:
                spec = AnimationSpecification.model_validate(model.specification)
        except Exception:
            spec = None
        created_at_attr = getattr(model, "created_at", None)
        created_at_str = created_at_attr.isoformat() if created_at_attr else None
        return AnimationAsset(
            id=str(model.id),
            animation_type=C4AnimationType(model.animation_type),
            title=model.title,
            status=AnimationStatus(model.status),
            asset_format=getattr(model, "asset_format", "html"),
            package_content=getattr(model, "package_content", None),
            specification=spec,
            pedagogical_rationale=getattr(model, "pedagogical_rationale", "") or "",
            explanation=model.explanation or {},
            provenance=AnimationSourceProvenance(model.provenance),
            source_references=model.source_references or [],
            concept_ids=model.concept_ids or [],
            presentation_id=str(model.presentation_id) if model.presentation_id else None,
            topic_id=model.topic_id,
            subtopic_id=model.subtopic_id,
            version=model.version,
            fingerprint=model.fingerprint,
            created_at=created_at_str,
            generation_duration_ms=(model.generation_metadata or {}).get("duration_ms"),
        )

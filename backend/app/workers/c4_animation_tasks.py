"""C4 Celery Tasks — async animation generation pipeline.

Integrates with the existing Celery infrastructure to handle animation
generation asynchronously after C3 visual generation completes (either
triggered explicitly via ``/c4/animations/generate`` or auto-dispatched
by the C3 worker).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.core.logging import get_logger
from app.database.unit_of_work import UnitOfWork
from app.workers.celery_app import celery_app
from app.workers.tasks import TaskWithDLQ

logger = get_logger(__name__)


def _run_async(coro: Any) -> Any:
    """Run async code from sync Celery task context."""

    async def _wrapper() -> Any:
        try:
            return await coro
        finally:
            try:
                from app.database.session import engine

                await engine.dispose()
            except Exception:
                pass

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: asyncio.run(_wrapper()))
            return future.result()
    else:
        return asyncio.run(_wrapper())


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=TaskWithDLQ,
    name="eduvision.c4.generate_animations",
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
)
def c4_generate_animations_task(
    self: Any,
    presentation_id: str,
    user_id: str,
    force_regenerate: bool = False,
) -> dict[str, Any]:
    """Generate animations for all topics in a presentation.

    Called after C3 visual generation completes, or manually via the API.
    """
    logger.info(
        "c4_generate_animations_task_started",
        presentation_id=presentation_id,
        user_id=user_id,
    )
    result: dict[str, Any] = _run_async(
        _generate_animations_async(
            presentation_id=presentation_id,
            user_id=uuid.UUID(user_id),
            force_regenerate=force_regenerate,
        )
    )
    logger.info(
        "c4_generate_animations_task_completed",
        presentation_id=presentation_id,
        result=result,
    )
    return result


async def _generate_animations_async(
    presentation_id: str,
    user_id: uuid.UUID,
    force_regenerate: bool = False,
) -> dict[str, Any]:
    """Async implementation of animation generation."""
    from app.repositories.presentation_repository import PresentationRepository
    from app.repositories.topic_animation_asset_repository import (
        TopicAnimationAssetRepository,
    )
    from app.repositories.topic_outline_repository import TopicOutlineRepository
    from app.repositories.topic_visual_asset_repository import TopicVisualAssetRepository
    from app.schemas.topic_outline import OutlineTopic
    from app.services.c4_animation_planning_pipeline import C4AnimationPlanningPipeline

    async with UnitOfWork() as uow:
        pres_repo = PresentationRepository(uow.session)
        presentation = await pres_repo.get_by_public_id(presentation_id)
        if not presentation:
            logger.error("c4_anim_pres_not_found", presentation_id=presentation_id)
            return {"success": False, "error": "Presentation not found"}

        if str(presentation.owner_id) != str(user_id):
            logger.error("c4_anim_not_owner", presentation_id=presentation_id)
            return {"success": False, "error": "Not owner"}

        # Load C2 outline
        outline_repo = TopicOutlineRepository(uow.session)
        outline = await outline_repo.get_by_presentation_id(presentation.id)
        if not outline or outline.status != "succeeded":
            logger.warning("c4_anim_no_outline", presentation_id=presentation_id)
            return {"success": False, "error": "No C2 outline available"}

        topics: list[OutlineTopic] = []
        for t_data in outline.topics or []:
            if isinstance(t_data, dict):
                try:
                    topics.append(OutlineTopic.model_validate(t_data))
                except Exception:
                    continue
        if not topics:
            return {"success": False, "error": "No valid topics found"}

        asset_repo = TopicAnimationAssetRepository(uow.session)
        c3_repo = TopicVisualAssetRepository(uow.session)
        pipeline = C4AnimationPlanningPipeline(asset_repo=asset_repo, c3_repo=c3_repo)
        pres_db_id = str(presentation.id)

        # Plan animations
        plan = await pipeline.plan_presentation_animations(
            presentation_id=pres_db_id,
            user_id=user_id,
            topics=topics,
            force_regenerate=force_regenerate,
        )

        # Generate each planned animation
        generated = 0
        failed = 0
        for topic_plan in plan.topic_plans:
            if topic_plan.animation_needed and topic_plan.specification:
                try:
                    asset = await pipeline.generate_and_persist_animation(
                        plan=topic_plan,
                        presentation_id=pres_db_id,
                        user_id=user_id,
                        force_regenerate=force_regenerate,
                    )
                    if asset:
                        generated += 1
                    else:
                        failed += 1
                except Exception as exc:
                    logger.error(
                        "c4_single_animation_generation_failed",
                        topic=topic_plan.topic_title,
                        error=str(exc),
                    )
                    failed += 1

        await uow.commit()

    return {
        "success": True,
        "presentation_id": presentation_id,
        "animations_planned": plan.animations_planned,
        "animations_generated": generated,
        "animations_failed": failed,
        "animations_skipped": plan.animations_skipped,
        "total_topics": plan.total_topics,
    }

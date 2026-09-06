"""Project blueprint composition shared by legacy and P16 video surfaces.

Keeps the deterministic description/component → blueprint → VideoProject chain
in one place so the old ``/videos`` surface and the new ``/video-projects``
surface produce byte-identical blueprints (no regeneration drift).
"""

from __future__ import annotations

from typing import Any

from app.schemas.video_engine import VideoProject
from app.schemas.visual_intelligence import (
    CategoryClassification,
    DiscoveredComponent,
    LearningObjectives,
    TopicCategory,
    VisualizationDecision,
    VisualizationType,
    VisualLearningModel,
)
from app.services.animation_planner_service import animation_planner_service
from app.services.video_composition_service import video_composition_service
from app.services.visual_intelligence_service import VisualIntelligenceService


def _fallback_components(components: list[dict[str, Any]]) -> list[DiscoveredComponent]:
    source = components or [{"component_id": "comp_1", "name": "Primary Unit"}]
    return [
        DiscoveredComponent(
            component_id=c.get("component_id", f"comp_{idx}"),
            name=c.get("name", f"Component {idx + 1}"),
            category=c.get("category", "process"),
            short_description=c.get("short_description", "Visual node element."),
            detailed_working=c.get("detailed_working", "Executes signal processing."),
        )
        for idx, c in enumerate(source)
    ]


def _fallback_model(
    topic: str,
    components: list[dict[str, Any]],
) -> VisualLearningModel:
    comps = _fallback_components(components)
    return VisualLearningModel(
        topic=topic,
        classification=CategoryClassification(
            primary_category=TopicCategory.PROCESS,
            confidence_score=0.9,
        ),
        learning_objectives=LearningObjectives(
            main_goal=f"Learn {topic}",
            learning_objectives=[f"Understand {topic}"],
        ),
        visualization_decision=VisualizationDecision(
            visualization_type=VisualizationType.FLOWCHART,
            reason="Sequential flow layout",
            confidence=0.9,
        ),
        components=comps,
    )


async def build_visual_learning_model(
    topic: str,
    description: str | None,
    components: list[dict[str, Any]],
) -> VisualLearningModel:
    if description:
        intel_service = VisualIntelligenceService()
        return await intel_service.generate_visual_learning_model(
            description,
            title=topic,
        )
    return _fallback_model(topic, components)


def compose_project(
    topic: str,
    model: VisualLearningModel,
    target_audience: str = "general_learner",
    difficulty_level: str = "Intermediate",
) -> VideoProject:
    blueprint = animation_planner_service.create_blueprint(model)
    return video_composition_service.compose_video_project(
        topic=topic,
        model=model,
        blueprint=blueprint,
        target_audience=target_audience,
        difficulty_level=difficulty_level,
    )

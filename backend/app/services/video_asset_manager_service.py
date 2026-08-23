"""Video Asset Management Service for Phase 4K.1 + 4K.2 AI Video Learning Engine.

Indexes, organizes, and reuses visual assets (slides, canvases, animations, diagrams, simulation clips)
across video scene sequences to maximize reusability and eliminate redundancy.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.schemas.animation_engine import AnimationBlueprint
from app.schemas.video_engine import AssetManifest, AssetType, VideoAsset
from app.schemas.visual_intelligence import VisualLearningModel


class VideoAssetManagerService:

    def build_asset_manifest(
        self,
        topic: str,
        model: VisualLearningModel | None = None,
        blueprint: AnimationBlueprint | None = None,
        extra_assets: list[dict[str, Any]] | None = None,
    ) -> AssetManifest:
        assets: list[VideoAsset] = []

        # 1. Primary Canvas & Diagram Assets from Visual Model
        if model:
            assets.append(
                VideoAsset(
                    asset_id="asset_canvas_main",
                    asset_type=AssetType.VISUAL_CANVAS,
                    name=f"Interactive Canvas for {topic}",
                    source_reference=f"visual_model:{model.topic}",
                    reusability_score=1.0,
                    metadata={
                        "visualization_type": model.visualization_decision.visualization_type.value if hasattr(model.visualization_decision.visualization_type, "value") else str(model.visualization_decision.visualization_type),
                        "component_count": len(model.components),
                    },
                )
            )

            assets.append(
                VideoAsset(
                    asset_id="asset_canvas_interactive",
                    asset_type=AssetType.VISUAL_CANVAS,
                    name="Interactive Canvas Reflection State",
                    source_reference=f"visual_model:{model.topic}:interactive",
                    reusability_score=0.9,
                )
            )

            for comp in model.components:
                assets.append(
                    VideoAsset(
                        asset_id=f"asset_comp_{comp.name}",
                        asset_type=AssetType.DIAGRAM,
                        name=f"Diagram Node: {comp.name}",
                        source_reference=f"component:{comp.component_id}",
                        reusability_score=0.85,
                        metadata={
                            "category": comp.category,
                            "short_description": comp.short_description,
                        },
                    )
                )

        # 2. Animation Blueprint Assets
        if blueprint:
            assets.append(
                VideoAsset(
                    asset_id=f"asset_anim_{blueprint.blueprint_id}",
                    asset_type=AssetType.ANIMATION_REFERENCE,
                    name=f"Animation Sequence: {blueprint.topic}",
                    source_reference=f"animation_blueprint:{blueprint.blueprint_id}",
                    reusability_score=0.95,
                    metadata={
                        "total_duration_ms": blueprint.timeline.total_duration_ms,
                        "scene_count": len(blueprint.timeline.scenes),
                    },
                )
            )

        # 3. Supplemental Slides & Quiz Visuals
        assets.append(
            VideoAsset(
                asset_id="asset_slide_intro",
                asset_type=AssetType.EXPLANATION_SLIDE,
                name=f"Introduction Slide: {topic}",
                source_reference="slide_generator:intro",
                reusability_score=1.0,
            )
        )
        assets.append(
            VideoAsset(
                asset_id="asset_slide_concepts",
                asset_type=AssetType.EXPLANATION_SLIDE,
                name="Concept Explanation Slide",
                source_reference="slide_generator:concepts",
                reusability_score=1.0,
            )
        )
        assets.append(
            VideoAsset(
                asset_id="asset_example_graphic",
                asset_type=AssetType.EXAMPLE_GRAPHIC,
                name="Worked Example Graphic",
                source_reference="example_generator:graphic",
                reusability_score=0.8,
            )
        )
        assets.append(
            VideoAsset(
                asset_id="asset_slide_summary",
                asset_type=AssetType.EXPLANATION_SLIDE,
                name="Summary & Key Takeaways Slide",
                source_reference="slide_generator:summary",
                reusability_score=1.0,
            )
        )
        assets.append(
            VideoAsset(
                asset_id="asset_quiz_visual",
                asset_type=AssetType.QUIZ_VISUAL,
                name="Interactive Visual Quiz Graphic",
                source_reference="quiz_engine:visual",
                reusability_score=0.75,
            )
        )

        # 4. Extra Custom Assets
        if extra_assets:
            for item in extra_assets:
                assets.append(
                    VideoAsset(
                        asset_id=item.get("asset_id", f"asset_{uuid.uuid4().hex[:8]}"),
                        asset_type=AssetType(item.get("asset_type", "image")),
                        name=item.get("name", "Custom Asset"),
                        source_reference=item.get("source_reference", "custom"),
                        reusability_score=item.get("reusability_score", 0.8),
                    )
                )

        return AssetManifest(
            manifest_id=f"manifest_{uuid.uuid4().hex[:8]}",
            assets=assets,
            total_assets=len(assets),
        )


video_asset_manager_service = VideoAssetManagerService()

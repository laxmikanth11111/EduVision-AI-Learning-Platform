"""Animation Classification Engine Service.

Identifies the optimal animation strategy, educational objective, sequence, and interaction rules for each visual diagram layout category.
"""

from __future__ import annotations

from app.schemas.animation_engine import (
    AnimationStyle,
    LayoutAnimationClassification,
)


class AnimationClassificationService:

    def classify_layout(
        self, layout_category: str, node_ids: list[str] | None = None
    ) -> LayoutAnimationClassification:
        cat = layout_category.lower()
        nodes = node_ids or []

        if "flow" in cat or "process" in cat:
            return LayoutAnimationClassification(
                layout_category=layout_category,
                recommended_style=AnimationStyle.FLOW_ALONG_EDGE,
                educational_objective="Demonstrate signal flow and sequential process execution.",
                focus_order=nodes,
                motion_priority="directional_flow",
                replay_behavior="loop_step",
            )
        elif "hierarch" in cat or "tree" in cat:
            return LayoutAnimationClassification(
                layout_category=layout_category,
                recommended_style=AnimationStyle.NODE_EXPANSION,
                educational_objective="Reveal parent-to-child relationships and component structure.",
                focus_order=nodes,
                motion_priority="top_down_expansion",
                replay_behavior="pause_on_leaf",
            )
        elif "network" in cat or "graph" in cat or "arch" in cat:
            return LayoutAnimationClassification(
                layout_category=layout_category,
                recommended_style=AnimationStyle.FOCUS_ZOOM,
                educational_objective="Highlight interconnected node dependencies and system topology.",
                focus_order=nodes,
                motion_priority="cluster_focus",
                replay_behavior="interactive_pause",
            )
        else:
            return LayoutAnimationClassification(
                layout_category=layout_category,
                recommended_style=AnimationStyle.PROGRESSIVE_REVEAL,
                educational_objective="Progressively unveil key visual elements and concept definitions.",
                focus_order=nodes,
                motion_priority="sequential",
                replay_behavior="loop_scene",
            )


animation_classification_service = AnimationClassificationService()

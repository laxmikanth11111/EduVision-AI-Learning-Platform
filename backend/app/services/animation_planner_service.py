"""Intelligent Animation Planner & Timeline Engine Service.

Converts VisualLearningModel and Knowledge Graph into a structured, validated AnimationBlueprint with scenes, timelines, narration synchronization, and interactive triggers.
"""

from __future__ import annotations

import time
import uuid

from app.schemas.animation_engine import (
    AnimationBlueprint,
    AnimationEvent,
    AnimationScene,
    AnimationTimeline,
    TransitionType,
)
from app.schemas.visual_intelligence import VisualLearningModel
from app.services.animation_classification_service import animation_classification_service
from app.services.animation_validation_service import animation_validation_service


class AnimationPlannerService:

    def create_blueprint(self, model: VisualLearningModel) -> AnimationBlueprint:
        now = time.time()
        node_ids = [c.component_id for c in model.components]

        layout_cat = (
            model.visualization_decision.visualization_type.value
            if hasattr(model, "visualization_decision") and model.visualization_decision
            else "flowchart"
        )

        classification = animation_classification_service.classify_layout(
            layout_category=layout_cat, node_ids=node_ids
        )

        scenes: list[AnimationScene] = []
        current_time_ms = 0.0

        # Scene 1: Overview & Intro
        scene_1_events = [
            AnimationEvent(
                event_id=f"evt_{uuid.uuid4().hex[:8]}",
                timestamp_ms=current_time_ms,
                duration_ms=1000.0,
                event_type="focus_camera",
                target_id="canvas_overview",
                motion_definition={"zoom": 1.0, "center_x": 0, "center_y": 0},
                narration_cue={
                    "start_ms": 0.0,
                    "end_ms": 1000.0,
                    "keyword": "Overview",
                    "text_emphasis": f"Introduction to {model.topic}",
                },
            )
        ]
        current_time_ms += 1000.0

        scenes.append(
            AnimationScene(
                scene_id=f"scene_{uuid.uuid4().hex[:8]}",
                scene_index=0,
                title=f"Introduction to {model.topic}",
                learning_objective=f"Understand high-level architecture of {model.topic}.",
                duration_ms=1000.0,
                events=scene_1_events,
                transition=TransitionType.FADE,
                camera_focus_target="canvas_overview",
                checkpoints=["cp_intro"],
            )
        )

        # Scenes 2+: Step-by-Step Component Reveals
        for idx, comp in enumerate(model.components):
            comp_id = comp.component_id
            scene_duration_ms = 2500.0

            evt_reveal = AnimationEvent(
                event_id=f"evt_{uuid.uuid4().hex[:8]}",
                timestamp_ms=current_time_ms,
                duration_ms=1000.0,
                event_type="reveal_component",
                target_id=comp_id,
                motion_definition={"opacity": [0.0, 1.0], "scale": [0.8, 1.0]},
                narration_cue={
                    "start_ms": current_time_ms,
                    "end_ms": current_time_ms + 1000.0,
                    "keyword": comp.name,
                    "text_emphasis": f"Focusing on {comp.name}",
                },
                interaction_trigger={
                    "trigger_type": "component_inspection",
                    "action_target_id": comp_id,
                },
            )

            evt_glow = AnimationEvent(
                event_id=f"evt_{uuid.uuid4().hex[:8]}",
                timestamp_ms=current_time_ms + 1000.0,
                duration_ms=1500.0,
                event_type="highlight_node",
                target_id=comp_id,
                motion_definition={"glow_color": "#6366F1", "pulse_count": 2},
                narration_cue={
                    "start_ms": current_time_ms + 1000.0,
                    "end_ms": current_time_ms + 2500.0,
                    "keyword": comp.name,
                    "text_emphasis": comp.short_description or f"{comp.name} execution phase",
                },
            )

            current_time_ms += scene_duration_ms

            scenes.append(
                AnimationScene(
                    scene_id=f"scene_{uuid.uuid4().hex[:8]}",
                    scene_index=idx + 1,
                    title=f"Component Phase: {comp.name}",
                    learning_objective=f"Examine internal function and dependencies of {comp.name}.",
                    duration_ms=scene_duration_ms,
                    events=[evt_reveal, evt_glow],
                    transition=TransitionType.GLOW if idx % 2 == 0 else TransitionType.SLIDE,
                    camera_focus_target=comp_id,
                    checkpoints=[f"cp_{comp_id}"],
                )
            )

        total_duration_ms = current_time_ms
        total_events = sum(len(s.events) for s in scenes)
        estimated_minutes = round(total_duration_ms / 60000.0, 2)

        timeline = AnimationTimeline(
            timeline_id=f"timeline_{uuid.uuid4().hex[:8]}",
            total_duration_ms=total_duration_ms,
            scenes=scenes,
            total_events=total_events,
            estimated_minutes=estimated_minutes,
            bookmarks=[{"time_ms": s.events[0].timestamp_ms, "title": s.title} for s in scenes if s.events],
        )

        blueprint_id = f"anim_{uuid.uuid4().hex[:8]}"

        validation = animation_validation_service.validate_timeline(
            node_ids=node_ids, timeline=timeline
        )

        return AnimationBlueprint(
            blueprint_id=blueprint_id,
            visual_model_id=f"vm_{uuid.uuid4().hex[:8]}",
            topic=model.topic,
            classification=classification,
            timeline=timeline,
            validation=validation,
            created_at=now,
        )


animation_planner_service = AnimationPlannerService()

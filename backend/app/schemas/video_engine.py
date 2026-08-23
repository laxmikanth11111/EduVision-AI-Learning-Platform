"""Pydantic V2 Schemas for Phase 4K.1 + 4K.2 AI Video Learning Engine Architecture.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SceneType(str, Enum):
    EXPLANATION_SLIDE = "explanation_slide"
    ANIMATED_VISUAL = "animated_visual"
    AI_TEACHING_PRESENTATION = "ai_teaching_presentation"
    COMPONENT_DEEP_DIVE = "component_deep_dive"
    INTERACTIVE_PAUSE = "interactive_pause"
    SIMULATION_HIGHLIGHTS = "simulation_highlights"
    WORKED_EXAMPLE = "worked_example"
    VISUAL_QUIZ = "visual_quiz"
    LESSON_SUMMARY = "lesson_summary"
    NEXT_TOPIC_RECOMMENDATION = "next_topic_recommendation"


class TransitionType(str, Enum):
    FADE = "fade"
    WIPE = "wipe"
    CROSS_DISSOLVE = "cross_dissolve"
    ZOOM_BLUR = "zoom_blur"
    SLIDE_LEFT = "slide_left"
    GLOW_DISSOLVE = "glow_dissolve"


class CameraMovement(str, Enum):
    STATIC = "static"
    SMOOTH_PAN = "smooth_pan"
    DOLLY_ZOOM = "dolly_zoom"
    TRACKING = "tracking"


class RenderingStatus(str, Enum):
    QUEUED = "queued"
    GENERATING_SCRIPT = "generating_script"
    GENERATING_AUDIO = "generating_audio"
    RENDERING_VIDEO = "rendering_video"
    MUXING_AUDIO = "muxing_audio"
    VALIDATING = "validating"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class AssetType(str, Enum):
    EXPLANATION_SLIDE = "explanation_slide"
    VISUAL_CANVAS = "visual_canvas"
    ANIMATION_REFERENCE = "animation_reference"
    IMAGE = "image"
    DIAGRAM = "diagram"
    EXAMPLE_GRAPHIC = "example_graphic"
    QUIZ_VISUAL = "quiz_visual"
    SIMULATION_CLIP = "simulation_clip"


class CameraPlan(BaseModel):
    plan_id: str
    focus_target: str = "canvas_overview"
    zoom_level: float = 1.0
    pan_coordinates: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    movement_type: CameraMovement = CameraMovement.STATIC


class TransitionPlan(BaseModel):
    transition_id: str
    from_scene_id: str
    to_scene_id: str
    transition_type: TransitionType = TransitionType.FADE
    duration_ms: float = 800.0


class NarrationCue(BaseModel):
    cue_id: str
    scene_id: str
    text_emphasis: str
    estimated_spoken_duration_ms: float = 4000.0
    pause_after_ms: float = 500.0
    voice_tone_guidance: str = "encouraging"


class SubtitleEntry(BaseModel):
    entry_id: str
    start_ms: float
    end_ms: float
    text: str
    emphasized_keywords: list[str] = Field(default_factory=list)
    technical_terms: list[str] = Field(default_factory=list)


class SubtitleTrack(BaseModel):
    track_id: str
    language: str = "en"
    entries: list[SubtitleEntry] = Field(default_factory=list)


class NarrationTrack(BaseModel):
    track_id: str
    cues: list[NarrationCue] = Field(default_factory=list)


class VideoAsset(BaseModel):
    asset_id: str
    asset_type: AssetType
    name: str
    source_reference: str
    reusability_score: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetManifest(BaseModel):
    manifest_id: str
    assets: list[VideoAsset] = Field(default_factory=list)
    total_assets: int = 0


class StoryboardScene(BaseModel):
    scene_id: str
    scene_type: SceneType
    title: str
    learning_objective: str
    visual_assets: list[str] = Field(default_factory=list)
    animation_reference: str | None = None
    teaching_notes: str = ""
    narration_cue: NarrationCue
    expected_learner_outcome: str = ""
    checkpoint: str | None = None
    scene_duration_ms: float = 5000.0
    transition: TransitionType = TransitionType.FADE
    future_interaction_marker: str | None = None


class VideoStoryboard(BaseModel):
    storyboard_id: str
    topic: str
    total_scenes: int
    scenes: list[StoryboardScene] = Field(default_factory=list)
    created_at: float = 0.0


class ScriptSection(BaseModel):
    section_id: str
    section_name: str  # "introduction", "concept_explanation", "guided_walkthrough", "reflection_questions", "key_takeaways", "summary", "transition_narration", "next_topic_bridge"
    heading: str
    narration_text: str
    bullets: list[str] = Field(default_factory=list)
    estimated_duration_ms: float = 5000.0


class VideoScript(BaseModel):
    script_id: str
    topic: str
    sections: list[ScriptSection] = Field(default_factory=list)
    word_count: int = 0
    estimated_total_spoken_minutes: float = 1.0


class VideoSegment(BaseModel):
    segment_id: str
    segment_type: str
    start_ms: float
    end_ms: float
    asset_id: str | None = None
    description: str = ""


class AudioAssetSchema(BaseModel):
    audio_id: str
    provider: str
    voice: str
    language: str
    duration_ms: float
    format: str = "mp3"
    file_size_bytes: int = 0
    storage_path: str
    playable_url: str


class VideoScene(BaseModel):
    scene_id: str
    scene_index: int
    scene_type: SceneType
    title: str
    duration_ms: float
    learning_objective: str
    storyboard: StoryboardScene
    narration_cue: NarrationCue
    transition: TransitionPlan
    camera_plan: CameraPlan
    segments: list[VideoSegment] = Field(default_factory=list)
    checkpoints: list[str] = Field(default_factory=list)
    audio_asset: AudioAssetSchema | None = None


class VideoTimeline(BaseModel):
    timeline_id: str
    total_duration_ms: float
    scene_count: int
    scenes: list[VideoScene] = Field(default_factory=list)
    bookmarks: list[dict[str, Any]] = Field(default_factory=list)


class VideoMetadata(BaseModel):
    estimated_read_time_minutes: float = 2.0
    target_audience: str = "general_learner"
    difficulty_level: str = "Intermediate"
    associated_blueprint_id: str | None = None
    associated_simulation_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class RenderingQueueItem(BaseModel):
    queue_id: str
    video_id: str
    priority: int = 1
    status: RenderingStatus = RenderingStatus.QUEUED
    progress_percentage: float = 0.0
    queued_at: float = 0.0


class ExportProfile(BaseModel):
    profile_id: str
    target_resolution: str = "1080p"
    target_fps: int = 30
    format: str = "blueprint_json"
    max_bitrate_kbps: int = 5000


class VideoValidationReport(BaseModel):
    is_valid: bool
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    completeness_score: float = 100.0


class VideoProject(BaseModel):
    video_id: str
    topic: str
    title: str
    description: str
    version: str = "1.0.0"
    rendering_status: RenderingStatus = RenderingStatus.QUEUED
    progress_percentage: float = 0.0
    playable_url: str | None = None
    has_audio: bool = False
    audio_status: str = "unavailable"
    audio_track: list[AudioAssetSchema] = Field(default_factory=list)
    timeline: VideoTimeline
    storyboard: VideoStoryboard
    script: VideoScript
    subtitle_track: SubtitleTrack
    narration_track: NarrationTrack
    asset_manifest: AssetManifest
    export_profile: ExportProfile
    metadata: VideoMetadata
    validation: VideoValidationReport
    graph_nodes: list[dict[str, Any]] = Field(default_factory=list)
    graph_edges: list[dict[str, Any]] = Field(default_factory=list)
    created_at: float = 0.0

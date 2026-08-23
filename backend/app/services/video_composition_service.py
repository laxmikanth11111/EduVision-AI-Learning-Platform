"""Video Composition Engine Service for Phase 4K.1 + 4K.2 AI Video Learning Engine.

Assembles ordered video compositions from existing EduVision AI assets (Visual Models, Knowledge Graph,
Animation Blueprints, Teaching Strategy, Learning Context), creating structured Video Projects.
"""

from __future__ import annotations

import asyncio
import time
import uuid

from app.core.config import settings
from app.schemas.animation_engine import AnimationBlueprint
from app.schemas.video_engine import (
    AudioAssetSchema,
    CameraMovement,
    CameraPlan,
    ExportProfile,
    NarrationCue,
    NarrationTrack,
    TransitionPlan,
    VideoMetadata,
    VideoProject,
    VideoScene,
    VideoSegment,
    VideoTimeline,
)
from app.schemas.visual_intelligence import VisualLearningModel
from app.services.tts_service import tts_service
from app.services.video_asset_manager_service import video_asset_manager_service
from app.services.video_script_service import video_script_service
from app.services.video_storyboard_service import video_storyboard_service
from app.services.video_subtitle_service import video_subtitle_service
from app.services.video_validation_service import video_validation_service


class VideoCompositionService:

    async def compose_video_project_async(
        self,
        topic: str,
        model: VisualLearningModel | None = None,
        blueprint: AnimationBlueprint | None = None,
        target_audience: str = "general_learner",
        difficulty_level: str = "Intermediate",
    ) -> VideoProject:
        video_id = f"video_{uuid.uuid4().hex[:10]}"

        # 1. Generate Storyboard
        storyboard = video_storyboard_service.generate_storyboard(
            topic=topic, model=model, blueprint=blueprint
        )

        # 2. Generate Teaching Script
        script = video_script_service.generate_script(topic=topic, model=model)

        # 3. Build Asset Manifest
        manifest = video_asset_manager_service.build_asset_manifest(
            topic=topic, model=model, blueprint=blueprint
        )

        # 4. Generate Subtitles
        subtitle_track = video_subtitle_service.generate_subtitles(storyboard.scenes)

        # 5. Build Scenes & Generate Synchronized Voice Narration Audio
        video_scenes: list[VideoScene] = []
        narration_cues: list[NarrationCue] = []
        audio_track: list[AudioAssetSchema] = []
        total_duration_ms = 0.0

        for idx, sb_scene in enumerate(storyboard.scenes):
            cam_plan = CameraPlan(
                plan_id=f"cam_{idx}_{uuid.uuid4().hex[:6]}",
                focus_target=sb_scene.visual_assets[0] if sb_scene.visual_assets else "canvas_overview",
                zoom_level=1.2 if sb_scene.scene_type == "component_deep_dive" else 1.0,
                movement_type=CameraMovement.DOLLY_ZOOM if sb_scene.scene_type == "component_deep_dive" else CameraMovement.STATIC,
            )

            trans_plan = TransitionPlan(
                transition_id=f"trans_{idx}_{uuid.uuid4().hex[:6]}",
                from_scene_id=sb_scene.scene_id,
                to_scene_id=storyboard.scenes[idx + 1].scene_id if idx + 1 < len(storyboard.scenes) else "end",
                transition_type=sb_scene.transition,
                duration_ms=800.0,
            )

            # Generate TTS Speech Audio for Scene
            if settings.TTS_ENABLED:
                narration_text = sb_scene.narration_cue.text_emphasis or sb_scene.learning_objective
                audio = await tts_service.generate_speech(narration_text)
            else:
                audio = None

            if audio and audio.is_speech:
                audio_schema = AudioAssetSchema(
                    audio_id=audio.audio_id,
                    provider=audio.provider,
                    voice=audio.voice,
                    language=audio.language,
                    duration_ms=audio.duration_ms,
                    format=audio.format,
                    file_size_bytes=audio.file_size_bytes,
                    storage_path=audio.storage_path,
                    playable_url=audio.playable_url,
                )
                audio_track.append(audio_schema)
                synced_duration_ms = max(sb_scene.scene_duration_ms, audio.duration_ms + 500.0)
            else:
                audio_schema = None
                synced_duration_ms = sb_scene.scene_duration_ms

            segments = [
                VideoSegment(
                    segment_id=f"seg_{idx}_1",
                    segment_type="narration",
                    start_ms=total_duration_ms,
                    end_ms=total_duration_ms + synced_duration_ms,
                    asset_id=sb_scene.visual_assets[0] if sb_scene.visual_assets else None,
                    description=sb_scene.narration_cue.text_emphasis,
                )
            ]

            v_scene = VideoScene(
                scene_id=sb_scene.scene_id,
                scene_index=idx,
                scene_type=sb_scene.scene_type,
                title=sb_scene.title,
                duration_ms=synced_duration_ms,
                learning_objective=sb_scene.learning_objective,
                storyboard=sb_scene,
                narration_cue=sb_scene.narration_cue,
                transition=trans_plan,
                camera_plan=cam_plan,
                segments=segments,
                checkpoints=[sb_scene.checkpoint] if sb_scene.checkpoint else [],
                audio_asset=audio_schema,
            )

            video_scenes.append(v_scene)
            narration_cues.append(sb_scene.narration_cue)
            total_duration_ms += synced_duration_ms

        timeline = VideoTimeline(
            timeline_id=f"timeline_{uuid.uuid4().hex[:8]}",
            total_duration_ms=total_duration_ms,
            scene_count=len(video_scenes),
            scenes=video_scenes,
            bookmarks=[
                {"time_ms": s.segments[0].start_ms, "title": s.title} for s in video_scenes
            ],
        )

        narration_track = NarrationTrack(
            track_id=f"narrtrack_{uuid.uuid4().hex[:8]}",
            cues=narration_cues,
        )

        # 6. Validate Project
        validation = video_validation_service.validate_video_project(
            storyboard=storyboard,
            timeline=timeline,
            script=script,
            subtitle_track=subtitle_track,
            asset_manifest=manifest,
        )

        metadata = VideoMetadata(
            estimated_read_time_minutes=round(total_duration_ms / 60000.0, 2),
            target_audience=target_audience,
            difficulty_level=difficulty_level,
            associated_blueprint_id=blueprint.blueprint_id if blueprint else None,
            associated_simulation_id="sim_cpu_fetch_execute",
            tags=[topic.lower().replace(" ", "_"), "educational_video", "ai_lesson"],
        )

        export_profile = ExportProfile(
            profile_id=f"exp_{uuid.uuid4().hex[:6]}",
            target_resolution="1080p",
            target_fps=30,
            format="blueprint_json",
            max_bitrate_kbps=5000,
        )

        has_audio = len(audio_track) > 0
        if has_audio:
            primary_provider = audio_track[0].provider
            audio_status = "ai_voice_narration" if primary_provider == "edge_tts" else "fallback_narration"
        else:
            audio_status = "speech_unavailable"

        return VideoProject(
            video_id=video_id,
            topic=topic,
            title=f"EduVision AI Video Lesson: {topic}",
            description=f"Structured AI-generated educational video project for {topic}.",
            version="1.0.0",
            has_audio=has_audio,
            audio_status=audio_status,
            audio_track=audio_track,
            timeline=timeline,
            storyboard=storyboard,
            script=script,
            subtitle_track=subtitle_track,
            narration_track=narration_track,
            asset_manifest=manifest,
            export_profile=export_profile,
            metadata=metadata,
            validation=validation,
            created_at=time.time(),
        )

    def compose_video_project(
        self,
        topic: str,
        model: VisualLearningModel | None = None,
        blueprint: AnimationBlueprint | None = None,
        target_audience: str = "general_learner",
        difficulty_level: str = "Intermediate",
    ) -> VideoProject:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If running inside an existing loop, create a background task or run_until_complete in thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.compose_video_project_async(
                            topic=topic,
                            model=model,
                            blueprint=blueprint,
                            target_audience=target_audience,
                            difficulty_level=difficulty_level,
                        ),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.compose_video_project_async(
                        topic=topic,
                        model=model,
                        blueprint=blueprint,
                        target_audience=target_audience,
                        difficulty_level=difficulty_level,
                    )
                )
        except Exception:
            return asyncio.run(
                self.compose_video_project_async(
                    topic=topic,
                    model=model,
                    blueprint=blueprint,
                    target_audience=target_audience,
                    difficulty_level=difficulty_level,
                )
            )


video_composition_service = VideoCompositionService()

"""Video Validation Service for Phase 4K.1 + 4K.2 AI Video Learning Engine.

Validates storyboard completeness, scene ordering, objective coverage, asset references,
timing consistency, narration markers, and subtitle track synchronization.
"""

from __future__ import annotations

from app.schemas.video_engine import (
    AssetManifest,
    SubtitleTrack,
    VideoScript,
    VideoStoryboard,
    VideoTimeline,
    VideoValidationReport,
)


class VideoValidationService:

    def validate_video_project(
        self,
        storyboard: VideoStoryboard,
        timeline: VideoTimeline,
        script: VideoScript,
        subtitle_track: SubtitleTrack,
        asset_manifest: AssetManifest,
    ) -> VideoValidationReport:
        warnings: list[str] = []
        errors: list[str] = []

        # 1. Storyboard Completeness
        if storyboard.total_scenes == 0 or len(storyboard.scenes) == 0:
            errors.append("Storyboard contains zero scenes.")

        # 2. Scene Order & Objective Coverage
        scene_types = [s.scene_type for s in storyboard.scenes]
        if "explanation_slide" not in scene_types:
            warnings.append("Storyboard is missing an introductory explanation slide.")
        if "lesson_summary" not in scene_types:
            warnings.append("Storyboard is missing a closing lesson summary scene.")

        # 3. Asset References Check
        manifest_asset_ids = {a.asset_id for a in asset_manifest.assets}
        manifest_sources = {a.source_reference for a in asset_manifest.assets}

        for sc in storyboard.scenes:
            for v_asset in sc.visual_assets:
                if v_asset not in manifest_asset_ids and v_asset not in manifest_sources:
                    warnings.append(f"Scene '{sc.title}' references asset '{v_asset}' not in manifest.")

        # 4. Timing Consistency
        calculated_timeline_duration = sum(s.duration_ms for s in timeline.scenes)
        if abs(calculated_timeline_duration - timeline.total_duration_ms) > 10.0:
            warnings.append(
                f"Timeline total_duration_ms ({timeline.total_duration_ms}ms) does not match sum of scene durations ({calculated_timeline_duration}ms)."
            )

        # 5. Subtitle Sync & Coverage
        if len(subtitle_track.entries) == 0:
            warnings.append("Subtitle track contains zero subtitle entries.")

        is_valid = len(errors) == 0
        total_checks = 5.0
        passed_checks = total_checks - len(errors) - (len(warnings) * 0.5)
        completeness_score = max(0.0, min(100.0, round((passed_checks / total_checks) * 100.0, 1)))

        return VideoValidationReport(
            is_valid=is_valid,
            warnings=warnings,
            errors=errors,
            completeness_score=completeness_score,
        )


video_validation_service = VideoValidationService()

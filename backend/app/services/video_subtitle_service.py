"""Subtitle & Caption Planner Service for Phase 4K.1 + 4K.2 AI Video Learning Engine.

Generates synchronized subtitle track metadata including scene timestamp alignment,
keyword emphasis highlights, technical terminology tags, and accessibility captions.
"""

from __future__ import annotations

import uuid

from app.schemas.video_engine import StoryboardScene, SubtitleEntry, SubtitleTrack


class VideoSubtitleService:

    def generate_subtitles(
        self,
        scenes: list[StoryboardScene],
        language: str = "en",
    ) -> SubtitleTrack:
        entries: list[SubtitleEntry] = []
        current_time_ms = 0.0

        for scene in scenes:
            cue_text = scene.narration_cue.text_emphasis
            duration = scene.scene_duration_ms

            # Split scene narration into sub-caption phrases if long
            phrases = [p.strip() for p in cue_text.split(".") if p.strip()]
            phrase_duration = duration / max(len(phrases), 1)

            for idx, phrase in enumerate(phrases):
                start_ms = current_time_ms + (idx * phrase_duration)
                end_ms = start_ms + phrase_duration - 200.0

                # Extract technical terms & keywords
                words = phrase.split()
                keywords = [w.strip(",.!") for w in words if len(w) > 6]
                tech_terms = [w.strip(",.!") for w in words if w.isupper() or len(w) > 8]

                entries.append(
                    SubtitleEntry(
                        entry_id=f"sub_{uuid.uuid4().hex[:6]}",
                        start_ms=round(start_ms, 1),
                        end_ms=round(end_ms, 1),
                        text=phrase + ".",
                        emphasized_keywords=keywords[:3],
                        technical_terms=tech_terms[:2],
                    )
                )

            current_time_ms += duration

        return SubtitleTrack(
            track_id=f"subtrack_{uuid.uuid4().hex[:8]}",
            language=language,
            entries=entries,
        )


video_subtitle_service = VideoSubtitleService()

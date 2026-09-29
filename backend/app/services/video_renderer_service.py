"""Video Binary Renderer Service for Phase 4K End-to-End AI Video Engine with Audio Muxing.

Renders real MP4 video binary files from VideoProject blueprints using PIL image frame drawing,
OpenCV VideoWriter frame composition, and FFmpeg audio/video stream muxing.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
from collections.abc import Callable

import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw

from app.core.logging import get_logger
from app.schemas.video_engine import VideoProject, VideoScene

logger = get_logger(__name__)

UPLOADS_VIDEO_DIR = os.path.join(os.getcwd(), "uploads", "videos")
UPLOADS_TEMP_DIR = os.path.join(os.getcwd(), "uploads", "temp")
os.makedirs(UPLOADS_VIDEO_DIR, exist_ok=True)
os.makedirs(UPLOADS_TEMP_DIR, exist_ok=True)


class VideoRendererService:

    def __init__(self) -> None:
        os.makedirs(UPLOADS_VIDEO_DIR, exist_ok=True)
        os.makedirs(UPLOADS_TEMP_DIR, exist_ok=True)

    def render_video_mp4(
        self,
        project: VideoProject,
        width: int = 1280,
        height: int = 720,
        fps: int = 12,
        progress_callback: Callable[[float], None] | None = None,
    ) -> str:
        """Renders complete binary MP4 video file with synchronized AAC audio track.

        Returns relative HTTP playable URL: `/uploads/videos/{video_id}.mp4`
        """
        output_filename = f"{project.video_id}.mp4"
        output_path = os.path.join(UPLOADS_VIDEO_DIR, output_filename)
        temp_video_path = os.path.join(UPLOADS_TEMP_DIR, f"raw_{project.video_id}.mp4")
        temp_audio_path = os.path.join(UPLOADS_TEMP_DIR, f"audio_{project.video_id}.mp3")
        concat_list_path = os.path.join(UPLOADS_TEMP_DIR, f"concat_{project.video_id}.txt")

        logger.info("video_render_start", video_id=project.video_id, path=output_path)

        # 1. Render Visual Video Stream to Temporary Video File
        # cv2.VideoWriter.fourcc is the supported spelling from OpenCV 4.5.4
        # onward; the older module-level cv2.VideoWriter_fourcc alias is
        # deprecated and is absent from the 5.x type stubs.
        fourcc = cv2.VideoWriter.fourcc(*"mp4v")
        writer = cv2.VideoWriter(temp_video_path, fourcc, float(fps), (width, height))

        if not writer.isOpened():
            fourcc = cv2.VideoWriter.fourcc(*"XVID")
            writer = cv2.VideoWriter(temp_video_path, fourcc, float(fps), (width, height))

        try:
            scenes = project.timeline.scenes
            total_scenes = len(scenes)

            for scene_idx, scene in enumerate(scenes):
                duration_sec = max(2.0, scene.duration_ms / 1000.0)
                num_frames = int(duration_sec * fps)

                for frame_idx in range(num_frames):
                    progress = frame_idx / max(1, num_frames)
                    frame_bgr = self._render_scene_frame(
                        project=project,
                        scene=scene,
                        scene_index=scene_idx,
                        total_scenes=total_scenes,
                        frame_progress=progress,
                        width=width,
                        height=height,
                    )
                    writer.write(frame_bgr)

                if progress_callback is not None and total_scenes:
                    progress_callback((scene_idx + 1) / total_scenes * 0.9)

        finally:
            writer.release()

        # 2. Collect Scene Audio Files & Perform FFmpeg Muxing
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        audio_files = [s.audio_asset.storage_path for s in project.timeline.scenes if s.audio_asset and os.path.exists(s.audio_asset.storage_path)]

        # Browsers only decode H.264 inside <video>; OpenCV writes mp4v which must be transcoded.
        h264_args = [
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "veryfast",
            "-crf", "23",
            "-movflags", "+faststart",
        ]

        try:
            if audio_files:
                # Write FFmpeg Concat File List
                with open(concat_list_path, "w", encoding="utf-8") as f:
                    for af in audio_files:
                        # Escape single quotes for ffmpeg concat
                        clean_path = af.replace("\\", "/").replace("'", "'\\''")
                        f.write(f"file '{clean_path}'\n")

                # Concatenate Scene Audio Tracks into single MP3
                concat_cmd = [
                    ffmpeg_exe,
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_list_path,
                    "-c:a", "libmp3lame",
                    "-b:a", "192k",
                    temp_audio_path,
                ]
                subprocess.run(concat_cmd, capture_output=True, check=True)

                # Transcode Video Stream to H.264 and Mux with Audio into Final Output MP4
                mux_cmd = [
                    ffmpeg_exe,
                    "-y",
                    "-i", temp_video_path,
                    "-i", temp_audio_path,
                    *h264_args,
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    output_path,
                ]
                subprocess.run(mux_cmd, capture_output=True, check=True)

                logger.info("ffmpeg_audio_mux_completed", video_id=project.video_id)
            else:
                # No audio: still transcode to H.264 so browsers can play the file
                mux_cmd = [
                    ffmpeg_exe,
                    "-y",
                    "-i", temp_video_path,
                    *h264_args,
                    "-an",
                    output_path,
                ]
                subprocess.run(mux_cmd, capture_output=True, check=True)

                logger.info("ffmpeg_h264_transcode_completed_no_audio", video_id=project.video_id)
        except Exception as exc:
            logger.warning("ffmpeg_transcode_failed_falling_back_to_raw_video", error=str(exc))
            # Fallback to copy raw video if transcoding fails
            if os.path.exists(temp_video_path):
                import shutil
                shutil.copyfile(temp_video_path, output_path)

        # Cleanup Temp Files
        for tmp_file in [temp_video_path, temp_audio_path, concat_list_path]:
            if os.path.exists(tmp_file):
                with contextlib.suppress(Exception):
                    os.remove(tmp_file)

        # 3. Output Validation & FFprobe Stream Probing
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError(f"Video rendering failed. File {output_path} is missing or 0 bytes.")

        file_size_bytes = os.path.getsize(output_path)

        # Run FFprobe Stream Inspection
        probe_cmd = [ffmpeg_exe, "-i", output_path]
        probe_res = subprocess.run(probe_cmd, capture_output=True, text=True)
        stderr_text = probe_res.stderr.lower()

        has_video_stream = "video:" in stderr_text
        is_h264 = "h264" in stderr_text
        has_audio_stream = "audio:" in stderr_text or "aac" in stderr_text or "mp3" in stderr_text

        if not has_video_stream:
            raise RuntimeError(f"FFprobe validation failed: Output MP4 {output_path} does not contain a valid Video stream.")

        if not is_h264:
            logger.warning(
                "video_stream_not_h264_browsers_will_not_play",
                video_id=project.video_id,
            )

        if project.has_audio and not has_audio_stream:
            logger.warning("ffprobe_audio_stream_missing_falling_back_to_silent", video_id=project.video_id)
            project.has_audio = False
            project.audio_status = "speech_unavailable"

        logger.info(
            "video_render_completed",
            video_id=project.video_id,
            file_size_bytes=file_size_bytes,
            has_video_stream=has_video_stream,
            has_audio_stream=has_audio_stream,
            path=output_path,
        )

        if progress_callback is not None:
            progress_callback(1.0)

        return f"/uploads/videos/{output_filename}"

    def _render_scene_frame(
        self,
        project: VideoProject,
        scene: VideoScene,
        scene_index: int,
        total_scenes: int,
        frame_progress: float,
        width: int,
        height: int,
    ) -> np.ndarray:
        # Create PIL Canvas
        img = Image.new("RGB", (width, height), color=(2, 6, 23))  # Slate 950 (#020617)
        draw = ImageDraw.Draw(img)

        # 1. Header Navigation Bar
        draw.rectangle([0, 0, width, 60], fill=(15, 23, 42))  # Slate 900 (#0f172a)
        draw.line([0, 60, width, 60], fill=(30, 41, 59), width=2)  # Slate 800

        # Topic Title & Chapter Counter
        draw.text((24, 18), f"EduVision AI Video: {project.topic}", fill=(99, 102, 241))  # Indigo 500
        draw.text(
            (width - 240, 18),
            f"Chapter {scene_index + 1} / {total_scenes}",
            fill=(148, 163, 184),  # Slate 400
        )

        # 2. Scene Title & Subtitle Banner
        draw.text((32, 85), f"Step {scene_index + 1}: {scene.title}", fill=(248, 250, 252))  # Slate 50

        # 3. Render Visual Diagram Component Nodes
        # Use actual graph nodes from the project if available, else fall back to defaults
        if project.graph_nodes:
            node_positions = []
            for node in project.graph_nodes:
                node_positions.append({
                    "x": node.get("x", 160),
                    "y": node.get("y", 260),
                    "label": node.get("label", node.get("name", "Component")),
                    "category": node.get("category", node.get("type", "concept")),
                })
        else:
            node_positions = [
                {"x": 160, "y": 260, "label": "Concept", "category": "Core"},
                {"x": 480, "y": 260, "label": "Relationship", "category": "Supporting"},
                {"x": 800, "y": 260, "label": "Outcome", "category": "Result"},
            ]

        # Draw Connection Lines
        if project.graph_edges:
            for edge in project.graph_edges:
                src_label = edge.get("source", edge.get("from", ""))
                tgt_label = edge.get("target", edge.get("to", ""))
                src_node = next((n for n in node_positions if n["label"].lower() == src_label.lower()), None)
                tgt_node = next((n for n in node_positions if n["label"].lower() == tgt_label.lower()), None)
                if src_node and tgt_node:
                    draw.line(
                        [src_node["x"] + 140, src_node["y"] + 40, tgt_node["x"], tgt_node["y"] + 40],
                        fill=(99, 102, 241), width=4,
                    )
                    dash_x = int((src_node["x"] + 140) + frame_progress * (tgt_node["x"] - (src_node["x"] + 140)))
                    draw.ellipse([dash_x - 6, src_node["y"] + 34, dash_x + 6, src_node["y"] + 46], fill=(168, 85, 247))
        else:
            for i in range(len(node_positions) - 1):
                n1 = node_positions[i]
                n2 = node_positions[i + 1]
                draw.line([n1["x"] + 140, n1["y"] + 40, n2["x"], n2["y"] + 40], fill=(99, 102, 241), width=4)
                dash_x = int((n1["x"] + 140) + frame_progress * (n2["x"] - (n1["x"] + 140)))
                draw.ellipse([dash_x - 6, n1["y"] + 34, dash_x + 6, n1["y"] + 46], fill=(168, 85, 247))

        # Draw Node Boxes
        active_target = scene.camera_plan.focus_target
        for idx, node in enumerate(node_positions):
            is_active = (scene_index == idx) or (active_target and active_target in node["label"].lower())

            rect_color = (30, 27, 75) if is_active else (15, 23, 42)  # Indigo 950 vs Slate 900
            border_color = (129, 140, 248) if is_active else (51, 65, 85)  # Indigo 400 vs Slate 700

            draw.rounded_rectangle(
                [node["x"], node["y"], node["x"] + 200, node["y"] + 90],
                radius=16,
                fill=rect_color,
                outline=border_color,
                width=3 if is_active else 1,
            )

            draw.text((node["x"] + 16, node["y"] + 16), node["category"].upper(), fill=(129, 140, 248))
            draw.text((node["x"] + 16, node["y"] + 44), node["label"], fill=(255, 255, 255))

            if is_active:
                draw.ellipse([node["x"] + 170, node["y"] + 16, node["x"] + 182, node["y"] + 28], fill=(168, 85, 247))

        # 4. Subtitle Caption Bar at Bottom
        narration_text = scene.storyboard.narration_cue.text_emphasis or scene.learning_objective
        draw.rectangle([100, height - 90, width - 100, height - 25], fill=(15, 23, 42), outline=(51, 65, 85), width=1)
        draw.text((120, height - 68), f'"{narration_text}"', fill=(224, 231, 255))

        # Convert PIL RGB -> BGR Numpy Array for OpenCV
        frame_rgb = np.array(img)
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        return frame_bgr


video_renderer_service = VideoRendererService()

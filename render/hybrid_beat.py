"""Animated clip + equation/concept panel (story illustrates the maths)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import config
from render.equation_panel import render_teaching_strip
from utils.schemas import Scene, StoryArc


def _concept_line(scene: Scene, arc: StoryArc) -> str:
    if scene.narration and len(scene.narration) > 20:
        return scene.narration[:100]
    return arc.scenario_summary[:100] if arc.scenario_summary else scene.title


def compose_hybrid_clip(
    video_path: Path,
    scene: Scene,
    arc: StoryArc,
    output_path: Path,
    *,
    show_equation: bool = True,
) -> str:
    """Overlay teaching strip on bottom of animated video."""
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    strip_png = output_path.parent / f"strip_{scene.scene_number:02d}.png"
    eq = scene.math_overlay if show_equation else None
    render_teaching_strip(eq, _concept_line(scene, arc), strip_png)

    # Scale video, overlay strip at bottom
    vf = (
        f"[0:v]scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2[bg];"
        f"[1:v]scale={config.VIDEO_WIDTH}:-1[strip];"
        f"[bg][strip]overlay=0:main_h-overlay_h[vo]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(strip_png),
        "-filter_complex", vf,
        "-map", "[vo]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Hybrid overlay failed: {result.stderr[:400]}")
    print(f"[Hybrid] Scene {scene.scene_number}: animation + teaching strip")
    return str(output_path)

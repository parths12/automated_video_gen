"""Extend an existing clip to target duration (for recap / generic narration beats)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import config


def continue_from_clip(
    source_mp4: Path,
    output_path: Path,
    target_duration: float,
    *,
    fps: int | None = None,
) -> str:
    """Loop/trim source clip to fill target_duration at output resolution."""
    source_mp4 = Path(source_mp4)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fps = fps or config.VIDEO_FPS
    crf = int(getattr(config, "WAN_CRF", 18))

    vf = (
        f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(source_mp4),
        "-t", str(target_duration),
        "-vf", vf,
        "-r", str(fps),
        "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError(f"continue_from_clip failed: {result.stderr[:400]}")
    print(f"[Video continue] {source_mp4.name} → {target_duration:.1f}s ({output_path.name})")
    return str(output_path)

"""Extract frames from video clips for scene continuity."""

from __future__ import annotations

import subprocess
from pathlib import Path


def extract_last_frame(video_path: Path, output_png: Path) -> str:
    """Save the last frame of an MP4 as PNG (for I2V / FramePack seed)."""
    video_path = Path(video_path)
    output_png = Path(output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)

    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=nb_frames",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        n = int(probe.stdout.strip())
        select = max(0, n - 1)
    except ValueError:
        select = 0

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"select=eq(n\\,{select})",
        "-vframes", "1",
        str(output_png),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not output_png.exists():
        # Fallback: seek near end
        cmd = [
            "ffmpeg", "-y", "-sseof", "-0.1", "-i", str(video_path),
            "-vframes", "1", str(output_png),
        ]
        subprocess.run(cmd, capture_output=True, check=False)
    if not output_png.exists():
        raise RuntimeError(f"Could not extract last frame from {video_path}")
    return str(output_png)

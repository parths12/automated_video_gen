"""Optional FramePack extension for longer beats (next-frame prediction).

Requires cloning https://github.com/lllyasviel/FramePack and setting FRAMEPACK_ROOT.
When unavailable, falls back to chained Wan I2V sections from the last frame.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import config


def framepack_available() -> bool:
    root = Path(config.FRAMEPACK_ROOT)
    return root.is_dir() and (root / "demo_gradio_f1.py").exists()


def extend_clip_from_image(
    image_path: Path,
    prompt: str,
    output_path: Path,
    target_duration: float,
    scene_number: int = 1,
) -> str:
    """
    Extend or generate video from a seed frame.

    If FramePack is installed and FRAMEPACK_ENABLED, run its Gradio worker module.
    Otherwise chain Wan I2V segments (same idea: last frame → next section).
    """
    image_path = Path(image_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if config.FRAMEPACK_ENABLED and framepack_available():
        return _extend_framepack(image_path, prompt, output_path, target_duration)

    from render.local_hf import render_scene_local_video_i2v

    return render_scene_local_video_i2v(
        prompt,
        output_path,
        target_duration,
        scene_number=scene_number,
        init_image_path=image_path,
        chain_sections=True,
    )


def _extend_framepack(
    image_path: Path,
    prompt: str,
    output_path: Path,
    target_duration: float,
) -> str:
    """Invoke FramePack beat helper script inside the cloned repo."""
    root = Path(config.FRAMEPACK_ROOT)
    helper = Path(__file__).resolve().parent.parent / "scripts" / "framepack_beat.py"
    if not helper.exists():
        raise FileNotFoundError(f"Missing {helper}")

    cmd = [
        sys.executable,
        str(helper),
        "--framepack-root", str(root),
        "--image", str(image_path),
        "--prompt", prompt,
        "--output", str(output_path),
        "--seconds", str(target_duration),
        "--section-seconds", str(config.FRAMEPACK_SECTION_SECONDS),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    print(f"[FramePack] Extending ~{target_duration:.1f}s from {image_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    if result.returncode != 0:
        print(f"[FramePack] Failed ({result.returncode}): {result.stderr[:500]}")
        raise RuntimeError("FramePack extension failed — check FRAMEPACK_ROOT and GPU memory")
    return str(output_path)

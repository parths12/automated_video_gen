"""SANA-Video T2V — one clip per story beat (no looping)."""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

import config
from render.prompt_builder import build_beat_video_prompt
from utils.disk_space import is_disk_quota_error
from utils.video_frames import snap_temporal_frames


SANA_NEGATIVE_PROMPT = (
    "blurry, low quality, deformed, ugly, bad anatomy, wrong math text, "
    "western classroom, scary, jump cuts, inconsistent characters, "
    "text subtitles, watermark, logo"
)


@lru_cache(maxsize=1)
def get_sana_pipeline():
    import torch
    from diffusers import SanaVideoPipeline

    from utils.local_inference import _configure_pipeline_progress, _device

    model_id = config.LOCAL_SANA_MODEL
    cache = str(config.HF_CACHE_DIR)
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    dev = _device()
    print(f"[Sana Video] Loading {model_id} on {dev} from {cache}...")

    # Free Wan VRAM if loaded
    try:
        from utils import local_inference

        if local_inference.get_video_pipeline.cache_info().currsize > 0:
            local_inference.get_video_pipeline.cache_clear()
            torch.cuda.empty_cache()
            print("[Sana Video] Freed Wan pipeline VRAM")
    except Exception:
        pass

    load_kw = dict(cache_dir=cache, token=token, torch_dtype=torch.bfloat16)
    try:
        pipe = SanaVideoPipeline.from_pretrained(model_id, **load_kw)
    except OSError as e:
        raise RuntimeError(
            f"Failed to load {model_id}. Download:\n"
            f"  huggingface-cli download {model_id} --cache-dir {cache}\n"
            f"Original: {e}"
        ) from e

    pipe.transformer.to(torch.bfloat16)
    if hasattr(pipe, "text_encoder"):
        pipe.text_encoder.to(torch.bfloat16)
    if hasattr(pipe, "vae"):
        pipe.vae.to(torch.float32)
    pipe.to(dev)
    _configure_pipeline_progress(pipe, desc="Sana denoise")
    print(f"[Sana Video] Pipeline ready on {dev}")
    return pipe


def _cap_beat_duration(target_duration: float) -> float:
    cap = float(os.environ.get("SANA_MAX_BEAT_SECONDS", str(config.SANA_MAX_BEAT_SECONDS)))
    return min(target_duration, cap)


def render_scene_sana_video(
    prompt: str,
    output_path: Path,
    target_duration: float,
    scene_number: int = 1,
    motion_score: int | None = None,
) -> str:
    """Generate one story-beat clip with SANA-Video; trim to scene duration."""
    import torch
    from diffusers.utils import export_to_video

    from utils.disk_space import MIN_FREE_GB, ensure_writable_dir, estimate_video_bytes
    from utils.local_inference import _make_wan_step_callback, _device

    output_path = Path(output_path)
    scene_dir = output_path.parent
    scene_dir.mkdir(parents=True, exist_ok=True)

    fps = 16
    gen_duration = _cap_beat_duration(target_duration)
    frames = snap_temporal_frames(gen_duration, fps=fps)
    height = int(os.environ.get("SANA_HEIGHT", config.SANA_HEIGHT))
    width = int(os.environ.get("SANA_WIDTH", config.SANA_WIDTH))
    steps = int(os.environ.get("SANA_STEPS", config.SANA_STEPS))
    guidance = float(os.environ.get("SANA_GUIDANCE", config.SANA_GUIDANCE))
    motion = motion_score if motion_score is not None else int(
        os.environ.get("SANA_MOTION_SCORE", config.SANA_MOTION_SCORE)
    )

    full_prompt = f"{prompt} motion score: {motion}."
    print(
        f"[Sana Video] Beat {scene_number}: {target_duration:.0f}s scene "
        f"→ {frames} frames ({frames/fps:.1f}s gen) at {width}x{height}"
    )
    if os.environ.get("LOG_VIDEO_PROMPT", "1").lower() not in ("0", "false", "no"):
        print(f"[Sana Video] Prompt:\n{full_prompt}\n")

    pipe = get_sana_pipeline()
    dev = _device()
    gen = torch.Generator(device=dev).manual_seed(
        config.LOCAL_IMAGE_SEED + scene_number * 100
    )

    need_gb = max(MIN_FREE_GB, estimate_video_bytes(frames, width, height) / (1024**3) * 1.2)
    raw_clip = scene_dir / "sana_raw.mp4"
    ensure_writable_dir(raw_clip.parent, min_gb=need_gb, label="Sana mp4 export")

    try:
        output = pipe(
            prompt=full_prompt,
            negative_prompt=SANA_NEGATIVE_PROMPT,
            height=height,
            width=width,
            frames=frames,
            guidance_scale=guidance,
            num_inference_steps=steps,
            generator=gen,
            use_resolution_binning=True,
            callback_on_step_end=_make_wan_step_callback(steps),
            callback_on_step_end_tensor_inputs=[],
        )
        video_frames = output.frames[0]
        export_to_video(video_frames, str(raw_clip), fps=fps)
    except (OSError, BrokenPipeError) as e:
        if is_disk_quota_error(e):
            raise
        raise RuntimeError(f"Sana generation failed: {e}") from e

    if not raw_clip.exists() or raw_clip.stat().st_size == 0:
        raise RuntimeError("Sana produced empty video")

    vf = (
        f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    cmd = [
        "ffmpeg", "-y", "-i", str(raw_clip),
        "-vf", vf,
        "-t", str(target_duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-r", str(config.VIDEO_FPS),
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if raw_clip.exists():
        try:
            raw_clip.unlink()
        except OSError:
            pass

    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError(f"Sana ffmpeg trim failed: {result.stderr[:300]}")

    print(f"[Sana Video] Beat {scene_number} saved: {output_path.name}")
    return str(output_path)

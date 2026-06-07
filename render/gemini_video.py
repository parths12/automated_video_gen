"""Gemini image keyframes + Veo animated scene clips."""

import subprocess
import time
from pathlib import Path

import config
from utils.gemini_client import get_genai_client


def _retry_on_quota(func, max_retries: int = 3):
    """Retry Gemini calls on 429 quota errors."""
    last_err = None
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            last_err = e
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 40 * (attempt + 1)
                print(f"[Gemini] Quota limit — waiting {wait}s before retry {attempt+1}/{max_retries}")
                time.sleep(wait)
                continue
            raise
    raise last_err


def _extend_video_to_duration(src: Path, dst: Path, target_seconds: float) -> str:
    """Loop/pad a short clip to match scene narration duration."""
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(src),
        ],
        capture_output=True,
        text=True,
    )
    try:
        src_dur = float(probe.stdout.strip())
    except ValueError:
        src_dur = float(config.VEO_MAX_DURATION)

    loop_count = max(1, int(target_seconds / max(src_dur, 1)) + 1)
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", str(loop_count),
        "-i", str(src),
        "-t", str(target_seconds),
        "-vf", f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
               f"pad={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg extend failed: {result.stderr}")
    return str(dst)


def generate_scene_image(prompt: str, output_path: Path) -> str | None:
    """Generate a 9:16 keyframe with Gemini image or Imagen."""
    from google.genai import types

    full_prompt = (
        f"{prompt}. Vertical portrait 9:16, 3D Pixar-style cartoon educational scene, "
        "Indian school setting, vibrant colours, NO text, NO equations, NO watermarks."
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _try_flash_image():
        client = get_genai_client()
        response = client.models.generate_content(
            model=config.GEMINI_IMAGE_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                output_path.write_bytes(part.inline_data.data)
                return str(output_path)
        return None

    def _try_imagen():
        client = get_genai_client()
        response = client.models.generate_images(
            model="imagen-4.0-fast-generate-001",
            prompt=full_prompt,
            config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="9:16"),
        )
        if response.generated_images:
            img = response.generated_images[0].image
            client.files.download(file=img)
            img.save(str(output_path))
            return str(output_path)
        return None

    try:
        result = _retry_on_quota(_try_flash_image)
        if result:
            print(f"[Gemini Image] Keyframe: {output_path}")
            return result
    except Exception as e:
        print(f"[Gemini Image] flash-image failed: {e}")

    try:
        result = _retry_on_quota(_try_imagen)
        if result:
            print(f"[Imagen] Keyframe: {output_path}")
            return result
    except Exception as e:
        print(f"[Imagen] skipped: {e}")

    return None


def generate_multi_keyframe_clip(
    scene_prompt: str,
    output_path: Path,
    target_duration: float,
    num_frames: int = 3,
) -> str:
    """
    Generate multiple AI keyframes and crossfade them for pseudo-animation.
    Works without Veo billing.
    """
    scene_dir = Path(output_path).parent
    frames = []
    motions = [
        "wide establishing shot,",
        "medium shot with gentle movement,",
        "close-up dramatic reveal,",
    ]
    for i in range(num_frames):
        frame_path = scene_dir / f"frame_{i:02d}.png"
        sub_prompt = f"{scene_prompt}. {motions[i % len(motions)]}"
        img = generate_scene_image(sub_prompt, frame_path)
        if img:
            frames.append(Path(img))

    if not frames:
        raise RuntimeError("No keyframes generated — check Gemini image quota or billing")

    if len(frames) == 1:
        from render.scene_renderer import render_scene_kenburns_from_image
        return render_scene_kenburns_from_image(frames[0], output_path, target_duration)

    # Build crossfade slideshow video
    seg = target_duration / len(frames)
    list_file = scene_dir / "frames_concat.txt"
    part_paths = []
    for i, fp in enumerate(frames):
        part = scene_dir / f"part_{i:02d}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-i", str(fp),
                "-vf", f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
                       f"crop={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT},"
                       f"zoompan=z='1.0+0.0008*on':d={int(seg*config.VIDEO_FPS)}:s={config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}:fps={config.VIDEO_FPS}",
                "-t", str(seg), "-pix_fmt", "yuv420p", "-c:v", "libx264", str(part),
            ],
            capture_output=True,
            check=False,
        )
        if part.exists():
            part_paths.append(part)

    with open(list_file, "w", encoding="utf-8") as f:
        for p in part_paths:
            f.write(f"file '{p.resolve()}'\n")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c", "copy", str(output_path)],
        capture_output=True,
        check=False,
    )
    if not output_path.exists():
        from render.scene_renderer import render_scene_kenburns_from_image
        return render_scene_kenburns_from_image(frames[0], output_path, target_duration)
    return str(output_path)


def generate_veo_clip(
    prompt: str,
    output_path: Path,
    image_path: Path | None = None,
    duration_seconds: int | None = None,
) -> str:
    """Generate animated clip with Google Veo (requires API quota / billing)."""
    from google.genai import types

    client = get_genai_client()
    duration = min(duration_seconds or config.VEO_MAX_DURATION, config.VEO_MAX_DURATION)
    if duration not in (4, 5, 6, 8):
        duration = 8

    veo_prompt = (
        f"{prompt}. Smooth cinematic motion, 3D cartoon educational style, "
        "Indian classroom, child-friendly, NO on-screen text or numbers."
    )

    config_kwargs = {
        "aspect_ratio": "9:16",
        "duration_seconds": duration,
        "person_generation": "allow_all",
    }

    def _start_veo():
        if image_path and image_path.exists():
            image_bytes = image_path.read_bytes()
            mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
            return client.models.generate_videos(
                model=config.GEMINI_VEO_MODEL,
                prompt=veo_prompt,
                image=types.Image(image_bytes=image_bytes, mime_type=mime),
                config=types.GenerateVideosConfig(**config_kwargs),
            )
        return client.models.generate_videos(
            model=config.GEMINI_VEO_MODEL,
            prompt=veo_prompt,
            config=types.GenerateVideosConfig(**config_kwargs),
        )

    operation = _retry_on_quota(_start_veo)
    print(f"[Veo] Generating ~{duration}s clip ({config.GEMINI_VEO_MODEL}), polling...")
    while not operation.done:
        time.sleep(config.VEO_POLL_SECONDS)
        operation = client.operations.get(operation)
        if getattr(operation, "error", None):
            raise RuntimeError(f"Veo error: {operation.error}")

    if not operation.response or not operation.response.generated_videos:
        raise RuntimeError("Veo returned no videos")

    generated = operation.response.generated_videos[0]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = output_path.with_name(output_path.stem + "_raw.mp4")
    client.files.download(file=generated.video)
    generated.video.save(str(raw_path))
    print(f"[Veo] Raw clip: {raw_path}")
    return str(raw_path)


def render_scene_gemini_veo(prompt: str, output_path: Path, target_duration: float) -> str:
    """Keyframe + Veo animation, extend to target duration."""
    output_path = Path(output_path)
    scene_dir = output_path.parent
    keyframe = scene_dir / "keyframe.png"
    generate_scene_image(prompt, keyframe)
    raw = generate_veo_clip(
        prompt=prompt,
        output_path=output_path,
        image_path=keyframe if keyframe.exists() else None,
        duration_seconds=config.VEO_MAX_DURATION,
    )
    return _extend_video_to_duration(Path(raw), output_path, target_duration)


def render_scene_gemini_image(prompt: str, output_path: Path, target_duration: float) -> str:
    """AI keyframe slideshow — no Veo billing required."""
    return generate_multi_keyframe_clip(prompt, Path(output_path), target_duration)

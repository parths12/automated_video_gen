"""3D cartoon scene clip generation with multiple backends."""

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config
from utils.schemas import Scene, StoryArc


def _load_character_bible() -> dict:
    if config.CHARACTER_BIBLE_PATH.exists():
        return json.loads(config.CHARACTER_BIBLE_PATH.read_text(encoding="utf-8"))
    return {"style": {"visual": "3D cartoon educational"}}


def _build_full_prompt(scene: Scene) -> str:
    from render.prompt_builder import build_scene_prompt

    return build_scene_prompt(scene)


def render_scene_kenburns_from_image(
    image_path: Path,
    output_path: Path,
    duration: float,
    width: int = config.VIDEO_WIDTH,
    height: int = config.VIDEO_HEIGHT,
) -> str:
    """Ken Burns zoom on an existing image file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fps = config.VIDEO_FPS
    frames = int(duration * fps)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='min(zoom+0.001,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={width}x{height}:fps={fps}"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-t", str(duration), "-pix_fmt", "yuv420p", "-c:v", "libx264",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg kenburns failed: {result.stderr}")
    return str(output_path)


def render_scene_kenburns(
    scene: Scene,
    output_path: Path,
    width: int = config.VIDEO_WIDTH,
    height: int = config.VIDEO_HEIGHT,
    duration: float | None = None,
) -> str:
    """
    Creates a scene clip using a stylized still image + Ken Burns zoom.
    Fallback when no GPU video model is available.
    """
    duration = duration or float(scene.duration_seconds)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    img_path = output_path.with_suffix(".png")
    _draw_scene_still(scene, img_path, width, height)

    fps = config.VIDEO_FPS
    frames = int(duration * fps)
    # Slow zoom in
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='min(zoom+0.001,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={width}x{height}:fps={fps}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(img_path),
        "-vf", vf,
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg kenburns failed: {result.stderr}")

    return str(output_path)


def _draw_scene_still(scene: Scene, path: Path, width: int, height: int) -> None:
    """Draw a gradient cartoon-style placeholder frame with scene title."""
    img = Image.new("RGB", (width, height), color=(30, 60, 120))
    draw = ImageDraw.Draw(img)

    # Gradient bands
    for y in range(height):
        r = int(30 + (y / height) * 40)
        g = int(60 + (y / height) * 80)
        b = int(120 + (y / height) * 60)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    title = scene.title[:40]
    desc = (scene.video_prompt or scene.animation_description)[:120]

    try:
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except OSError:
        font_lg = ImageFont.load_default()
        font_sm = ImageFont.load_default()

    draw.text((60, height // 3), title, fill=(255, 220, 100), font=font_lg)
    draw.text((60, height // 2), desc, fill=(255, 255, 255), font=font_sm)
    draw.text((60, height - 120), f"Scene {scene.scene_number} | 3D Cartoon Style", fill=(200, 230, 255), font=font_sm)

    img.save(path)


def render_scene_storyboard_only(scene: Scene, output_dir: Path) -> dict:
    """Saves storyboard JSON + PNG still without video encode."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    still = output_dir / f"scene_{scene.scene_number:02d}.png"
    _draw_scene_still(scene, still, config.VIDEO_WIDTH, config.VIDEO_HEIGHT)
    meta = {
        "scene_number": scene.scene_number,
        "title": scene.title,
        "duration_seconds": scene.duration_seconds,
        "video_prompt": _build_full_prompt(scene),
        "math_overlay": scene.math_overlay,
        "still_path": str(still),
    }
    meta_path = output_dir / f"scene_{scene.scene_number:02d}_storyboard.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def render_all_scenes(
    arc: StoryArc,
    output_dir: str | Path,
    backend: str | None = None,
) -> list[str]:
    """Renders all scenes; returns list of MP4 paths (or storyboard paths)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    backend = (backend or config.VIDEO_BACKEND).lower()

    # Unified micro-story: sequential beats (Sana/Wan per beat) — no looping
    if arc.unified_story and backend in ("local_sana", "local_video", "local"):
        from render.unified_story import render_story_beats

        if config.VIDEO_LOOP_UNIFIED and backend in ("local_video", "local"):
            from render.unified_story import render_unified_master_clip

            master = render_unified_master_clip(arc, output_dir)
            return [master]
        return render_story_beats(arc, output_dir, backend=backend)

    clip_paths = []
    for scene in arc.scenes:
        scene_dir = output_dir / f"scene_{scene.scene_number:02d}"
        scene_dir.mkdir(parents=True, exist_ok=True)

        if backend == "storyboard_only":
            meta = render_scene_storyboard_only(scene, scene_dir)
            clip_paths.append(meta["still_path"])
            print(f"[SceneRenderer] Storyboard scene {scene.scene_number}: {meta['still_path']}")
            continue

        if backend == "gemini_veo":
            from render.gemini_video import render_scene_gemini_veo

            out_mp4 = scene_dir / "clip.mp4"
            prompt = _build_full_prompt(scene)
            try:
                render_scene_gemini_veo(
                    prompt=prompt,
                    output_path=out_mp4,
                    target_duration=float(scene.duration_seconds),
                )
            except Exception as e:
                print(f"[SceneRenderer] Veo failed ({e}), trying gemini_image fallback")
                from render.gemini_video import render_scene_gemini_image
                render_scene_gemini_image(prompt, out_mp4, float(scene.duration_seconds))
            clip_paths.append(str(out_mp4))
            print(f"[SceneRenderer] Gemini Veo scene {scene.scene_number}: {out_mp4}")
            continue

        if backend == "local_sana":
            from render.prompt_builder import build_beat_video_prompt
            from render.sana_video import render_scene_sana_video

            out_mp4 = scene_dir / "clip.mp4"
            prompt = build_beat_video_prompt(scene, arc)
            try:
                render_scene_sana_video(
                    prompt, out_mp4, float(scene.duration_seconds), scene_number=scene.scene_number
                )
            except Exception as e:
                print(f"[SceneRenderer] Sana failed ({e}), local_image fallback")
                from render.local_hf import render_scene_local_image
                render_scene_local_image(
                    prompt, out_mp4, float(scene.duration_seconds), scene_number=scene.scene_number
                )
            clip_paths.append(str(out_mp4))
            print(f"[SceneRenderer] Sana scene {scene.scene_number}: {out_mp4}")
            continue

        if backend == "local_video":
            from render.local_hf import render_scene_local_video

            out_mp4 = scene_dir / "clip.mp4"
            prompt = _build_full_prompt(scene)
            try:
                render_scene_local_video(
                    prompt, out_mp4, float(scene.duration_seconds), scene_number=scene.scene_number
                )
            except Exception as e:
                print(f"[SceneRenderer] Local video failed ({e}), falling back to local_image")
                from render.local_hf import render_scene_local_image
                render_scene_local_image(
                    prompt, out_mp4, float(scene.duration_seconds), scene_number=scene.scene_number
                )
            clip_paths.append(str(out_mp4))
            print(f"[SceneRenderer] Local Video scene {scene.scene_number}: {out_mp4}")
            continue

        if backend in ("local_image", "local"):
            from render.local_hf import render_scene_local_image

            out_mp4 = scene_dir / "clip.mp4"
            prompt = _build_full_prompt(scene)
            try:
                render_scene_local_image(
                    prompt, out_mp4, float(scene.duration_seconds), scene_number=scene.scene_number
                )
            except Exception as e:
                print(f"[SceneRenderer] Local image failed ({e}), Ken Burns fallback")
                render_scene_kenburns(scene, out_mp4, duration=float(scene.duration_seconds))
            clip_paths.append(str(out_mp4))
            print(f"[SceneRenderer] Local HF scene {scene.scene_number}: {out_mp4}")
            continue

        if backend == "gemini_image":
            from render.gemini_video import render_scene_gemini_image

            out_mp4 = scene_dir / "clip.mp4"
            prompt = _build_full_prompt(scene)
            try:
                render_scene_gemini_image(prompt, out_mp4, float(scene.duration_seconds))
            except Exception as e:
                print(f"[SceneRenderer] Image gen failed ({e}), Ken Burns fallback")
                render_scene_kenburns(scene, out_mp4, duration=float(scene.duration_seconds))
            clip_paths.append(str(out_mp4))
            print(f"[SceneRenderer] Gemini image scene {scene.scene_number}: {out_mp4}")
            continue

        if backend in ("kenburns", "api"):
            out_mp4 = scene_dir / "clip.mp4"
            render_scene_kenburns(scene, out_mp4, duration=float(scene.duration_seconds))
            clip_paths.append(str(out_mp4))
            print(f"[SceneRenderer] Scene {scene.scene_number} clip: {out_mp4}")
            continue

        raise ValueError(f"Unknown VIDEO_BACKEND: {backend}")

    return clip_paths

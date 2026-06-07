"""Animated beats: one visual world, simple prompt per Wan chunk."""

from __future__ import annotations

import os
from pathlib import Path

import config
from render.prompt_builder import build_beat_video_prompt
from utils.schemas import StoryArc


def _use_educational_beat(scene) -> bool:
    if not config.EDUCATIONAL_BEATS:
        return False
    return bool(scene.reveals_formula or scene.math_overlay)


def _hybrid_teaching(scene) -> bool:
    if not config.HYBRID_TEACHING:
        return False
    if scene.math_overlay or scene.reveals_formula:
        return True
    return scene.scene_number in (2, 3)


def _render_animated(
    prompt: str,
    raw_mp4: Path,
    duration: float,
    scene_number: int,
    backend: str,
    chunk_prompts: list[str] | None = None,
    init_image: Path | None = None,
) -> bool:
    if backend == "local_sana":
        from render.sana_video import render_scene_sana_video

        try:
            render_scene_sana_video(prompt, raw_mp4, duration, scene_number=scene_number)
            return True
        except Exception as e:
            print(f"[Unified Story] Sana beat {scene_number} failed: {e}")
    elif backend in ("local_video", "local"):
        from render.local_hf import render_scene_local_video

        try:
            render_scene_local_video(
                prompt,
                raw_mp4,
                duration,
                scene_number=scene_number,
                chunk_prompts=chunk_prompts,
                init_image_path=init_image,
            )
            return True
        except Exception as e:
            print(f"[Unified Story] Wan beat {scene_number} failed: {e}")
    return False


def render_story_beats(arc: StoryArc, output_dir: Path, backend: str | None = None) -> list[str]:
    backend = (backend or config.VIDEO_BACKEND).lower()
    output_dir = Path(output_dir)
    clip_paths: list[str] = []
    prev_frame: Path | None = None
    unloaded_for_i2v = False

    setting = getattr(arc, "visual_setting", "") or "single world"
    print(
        f"[Unified Story] {arc.scenario_title or arc.topic} — setting={setting} "
        f"backend={backend}"
    )

    for scene in arc.scenes:
        scene_dir = output_dir / f"scene_{scene.scene_number:02d}"
        scene_dir.mkdir(parents=True, exist_ok=True)
        out_mp4 = scene_dir / "clip.mp4"
        raw_mp4 = scene_dir / "anim_raw.mp4"
        duration = float(scene.duration_seconds)

        chunk_prompts = scene.chunk_prompts or None
        fallback = build_beat_video_prompt(scene, arc)
        summary_prompt = scene.video_prompt or fallback

        init_image = prev_frame if (prev_frame and config.WAN_USE_PREV_FRAME) else None
        if init_image and backend in ("local_video", "local") and not unloaded_for_i2v:
            from utils.local_inference import unload_video_pipelines

            unload_video_pipelines()
            unloaded_for_i2v = True
            print(
                f"[Unified Story] Beat {scene.scene_number}: I2V continues "
                f"{setting} from previous beat"
            )

        if _use_educational_beat(scene):
            from render.educational_beat import render_educational_beat

            render_educational_beat(scene, arc, out_mp4, duration)
            clip_paths.append(str(out_mp4))
            continue

        rendered = _render_animated(
            summary_prompt,
            raw_mp4,
            duration,
            scene.scene_number,
            backend,
            chunk_prompts=chunk_prompts,
            init_image=init_image,
        )

        if not rendered:
            fallback_mode = os.environ.get("STORY_FALLBACK", "local_image").lower()
            if fallback_mode == "local_image":
                from render.local_hf import render_scene_local_image

                render_scene_local_image(
                    summary_prompt, raw_mp4, duration, scene_number=scene.scene_number
                )
            else:
                from render.scene_renderer import render_scene_kenburns

                render_scene_kenburns(scene, raw_mp4, duration=duration)

        if _hybrid_teaching(scene) and raw_mp4.exists():
            from render.hybrid_beat import compose_hybrid_clip

            compose_hybrid_clip(
                raw_mp4, scene, arc, out_mp4, show_equation=bool(scene.math_overlay)
            )
        elif raw_mp4.exists():
            import shutil

            shutil.copy(raw_mp4, out_mp4)
        else:
            raise RuntimeError(f"No video for scene {scene.scene_number}")

        if out_mp4.exists() and backend in ("local_video", "local", "local_sana"):
            from utils.video_io import extract_last_frame

            frame_png = scene_dir / "last_frame.png"
            try:
                extract_last_frame(out_mp4, frame_png)
                prev_frame = frame_png
            except Exception as e:
                print(f"[Unified Story] Could not extract last frame: {e}")

        clip_paths.append(str(out_mp4))
        n_chunks = len(chunk_prompts) if chunk_prompts else 1
        print(
            f"[Unified Story] Beat {scene.scene_number} done: {out_mp4.name} "
            f"({n_chunks} chunk prompts)"
        )

    return clip_paths

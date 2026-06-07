"""Scene rendering with local Hugging Face image (and optional video) models."""

import os
from pathlib import Path

import config
from utils.local_inference import generate_image_local


def generate_multi_keyframe_clip_local(
    scene_prompt: str,
    output_path: Path,
    target_duration: float,
    scene_number: int = 1,
    num_frames: int = 3,
) -> str:
    """Generate keyframes locally and animate with ffmpeg (no API)."""
    import subprocess

    scene_dir = Path(output_path).parent
    motions = [
        "wide establishing shot, classroom background,",
        "medium shot, character interacting with props,",
        "close-up dramatic angle, glowing educational focus,",
    ]
    frames = []
    base_seed = config.LOCAL_IMAGE_SEED + scene_number * 100

    for i in range(num_frames):
        frame_path = scene_dir / f"frame_{i:02d}.png"
        sub = f"{scene_prompt}. {motions[i % len(motions)]}"
        try:
            generate_image_local(sub, frame_path, seed=base_seed + i)
            frames.append(frame_path)
        except Exception as e:
            print(f"[Local] Frame {i} failed: {e}")

    if not frames:
        raise RuntimeError("Local image generation produced no frames")

    if len(frames) == 1:
        from render.scene_renderer import render_scene_kenburns_from_image
        return render_scene_kenburns_from_image(frames[0], output_path, target_duration)

    seg = target_duration / len(frames)
    parts = []
    for i, fp in enumerate(frames):
        part = scene_dir / f"part_{i:02d}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-loop", "1", "-i", str(fp),
                "-vf", f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
                       f"crop={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT},"
                       f"zoompan=z='1.0+0.001*on':d={max(1,int(seg*config.VIDEO_FPS))}:"
                       f"s={config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}:fps={config.VIDEO_FPS}",
                "-t", str(seg), "-pix_fmt", "yuv420p", "-c:v", "libx264", str(part),
            ],
            capture_output=True,
            check=False,
        )
        if part.exists():
            parts.append(part)

    list_f = scene_dir / "concat.txt"
    with open(list_f, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{p.resolve()}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_f), "-c", "copy", str(output_path)],
        capture_output=True,
        check=False,
    )
    if not output_path.exists() and frames:
        from render.scene_renderer import render_scene_kenburns_from_image
        return render_scene_kenburns_from_image(frames[0], output_path, target_duration)
    return str(output_path)


def render_scene_local_image(prompt: str, output_path: Path, target_duration: float, scene_number: int = 1) -> str:
    return generate_multi_keyframe_clip_local(
        prompt, output_path, target_duration, scene_number=scene_number
    )


def _snap_dim(n: int, multiple: int = 16) -> int:
    """Wan VAE requires height and width divisible by `multiple`."""
    n = max(multiple, int(n))
    return (n // multiple) * multiple


def _exact_wan_frames(target_duration: float, fps: int = 16) -> int:
    from utils.video_frames import snap_temporal_frames

    return snap_temporal_frames(target_duration, fps)


def render_scene_local_video(
    prompt: str,
    output_path: Path,
    target_duration: float,
    scene_number: int = 1,
    chunk_prompts: list[str] | None = None,
    init_image_path: Path | str | None = None,
) -> str:
    """Generate one Wan2.1-T2V clip per scene, sized to exactly cover target_duration.

    On H200 (141GB VRAM) Wan2.1-1.3B can generate the full scene in a single pass:
      - Frame count is computed per-scene so clip duration > target_duration by ~0.06s
      - No looping, no concatenation, no repeated content
      - Rendered at WAN_WIDTH x WAN_HEIGHT (default 480x832, 9:16) then upscaled in compose
      - Trimmed to exactly target_duration at the end

    Resolution env vars (both dims must be multiples of 16):
      WAN_HEIGHT=832   WAN_WIDTH=480   → fast 9:16 (default)
      WAN_HEIGHT=1472  WAN_WIDTH=832   → high-quality 9:16 (much slower)
    Quality env vars:
      WAN_STEPS=50     → inference steps (raise to 75 for even better quality)
      WAN_GUIDANCE=6.0 → guidance scale
    """
    import subprocess

    from utils.disk_space import is_disk_quota_error
    from utils.local_inference import generate_video_i2v_local, generate_video_local
    from utils.video_io import extract_last_frame

    output_path = Path(output_path)
    scene_dir = output_path.parent
    scene_dir.mkdir(parents=True, exist_ok=True)

    wan_fps = 16
    wan_height = _snap_dim(int(getattr(config, "WAN_HEIGHT", 1280)))
    wan_width = _snap_dim(int(getattr(config, "WAN_WIDTH", 704)))
    wan_steps = int(getattr(config, "WAN_STEPS", 60))
    wan_guidance = float(getattr(config, "WAN_GUIDANCE", 6.0))
    i2v_steps = int(os.environ.get("WAN_I2V_STEPS", str(wan_steps)))
    i2v_guidance = float(os.environ.get("WAN_I2V_GUIDANCE", str(wan_guidance)))
    max_frames = int(getattr(config, "WAN_MAX_FRAMES_PER_PASS", 81))
    max_sec = (max_frames - 1) / wan_fps

    parts: list[Path] = []
    remaining = float(target_duration)
    chunk_i = 0
    seed_image: Path | None = Path(init_image_path) if init_image_path else None
    prompts = chunk_prompts or [prompt]

    print(
        f"[Local Video] Scene {scene_number}: {target_duration:.1f}s, "
        f"{len(prompts)} chunk prompt(s), i2v_seed={seed_image is not None}"
    )

    while remaining > 0.25:
        chunk_dur = min(remaining, max_sec)
        wan_frames = min(_exact_wan_frames(chunk_dur, fps=wan_fps), max_frames)
        raw_clip = scene_dir / f"t2v_chunk_{chunk_i:02d}.mp4"
        chunk_prompt = prompts[min(chunk_i, len(prompts) - 1)]
        use_i2v = seed_image is not None and (chunk_i > 0 or init_image_path)
        print(f"[Local Video]   chunk {chunk_i}: {chunk_prompt[:72]}...")

        try:
            if use_i2v:
                generate_video_i2v_local(
                    prompt=chunk_prompt,
                    image_path=seed_image,
                    output_path=raw_clip,
                    num_frames=wan_frames,
                    height=wan_height,
                    width=wan_width,
                    guidance_scale=i2v_guidance,
                    num_inference_steps=i2v_steps,
                    seed=config.LOCAL_IMAGE_SEED + scene_number * 100 + chunk_i,
                )
            else:
                generate_video_local(
                    prompt=chunk_prompt,
                    output_path=raw_clip,
                    num_frames=wan_frames,
                    height=wan_height,
                    width=wan_width,
                    guidance_scale=wan_guidance,
                    num_inference_steps=wan_steps,
                    seed=config.LOCAL_IMAGE_SEED + scene_number * 100 + chunk_i,
                )
        except Exception as e:
            if is_disk_quota_error(e):
                raise OSError(
                    f"Disk quota exceeded during Wan export for scene {scene_number}."
                ) from e
            print(f"[Local Video] Generation failed: {e} — falling back to image renderer")
            return render_scene_local_image(prompt, output_path, target_duration, scene_number)

        if not raw_clip.exists() or raw_clip.stat().st_size == 0:
            print("[Local Video] Empty chunk — falling back to image renderer")
            return render_scene_local_image(prompt, output_path, target_duration, scene_number)

        trimmed = scene_dir / f"t2v_chunk_{chunk_i:02d}_trim.mp4"
        _postprocess_wan_clip(raw_clip, trimmed, chunk_dur, wan_width, wan_height)
        parts.append(trimmed)
        remaining -= chunk_dur
        chunk_i += 1
        seed_png = scene_dir / f"chunk_{chunk_i:02d}_last.png"
        extract_last_frame(trimmed, seed_png)
        seed_image = seed_png
        try:
            raw_clip.unlink()
        except OSError:
            pass

    if len(parts) == 1:
        import shutil
        shutil.copy(parts[0], output_path)
        print(f"[Local Video] Scene {scene_number} done: {output_path.name}")
        return str(output_path)

    list_f = scene_dir / "t2v_concat.txt"
    with open(list_f, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{p.resolve()}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_f), "-c", "copy", str(output_path)],
        capture_output=True,
        check=False,
    )
    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"[Local Video] Scene {scene_number}: {len(parts)} chunks → {output_path.name}")
        return str(output_path)

    print("[Local Video] Chunk concat failed — falling back to image renderer")
    return render_scene_local_image(prompt, output_path, target_duration, scene_number)


def _postprocess_wan_clip(
    raw_clip: Path,
    output_path: Path,
    target_duration: float,
    wan_width: int,
    wan_height: int,
) -> str:
    """Scale/pad to 1080x1920 and trim to target duration."""
    import subprocess

    needs_scale = (wan_width != config.VIDEO_WIDTH or wan_height != config.VIDEO_HEIGHT)
    vf = (
        f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}"
        f":force_original_aspect_ratio=decrease,"
        f"pad={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        if needs_scale
        else "setsar=1"
    )
    crf = int(getattr(config, "WAN_CRF", 18))
    cmd = [
        "ffmpeg", "-y", "-i", str(raw_clip),
        "-vf", vf,
        "-t", str(target_duration),
        "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-r", str(config.VIDEO_FPS),
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        return str(output_path)
    raise RuntimeError(f"ffmpeg postprocess failed: {result.stderr[:300]}")


def render_scene_local_video_i2v(
    prompt: str,
    output_path: Path,
    target_duration: float,
    scene_number: int = 1,
    init_image_path: Path | str | None = None,
    chain_sections: bool = False,
) -> str:
    """Wan2.1 I2V from seed frame — optional chained sections for longer beats."""
    import subprocess

    from utils.local_inference import generate_video_i2v_local, unload_video_pipelines

    if not init_image_path:
        return render_scene_local_video(
            prompt, output_path, target_duration, scene_number=scene_number
        )

    output_path = Path(output_path)
    scene_dir = output_path.parent
    scene_dir.mkdir(parents=True, exist_ok=True)
    wan_height = _snap_dim(int(getattr(config, "WAN_HEIGHT", 1280)))
    wan_width = _snap_dim(int(getattr(config, "WAN_WIDTH", 704)))
    wan_steps = int(os.environ.get("WAN_I2V_STEPS", str(getattr(config, "WAN_STEPS", 60))))
    wan_guidance = float(os.environ.get("WAN_I2V_GUIDANCE", str(getattr(config, "WAN_GUIDANCE", 5.0))))
    max_frames = int(getattr(config, "WAN_MAX_FRAMES_PER_PASS", 81))
    wan_fps = 16

    section_sec = float(config.WAN_I2V_SECTION_SECONDS)
    if chain_sections and target_duration > section_sec + 0.5:
        n_sections = max(2, int(target_duration / section_sec + 0.99))
        per_sec = target_duration / n_sections
    else:
        n_sections = 1
        per_sec = target_duration

    seed_image = Path(init_image_path)
    parts: list[Path] = []

    for sec_i in range(n_sections):
        frames = min(_exact_wan_frames(per_sec, fps=wan_fps), max_frames)
        raw = scene_dir / f"i2v_sec_{sec_i:02d}.mp4"
        try:
            generate_video_i2v_local(
                prompt=prompt,
                image_path=seed_image,
                output_path=raw,
                num_frames=frames,
                height=wan_height,
                width=wan_width,
                guidance_scale=wan_guidance,
                num_inference_steps=wan_steps,
                seed=config.LOCAL_IMAGE_SEED + scene_number * 100 + sec_i,
            )
        except Exception as e:
            import traceback
            print(f"[Wan I2V] Section {sec_i} failed: {e} — T2V fallback")
            traceback.print_exc()
            return render_scene_local_video(
                prompt, output_path, target_duration, scene_number=scene_number
            )
        trimmed = scene_dir / f"i2v_sec_{sec_i:02d}_trim.mp4"
        _postprocess_wan_clip(raw, trimmed, per_sec, wan_width, wan_height)
        parts.append(trimmed)
        from utils.video_io import extract_last_frame

        seed_image = Path(extract_last_frame(trimmed, scene_dir / f"seed_{sec_i:02d}.png"))

    if len(parts) == 1:
        import shutil
        shutil.copy(parts[0], output_path)
        return str(output_path)

    list_f = scene_dir / "i2v_concat.txt"
    with open(list_f, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{p.resolve()}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_f), "-c", "copy", str(output_path)],
        capture_output=True,
        check=False,
    )
    if output_path.exists():
        print(f"[Wan I2V] Scene {scene_number}: {n_sections} chained sections → {output_path.name}")
        return str(output_path)
    return render_scene_local_video(prompt, output_path, target_duration, scene_number=scene_number)

"""Stitch scene clips, math overlays, TTS, and subtitles into final Short."""

import subprocess
from pathlib import Path

import config
from render.math_overlay import render_latex_overlay
from utils.schemas import NarrationScript, StoryArc


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _apply_math_overlay(
    video_path: Path, latex: str, out_path: Path, fontsize: int | None = None
) -> str:
    """Overlay LaTeX PNG on bottom third of video."""
    overlay_png = out_path.parent / "math_overlay.png"
    render_latex_overlay(
        latex,
        overlay_png,
        width=config.VIDEO_WIDTH,
        fontsize=fontsize or config.MATH_OVERLAY_FONTSIZE,
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(overlay_png),
        "-filter_complex",
        f"[1:v]scale={config.VIDEO_WIDTH}:-1[ov];[0:v][ov]overlay=(W-w)/2:H-h-50",
        "-c:a", "copy",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Math overlay failed: {result.stderr}")
    return str(out_path)


def _concat_clips(clip_paths: list[str], output_path: Path) -> str:
    """Concatenate scene MP4s with ffmpeg concat demuxer."""
    list_file = output_path.parent / "concat_list.txt"
    valid = [p for p in clip_paths if p.endswith(".mp4")]
    if not valid:
        raise ValueError("No MP4 clips to concatenate")

    with open(list_file, "w", encoding="utf-8") as f:
        for p in valid:
            f.write(f"file '{Path(p).resolve()}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Re-encode fallback
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-vf", f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
                   f"pad={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Concat failed: {result.stderr}")
    return str(output_path)


def _concat_clips_with_crossfade(
    clip_paths: list[str],
    output_path: Path,
    fade_duration: float | None = None,
) -> str:
    """Concatenate clips with crossfade transitions between scenes.

    Uses ffmpeg xfade filter for smooth visual transitions.
    Falls back to regular concat if xfade fails.
    """
    if fade_duration is None:
        fade_duration = float(getattr(config, "CROSSFADE_SECONDS", 1.0))

    valid = [p for p in clip_paths if p.endswith(".mp4")]
    if not valid:
        raise ValueError("No MP4 clips to concatenate")
    if len(valid) == 1:
        import shutil
        shutil.copy(valid[0], output_path)
        return str(output_path)

    # Build xfade filter chain: pairs of inputs crossfaded sequentially
    # First get durations of each clip
    durations = []
    for p in valid:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", p],
            capture_output=True, text=True,
        )
        try:
            durations.append(float(probe.stdout.strip()))
        except ValueError:
            durations.append(15.0)

    # Build inputs
    inputs = []
    for p in valid:
        inputs.extend(["-i", p])

    # Build xfade filter chain
    n = len(valid)
    filters = []
    offset = durations[0] - fade_duration
    if n == 2:
        transition = getattr(config, "CROSSFADE_TRANSITION", "dissolve")
        filters.append(
            f"[0:v][1:v]xfade=transition={transition}:duration={fade_duration}:offset={offset}"
        )
    else:
        # Chain: [0][1] -> [v1], [v1][2] -> [v2], ...
        transition = getattr(config, "CROSSFADE_TRANSITION", "dissolve")
        filters.append(
            f"[0:v][1:v]xfade=transition={transition}:duration={fade_duration}:offset={offset}[v1]"
        )
        for i in range(2, n):
            offset += durations[i - 1] - fade_duration
            prev = f"[v{i-1}]"
            if i == n - 1:
                filters.append(
                    f"{prev}[{i}:v]xfade=transition={transition}:duration={fade_duration}:offset={offset}"
                )
            else:
                filters.append(
                    f"{prev}[{i}:v]xfade=transition={transition}:duration={fade_duration}:offset={offset}[v{i}]"
                )

    filter_complex = ";".join(filters)
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[Composer] Crossfade failed, falling back to simple concat: {result.stderr[:200]}")
        return _concat_clips(clip_paths, output_path)
    return str(output_path)


def _mux_audio_video(video_path: Path, audio_path: Path, output_path: Path, duration: float) -> str:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex",
        f"[0:v]scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1[v];"
        f"[1:a]apad=whole_dur={duration}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Audio mux failed: {result.stderr}")
    return str(output_path)


def _burn_subtitles(video_path: Path, srt_path: Path, output_path: Path) -> str:
    srt_escaped = str(srt_path).replace(":", r"\:").replace("'", r"\'")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf",
        f"subtitles='{srt_escaped}':force_style="
        f"'FontSize={config.SUBTITLE_FONTSIZE},PrimaryColour=&HFFFFFF,"
        f"OutlineColour=&H000000,Outline=1,"
        f"Alignment={config.SUBTITLE_ALIGNMENT},MarginV={config.SUBTITLE_MARGIN_V}'",
        "-c:a", "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Copy without subs if burn fails
        import shutil
        shutil.copy(video_path, output_path)
        print(f"[Composer] Subtitle burn skipped: {result.stderr[:200]}")
    return str(output_path)


def _compose_unified_story(
    arc: StoryArc,
    master_clip: str,
    narration: NarrationScript,
    audio_path: str,
    output_dir: Path,
) -> str:
    """Loop one master clip to full duration, optional reveal math overlay, mux audio."""
    from render.unified_story import loop_video_to_duration

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    total_duration = float(sum(s.duration_seconds for s in arc.scenes))

    looped = output_dir / "unified_looped.mp4"
    loop_video_to_duration(Path(master_clip), looped, total_duration)

    reveal = next(
        (s for s in arc.scenes if s.reveals_formula and s.math_overlay),
        None,
    )
    video_for_mux = looped
    if reveal and reveal.math_overlay:
        with_math = output_dir / "unified_with_math.mp4"
        _apply_math_overlay(
            looped, reveal.math_overlay, with_math, fontsize=config.MATH_OVERLAY_FONTSIZE
        )
        video_for_mux = with_math

    with_audio = output_dir / "with_audio.mp4"
    _mux_audio_video(video_for_mux, Path(audio_path), with_audio, total_duration)

    from render.subtitle_sync import save_srt

    srt_path = output_dir / "subtitles.srt"
    save_srt(narration, total_duration, srt_path)

    final_path = output_dir / "final_short.mp4"
    _burn_subtitles(with_audio, srt_path, final_path)
    print(f"[Composer] Unified story final Short: {final_path}")
    return str(final_path)


def compose_final_short(
    arc: StoryArc,
    scene_clip_paths: list[str],
    narration: NarrationScript,
    audio_path: str,
    output_dir: Path,
) -> str:
    """
    Full compose pipeline:
    1. Apply per-scene math overlays
    2. Concat clips
    3. Mux TTS audio
    4. Burn subtitles
    """
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg not found — install ffmpeg for video composition")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Loop single clip only when explicitly enabled (legacy Wan shortcut)
    if (
        arc.unified_story
        and len(scene_clip_paths) == 1
        and config.VIDEO_LOOP_UNIFIED
    ):
        return _compose_unified_story(
            arc, scene_clip_paths[0], narration, audio_path, output_dir
        )

    scenes_dir = output_dir / "scenes"
    scenes_dir.mkdir(exist_ok=True)

    processed_clips = []
    for scene, clip in zip(arc.scenes, scene_clip_paths):
        clip_path = Path(clip)
        if not clip_path.suffix == ".mp4":
            continue
        out = scenes_dir / f"scene_{scene.scene_number:02d}_processed.mp4"
        # Hybrid beats already have equation strip; skip duplicate overlay
        if scene.math_overlay and not config.HYBRID_TEACHING:
            _apply_math_overlay(
                clip_path, scene.math_overlay, out, fontsize=config.MATH_OVERLAY_FONTSIZE
            )
        else:
            import shutil
            shutil.copy(clip_path, out)
        processed_clips.append(str(out))

    raw_concat = output_dir / "raw_concat.mp4"
    if config.VIDEO_BACKEND.lower() in ("local_video", "local_sana", "gemini_veo"):
        _concat_clips_with_crossfade(processed_clips, raw_concat)
    else:
        _concat_clips(processed_clips, raw_concat)

    total_duration = sum(s.duration_seconds for s in arc.scenes)
    with_audio = output_dir / "with_audio.mp4"
    _mux_audio_video(raw_concat, Path(audio_path), with_audio, float(total_duration))

    from render.subtitle_sync import save_srt

    srt_path = output_dir / "subtitles.srt"
    save_srt(narration, float(total_duration), srt_path)

    final_path = output_dir / "final_short.mp4"
    _burn_subtitles(with_audio, srt_path, final_path)
    print(f"[Composer] Final Short: {final_path}")
    return str(final_path)

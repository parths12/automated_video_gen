"""Build prompts for image/video models from story arc + character bible."""

from __future__ import annotations

import json
from pathlib import Path

import config
from utils.schemas import Scene, StoryArc


def _load_character_bible() -> dict:
    if config.CHARACTER_BIBLE_PATH.exists():
        return json.loads(config.CHARACTER_BIBLE_PATH.read_text(encoding="utf-8"))
    return {"style": {"visual": "3D cartoon educational"}}


def build_scene_prompt(scene: Scene, arc: StoryArc | None = None, prev_beat: str = "") -> str:
    return build_beat_video_prompt(scene, arc, prev_beat=prev_beat)


def build_beat_video_prompt(
    scene: Scene,
    arc: StoryArc | None = None,
    prev_beat: str = "",
) -> str:
    """Short summary prompt; per-chunk actions live in scene.chunk_prompts."""
    if scene.chunk_prompts:
        return scene.chunk_prompts[0]

    bible = _load_character_bible()
    style = bible.get("style", {}).get("visual", "3D Pixar-like cartoon animation")
    beat = (scene.video_prompt or scene.animation_description or "").strip()
    neg = bible.get("negative_prompt", "blurry, static image, text on screen, watermark")

    continuity = ""
    if prev_beat:
        continuity = (
            "Continue the same visual world and characters from the previous shot. "
            f"Previous moment: {prev_beat[:180]}. "
        )
    elif arc and arc.scenario_summary:
        continuity = f"Story setting: {arc.scenario_summary[:120]}. "

    # Video model: visuals only. Equations/teaching go in narration + hybrid strip, not in T2V prompt.
    setting = ""
    if arc and arc.scenario_summary:
        setting = f"Visual story: {arc.scenario_summary[:100]}. "

    shot = scene.shot_type.value if hasattr(scene, "shot_type") else "journey"

    return (
        f"Animated cartoon video clip, vertical 9:16 portrait, {style}. "
        f"{continuity}{setting}"
        f"Action in this beat: {beat} "
        f"Shot: {shot}. "
        f"Show motion and objects clearly; no text or formulas on screen. "
        f"Smooth motion, cinematic camera. "
        f"Avoid: {neg}, frozen slideshow, unrelated jump cut, railway unless story is on a train."
    )


def build_unified_wan_prompt(arc: StoryArc) -> str:
    bible = _load_character_bible()
    style = bible.get("style", {}).get("visual", "3D Pixar-like educational cartoon")
    core = (arc.master_video_prompt or "").strip()
    if not core:
        beats = [s.video_prompt or s.animation_description for s in arc.scenes[:4]]
        core = " Then ".join(b.strip() for b in beats if b.strip())
    if len(core) > 900:
        core = core[:897] + "..."
    setting = (arc.scenario_summary or arc.topic or "")[:200]
    return (
        f"Single continuous animated 3D cartoon, vertical 9:16. {style}. "
        f"{setting} {core} Fluid motion, no on-screen text."
    )

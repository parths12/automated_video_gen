"""One visual world for the whole Short; simple per-chunk prompts (~5s each)."""

from __future__ import annotations

import math
import re

import config
from utils.schemas import ConceptCard, StoryArc

_GENERIC_NARRATION = re.compile(
    r"comment below|which ncert|explore next|now you can see why|maths works|magic of maths",
    re.I,
)

_STYLE = "3D Pixar, vertical 9:16, India, no text"

# Simple action beats per scene (same location/subject throughout the whole video)
_CAR_CHUNKS: dict[int, list[str]] = {
    1: [
        f"{_STYLE}. White car stopped at red traffic light on a straight city road. Wide shot.",
        f"{_STYLE}. Same white car, same road. Light turns green. Car creeps forward slowly.",
        f"{_STYLE}. Same white car, same road. Car moves a little faster. Side tracking shot.",
        f"{_STYLE}. Same white car, same road. Steady slow drive. Trees in background.",
    ],
    2: [
        f"{_STYLE}. Same white car, same road. Car accelerates, speed clearly increasing.",
        f"{_STYLE}. Same white car, same road. Shop fronts pass faster. Motion on asphalt.",
        f"{_STYLE}. Same white car, same road. Low angle beside car. Faster roll.",
        f"{_STYLE}. Same white car, same road. Long straight ahead. Smooth acceleration.",
    ],
    3: [
        f"{_STYLE}. Same white car, same road. Soft glow trail behind car. Still speeding up.",
        f"{_STYLE}. Same white car, same road. Road markers zip past. Dynamic tracking.",
        f"{_STYLE}. Same white car, same road. Wide shot, car mid-journey, clear motion.",
    ],
    4: [
        f"{_STYLE}. Same white car, same road. Car eases speed, driver waves cheerfully.",
        f"{_STYLE}. Same white car parked roadside. Teen student thumbs up, warm sunset.",
    ],
}

_CRICKET_CHUNKS: dict[int, list[str]] = {
    1: [
        f"{_STYLE}. Indian cricket ground, empty pitch, afternoon light. Wide establishing shot.",
        f"{_STYLE}. Same ground. Batsman in blue jersey takes stance at crease.",
        f"{_STYLE}. Same ground. Batsman swings bat, hits red ball.",
        f"{_STYLE}. Same ground. Red ball rolls along green pitch toward camera.",
    ],
    2: [
        f"{_STYLE}. Same cricket pitch. Ball keeps rolling, slowing slightly on grass.",
        f"{_STYLE}. Same pitch. Fielder runs in from mid-off toward the ball.",
        f"{_STYLE}. Same pitch. Close-up of ball spinning on ground.",
        f"{_STYLE}. Same pitch. Ball reaches rough patch, small bounce.",
    ],
    3: [
        f"{_STYLE}. Same pitch. Two fielders chase ball along ground.",
        f"{_STYLE}. Same pitch. Ball passes white crease line.",
        f"{_STYLE}. Same pitch. Wide shot, players in same stadium.",
    ],
    4: [
        f"{_STYLE}. Same pitch. Players smile, relaxed end of play.",
        f"{_STYLE}. Same ground. Student in stands waves at camera.",
    ],
}


def is_generic_narration(text: str) -> bool:
    return bool(_GENERIC_NARRATION.search(text or ""))


def pick_visual_setting(concept_card: ConceptCard) -> str:
    """One setting for the entire video — driven by visual_metaphor first."""
    forced = getattr(config, "VISUAL_SETTING", "") or ""
    if forced in ("city_car", "cricket_pitch"):
        return forced

    meta = (concept_card.visual_metaphor or "").lower()
    if any(k in meta for k in ("car", "road", "traffic", "vehicle", "driver", "highway")):
        return "city_car"
    if any(k in meta for k in ("cricket", "pitch", "batsman", "bowler")):
        return "cricket_pitch"

    if config.SUBJECT == "physics":
        return "city_car"
    hooks = " ".join(concept_card.real_world_hooks[:5]).lower()
    if "cricket" in hooks and "car" not in hooks:
        return "cricket_pitch"
    return "city_car"


def _chunk_bank(setting: str) -> dict[int, list[str]]:
    return _CRICKET_CHUNKS if setting == "cricket_pitch" else _CAR_CHUNKS


def build_chunk_prompts_for_scene(
    setting: str,
    scene_number: int,
    duration_seconds: float,
    *,
    generic: bool = False,
) -> list[str]:
    """Return N simple prompts for N Wan chunks in this scene."""
    max_sec = (int(getattr(config, "WAN_MAX_FRAMES_PER_PASS", 81)) - 1) / 16.0
    n_chunks = max(1, int(math.ceil(duration_seconds / max(max_sec, 4.0))))

    bank = _chunk_bank(setting)
    templates = list(bank.get(scene_number, bank.get(4, [])))
    if generic:
        if setting == "cricket_pitch":
            templates = [
                f"{_STYLE}. Same cricket pitch. Ball still rolling slowly on grass.",
                f"{_STYLE}. Same cricket ground. Calm wide shot, same players.",
            ]
        else:
            templates = [
                f"{_STYLE}. Same white car, same road. Car keeps driving at steady speed.",
                f"{_STYLE}. Same white car, same road. Gentle tracking shot, same world.",
            ]

    if not templates:
        templates = [f"{_STYLE}. Same scene continues. Simple motion."]

    prompts: list[str] = []
    for i in range(n_chunks):
        prompts.append(templates[min(i, len(templates) - 1)])
    return prompts


def scene_summary_prompt(setting: str, scene_number: int) -> str:
    if setting == "cricket_pitch":
        summaries = {
            1: "Cricket ground: batsman hits ball, ball rolls on pitch",
            2: "Same pitch: ball rolling, fielders react",
            3: "Same pitch: motion along the ground",
            4: "Same cricket ground: friendly recap",
        }
    else:
        summaries = {
            1: "City road: white car starts from traffic light",
            2: "Same road: car accelerates faster",
            3: "Same road: car still accelerating, motion trail",
            4: "Same road: car recap, student waves",
        }
    return summaries.get(scene_number, "Same setting continues")


def apply_visual_director(arc: StoryArc, concept_card: ConceptCard) -> StoryArc:
    setting = pick_visual_setting(concept_card)
    arc.visual_setting = setting
    arc.master_video_prompt = (
        f"Single continuous {setting.replace('_', ' ')} — same location and subject all beats"
    )
    arc.scenario_summary = (
        f"{concept_card.definition} "
        f"(Visual: one {setting.replace('_', ' ')} story throughout.)"
    )

    for scene in arc.scenes:
        generic = is_generic_narration(scene.narration)
        scene.chunk_prompts = build_chunk_prompts_for_scene(
            setting, scene.scene_number, float(scene.duration_seconds), generic=generic
        )
        scene.video_prompt = scene_summary_prompt(setting, scene.scene_number)
        scene.animation_description = f"Setting={setting}; {len(scene.chunk_prompts)} chunks"
        print(
            f"[Visual director] Beat {scene.scene_number} ({setting}): "
            f"{len(scene.chunk_prompts)} chunk prompts — e.g. {scene.chunk_prompts[0][:60]}..."
        )
    return arc

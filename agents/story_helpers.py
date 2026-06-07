"""Subject-aware story defaults — avoid train/canteen template bleed into physics."""

from __future__ import annotations

import re

import config
from utils.schemas import ConceptCard, HookSpec, StoryArc

# Shown to LLM as shape-only example (not content to copy)
PHYSICS_STORY_EXAMPLE = """{
  "scenario_title": "The cricket ball's path",
  "scenario_summary": "A bowler releases the ball; students see position change and speed build — motion in a straight line.",
  "master_video_prompt": "3D Pixar cricket ground: ball rolling, fielders, motion trails",
  "scenes": [
    {
      "scene_number": 1,
      "title": "Something moves",
      "duration_seconds": 18,
      "narration": "Watch the red ball leave the bowler's hand — its position keeps changing. That change with time is motion!",
      "video_prompt": "Animated 3D Pixar vertical 9:16: Indian school cricket ground, red cricket ball released from bowler's hand, camera follows ball down the pitch, green field, afternoon light, smooth motion blur",
      "math_overlay": null,
      "shot_type": "journey",
      "reveals_formula": false
    },
    {
      "scene_number": 2,
      "title": "Faster and faster",
      "duration_seconds": 20,
      "narration": "Every second it covers more ground — the ball is speeding up along a straight path.",
      "video_prompt": "3D Pixar 9:16: same cricket ball rolling faster along straight white line on pitch, distance markers appear, same ground same lighting",
      "math_overlay": "v = \\\\Delta x / \\\\Delta t",
      "shot_type": "journey",
      "reveals_formula": false
    },
    {
      "scene_number": 3,
      "title": "The idea clicks",
      "duration_seconds": 22,
      "narration": "Motion means changing position. Distance and time tell us how fast the journey is!",
      "video_prompt": "3D Pixar 9:16: ball reaches batsman end, glowing trail shows path, student Arjun points at trail smiling, celebratory sparkles, same cricket ground",
      "math_overlay": "\\\\text{speed} = \\\\frac{\\\\text{distance}}{\\\\text{time}}",
      "shot_type": "reveal",
      "reveals_formula": true
    },
    {
      "scene_number": 4,
      "title": "Recap",
      "duration_seconds": 15,
      "narration": "Whenever position changes with time, that's motion. Comment your next physics topic!",
      "video_prompt": "3D Pixar 9:16: Arjun and friends hold cricket ball, wave at camera, sunset stadium, cheerful ending",
      "math_overlay": null,
      "shot_type": "recap",
      "reveals_formula": false
    }
  ]
}"""

MATH_STORY_EXAMPLE = """{
  "scenario_title": "Ravi and the mithai box",
  "scenario_summary": "Animated story: 30 sweets, Ravi eats 2, auntie splits 28 into four piles of 7.",
  "scenes": []
}"""

_WRONG_PHYSICS_VISUAL = re.compile(
    r"canteen|mithai|sweet shop|balance scale|lhs|rhs|four students.*pile|"
    r"removes two items|equal piles of seven|vande bharat|train platform",
    re.I,
)

_WRONG_MATH_OVERLAY = {"x = 5", "30 - 2 = 28", "28 / 4 = 7", "2x - 3 = 7"}


def default_equation(concept_card: ConceptCard) -> str | None:
    if concept_card.latex_equations:
        return concept_card.latex_equations[0]
    if config.SUBJECT == "physics":
        topic = concept_card.topic.lower()
        if "accelerat" in topic:
            return "a = \\Delta v / \\Delta t"
        if "velocity" in topic:
            return "v = \\Delta x / \\Delta t"
        if "motion" in topic:
            return "\\text{speed} = \\frac{\\text{distance}}{\\text{time}}"
        return None
    return "2x - 3 = 7"


def default_beat_prompts(concept_card: ConceptCard, hook_spec: HookSpec) -> list[str]:
    """Fallback video beats tied to the concept card — not generic canteen/train."""
    metaphor = (concept_card.visual_metaphor or concept_card.definition or concept_card.topic).strip()
    hook = (hook_spec.visual_action or hook_spec.opening_line or metaphor)[:120]

    if config.SUBJECT == "physics":
        return [
            (
                "Animated 3D Pixar vertical 9:16: Indian cricket match, batsman hits red ball, "
                "ball rolls along green pitch, cinematic tracking shot, clear motion on ground."
            ),
            (
                "Animated 3D Pixar vertical 9:16: Indian city road, white car starts from rest, "
                "accelerates slowly in straight line, camera tracks car, afternoon light."
            ),
            (
                f"Animated 3D Pixar vertical 9:16: same scene, glowing path shows distance over time, "
                "reveal moment, dynamic camera, no text on screen."
            ),
            (
                f"Animated 3D Pixar vertical 9:16: same world, friendly recap, characters wave to camera, "
                "warm ending shot."
            ),
        ]

    return [
        f"3D Pixar 9:16: Indian classroom story for {concept_card.topic[:40]}, {hook}, establishing shot",
        "3D Pixar 9:16: same characters, visual metaphor develops, smooth motion, same setting",
        "3D Pixar 9:16: same scene, equation moment shown via props not text slides, reveal",
        "3D Pixar 9:16: characters celebrate, thumbs up, cheerful recap",
    ]


def story_example_json() -> str:
    if config.SUBJECT == "physics":
        return PHYSICS_STORY_EXAMPLE
    return MATH_STORY_EXAMPLE


def sanitize_story_arc(
    arc: StoryArc, concept_card: ConceptCard, hook_spec: HookSpec | None = None
) -> StoryArc:
    """Fix LLM bleed: wrong math overlays, canteen/train prompts on physics topics."""
    from utils.schemas import HookType

    eq = default_equation(concept_card)
    if hook_spec is None:
        hook_spec = HookSpec(
            hook_type=HookType.CURIOSITY,
            opening_line=concept_card.definition[:80],
            visual_action=concept_card.visual_metaphor,
            knowledge_gap_question=f"What is {concept_card.topic}?",
            analogy=concept_card.visual_metaphor,
        )
    beats = default_beat_prompts(concept_card, hook_spec)
    metaphor_lower = (concept_card.visual_metaphor or "").lower()
    allow_train = "train" in metaphor_lower or "rail" in metaphor_lower or "metro" in metaphor_lower

    for i, scene in enumerate(arc.scenes):
        overlay = (scene.math_overlay or "").strip()
        if config.SUBJECT == "physics":
            if overlay in _WRONG_MATH_OVERLAY or (overlay and not concept_card.latex_equations):
                scene.math_overlay = eq
            elif eq and scene.scene_number in (2, 3) and not overlay:
                scene.math_overlay = eq
        vp = scene.video_prompt or ""
        if config.SUBJECT == "physics":
            off_topic = bool(_WRONG_PHYSICS_VISUAL.search(vp))
            train_trope = bool(
                not allow_train
                and re.search(r"vande bharat|train platform|railway track|\btrain\b", vp, re.I)
            )
            if off_topic or train_trope:
                scene.video_prompt = beats[min(i, len(beats) - 1)]
                print(f"[Story sanitize] Fixed beat {scene.scene_number} video_prompt")

        # Narration should teach; video_prompt stays visual-only
        if scene.narration and len(scene.narration) < 30 and concept_card.definition:
            scene.narration = (
                f"{concept_card.definition[:100]} "
                f"Watch what happens in this scene!"
            )[:200]

    if not arc.scenario_summary:
        arc.scenario_summary = concept_card.definition
    return arc

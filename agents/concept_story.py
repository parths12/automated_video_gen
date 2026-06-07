"""Optional story templates — only used when CONCEPT_ANCHOR_MODE=strict (legacy)."""

from __future__ import annotations

import config
from utils.schemas import ConceptCard, HookSpec, StoryArc


def build_concept_anchored_scenes(concept_card: ConceptCard, hook_spec: HookSpec) -> list[dict]:
    """Animated story tied to LHS/RHS — visual metaphor, not text slides."""
    eq_main = concept_card.latex_equations[0] if concept_card.latex_equations else "2x - 3 = 7"
    hook_line = hook_spec.opening_line[:90]

    return [
        {
            "scene_number": 1,
            "title": "The unbalanced scale",
            "duration_seconds": 18,
            "narration": (
                f"{hook_line} "
                "Watch this golden detective scale — the left pan sinks down, the right pan floats up. "
                "Something is not equal yet!"
            ),
            "animation_description": "Scale intro",
            "video_prompt": (
                "Animated 3D Pixar vertical 9:16: Arjun and Riya enter a magical Indian classroom, "
                "a giant golden balance scale materializes, left pan heavy with glowing mystery blocks, "
                "right pan holds a single bright glowing orb, scale tilted dramatically, "
                "children walk closer with curious expressions, slow cinematic dolly forward"
            ),
            "math_overlay": None,
            "shot_type": "journey",
            "reveals_formula": False,
        },
        {
            "scene_number": 2,
            "title": "Left side vs right side",
            "duration_seconds": 20,
            "narration": (
                f"The left side is the expression two x minus three — like {eq_main.split('=')[0].strip()}. "
                "The right side is seven. The scale will balance only when both match!"
            ),
            "animation_description": "LHS RHS visual",
            "video_prompt": (
                "Animated 3D Pixar vertical 9:16: same golden scale same classroom, "
                "teacher character points at left pan where blue glowing cubes stack and pulse, "
                "then points at right pan with orange glowing sphere, "
                "Arjun and Riya nod, smooth pan across the scale, blocks gently wobble"
            ),
            "math_overlay": eq_main,
            "shot_type": "journey",
            "reveals_formula": False,
        },
        {
            "scene_number": 3,
            "title": "The scale balances",
            "duration_seconds": 22,
            "narration": (
                "Substitute x equals five — the left becomes seven, the right is seven! "
                "The scale lights up green. That is a solution — LHS equals RHS!"
            ),
            "animation_description": "Solution reveal",
            "video_prompt": (
                "Animated 3D Pixar vertical 9:16: golden balance scale slowly levels perfectly horizontal, "
                "green magical light bursts from center, Arjun and Riya jump and cheer, "
                "confetti sparkles, both pans glow equal brightness, celebration dance, same setting"
            ),
            "math_overlay": "x = 5",
            "shot_type": "reveal",
            "reveals_formula": True,
        },
        {
            "scene_number": 4,
            "title": "Remember the idea",
            "duration_seconds": 15,
            "narration": (
                "Whenever LHS equals RHS, you found a solution. "
                "Which NCERT topic next? Comment below!"
            ),
            "animation_description": "Recap",
            "video_prompt": (
                "Animated 3D Pixar vertical 9:16: Arjun Riya Priya Dev give thumbs up in front of "
                "glowing green balance scale, friendly wave to camera, warm sunset classroom windows, "
                "playful ending shot"
            ),
            "math_overlay": None,
            "shot_type": "recap",
            "reveals_formula": False,
        },
    ]


def build_sweets_story_scenes(concept_card: ConceptCard, hook_spec: HookSpec) -> list[dict]:
    """Legacy sweets-shop template (strict mode only)."""
    return [
        {
            "scene_number": 1,
            "title": "Thirty sweets",
            "duration_seconds": 18,
            "narration": "Ravi, Riya, Priya and Dev at a Diwali sweet shop. Thirty colourful mithai on the tray!",
            "manim_hint": "",
            "video_prompt": (
                "Animated 3D Pixar vertical 9:16: four Indian teens at bright sweet shop counter, "
                "glass tray piled with thirty golden mithai, Ravi in blue kurta reaches toward sweets, "
                "friends smile, warm festival lights, camera push-in"
            ),
            "animation_description": "Shop intro",
            "math_overlay": None,
            "shot_type": "journey",
            "reveals_formula": False,
        },
        {
            "scene_number": 2,
            "title": "Ravi eats two",
            "duration_seconds": 20,
            "narration": "Ravi quickly eats two mithai! Only twenty-eight left on the tray now.",
            "video_prompt": (
                "Animated 3D Pixar vertical 9:16: same four friends same shop, "
                "Ravi eats two mithai with animated chewing motion, tray shows fewer sweets, "
                "Riya looks surprised, smooth side camera move"
            ),
            "animation_description": "Subtraction beat",
            "math_overlay": "30 - 2 = 28",
            "shot_type": "journey",
            "reveals_formula": False,
        },
        {
            "scene_number": 3,
            "title": "Fair division",
            "duration_seconds": 22,
            "narration": "The auntie divides twenty-eight into four equal piles — seven for each friend!",
            "video_prompt": (
                "Animated 3D Pixar vertical 9:16: friendly auntie in saree slides mithai into four equal piles, "
                "each friend receives seven sweets, everyone cheers, sparkles, same shop"
            ),
            "animation_description": "Division beat",
            "math_overlay": "28 / 4 = 7",
            "shot_type": "reveal",
            "reveals_formula": True,
        },
        {
            "scene_number": 4,
            "title": "Happy ending",
            "duration_seconds": 15,
            "narration": "Fair sharing feels like balancing both sides of an equation! Comment your next topic!",
            "video_prompt": (
                "Animated 3D Pixar vertical 9:16: four friends hold up seven mithai each, laugh and wave at camera"
            ),
            "animation_description": "Recap",
            "math_overlay": None,
            "shot_type": "recap",
            "reveals_formula": False,
        },
    ]


def _is_physics_motion(concept_card: ConceptCard) -> bool:
    blob = " ".join(
        [
            concept_card.topic,
            concept_card.chapter_name,
            concept_card.definition,
            concept_card.visual_metaphor,
        ]
    ).lower()
    keys = (
        "kinematic", "motion", "velocity", "acceleration", "displacement",
        "speed", "rectilinear", "relative velocity", "physics",
    )
    return any(k in blob for k in keys) or getattr(config, "SUBJECT", "") == "physics"


def build_kinematics_story_scenes(concept_card: ConceptCard, hook_spec: HookSpec) -> list[dict]:
    """Legacy train template (strict mode only)."""
    hook = hook_spec.opening_line[:90]
    eq = concept_card.latex_equations[0] if concept_card.latex_equations else "v = u + at"
    return [
        {
            "scene_number": 1,
            "title": "Train leaves the platform",
            "duration_seconds": 18,
            "narration": (
                f"{hook} "
                "Picture a Vande Bharat train leaving New Delhi station. "
                "The platform signs whizz past — the train is in motion along a straight track!"
            ),
            "manim_hint": "",
            "animation_description": "Train departs",
            "video_prompt": (
                "Animated 3D Pixar vertical 9:16: sleek Indian Vande Bharat train accelerates "
                "along straight railway track leaving crowded station platform, "
                "passengers visible through windows, morning golden light, "
                "camera tracks alongside train, motion blur on platform pillars"
            ),
            "math_overlay": None,
            "shot_type": "journey",
            "reveals_formula": False,
        },
        {
            "scene_number": 2,
            "title": "Speed builds up",
            "duration_seconds": 20,
            "narration": (
                "Its speed keeps increasing every second — that is acceleration! "
                "Velocity tells us how fast and in which direction the train moves."
            ),
            "animation_description": "Acceleration",
            "video_prompt": (
                "Animated 3D Pixar vertical 9:16: same train on straight track, "
                "speedometer needle rises smoothly, green arrow shows forward direction, "
                "landscape streaks past, driver cabin view, dynamic camera dolly"
            ),
            "math_overlay": "a = \\Delta v / \\Delta t",
            "shot_type": "journey",
            "reveals_formula": False,
        },
        {
            "scene_number": 3,
            "title": "The kinematic idea",
            "duration_seconds": 22,
            "narration": (
                f"For uniform acceleration we use equations like {eq}. "
                "Distance, velocity, time — all linked on a straight line journey!"
            ),
            "animation_description": "Formula reveal",
            "video_prompt": (
                "Animated 3D Pixar vertical 9:16: train moves at steady acceleration, "
                "glowing motion trail behind, position markers appear along track, "
                "celebration sparkles, wide cinematic shot, same train same track"
            ),
            "math_overlay": eq,
            "shot_type": "reveal",
            "reveals_formula": True,
        },
        {
            "scene_number": 4,
            "title": "Relative motion",
            "duration_seconds": 15,
            "narration": (
                "Two trains on parallel tracks — motion depends on who you watch from! "
                "Which physics topic next? Comment below!"
            ),
            "animation_description": "Recap",
            "video_prompt": (
                "Animated 3D Pixar vertical 9:16: two Indian trains on parallel tracks, "
                "one overtakes the other, student Arjun watches from overpass waving, "
                "sunset sky, playful ending"
            ),
            "math_overlay": None,
            "shot_type": "recap",
            "reveals_formula": False,
        },
    ]


def _pick_template(concept_card: ConceptCard, hook_spec: HookSpec) -> list[dict]:
    topic_lower = concept_card.topic.lower()
    if "lhs" in topic_lower or "rhs" in topic_lower or "linear equation" in topic_lower:
        return build_concept_anchored_scenes(concept_card, hook_spec)
    if _is_physics_motion(concept_card):
        return build_kinematics_story_scenes(concept_card, hook_spec)
    return build_sweets_story_scenes(concept_card, hook_spec)


def _prompt_needs_help(prompt: str) -> bool:
    p = (prompt or "").strip()
    return len(p) < 80


def apply_concept_anchor(arc: StoryArc, concept_card: ConceptCard, hook_spec: HookSpec) -> StoryArc:
    """
    Optional post-process for planner output.

    CONCEPT_ANCHOR_MODE:
      off    — no overrides (default; LLM chooses creative visuals)
      soft   — only fill empty/very short video_prompt or narration
      strict — legacy: replace off-topic beats with fixed templates
    """
    mode = getattr(config, "CONCEPT_ANCHOR_MODE", "off")
    if mode == "off":
        if not arc.scenario_summary:
            arc.scenario_summary = concept_card.definition
        if not arc.scenario_title:
            arc.scenario_title = concept_card.topic[:60]
        return arc

    template_scenes = _pick_template(concept_card, hook_spec)
    by_num = {s.scene_number: s for s in arc.scenes}

    for t in template_scenes:
        n = t["scene_number"]
        scene = by_num.get(n)
        if not scene:
            continue
        if mode == "strict" or _prompt_needs_help(scene.video_prompt):
            scene.video_prompt = t["video_prompt"]
            scene.animation_description = t.get("animation_description", "")[:200]
            print(f"[Concept anchor/{mode}] Beat {n} video_prompt set")
        if mode == "strict" or len((scene.narration or "")) < 40:
            scene.narration = t["narration"]
        if n == 3:
            scene.reveals_formula = True
        if t.get("math_overlay") and not scene.math_overlay:
            scene.math_overlay = t["math_overlay"]

    arc.scenario_title = arc.scenario_title or concept_card.topic[:60]
    arc.scenario_summary = arc.scenario_summary or concept_card.definition
    if not arc.master_video_prompt and arc.scenes:
        arc.master_video_prompt = (arc.scenes[0].video_prompt or "")[:1200]
    arc.quiz_correct_answer = arc.quiz_correct_answer or concept_card.definition[:120]
    return arc

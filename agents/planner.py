"""Story arc planner with 3D scene prompts."""

import json

import config
from utils.json_parse import extract_scene_objects, parse_model_json
from utils.json_prompts import STORY_ARC_EXAMPLE, json_instruction, use_example_prompts
from utils.llm_client import _extract_json, call_llm
from utils.schemas import ConceptCard, HookSpec, Scene, StoryArc


PLANNER_SYSTEM_PROMPT = """You are a master educational video writer for Indian students.
Style: animated story-driven 3D cartoon Shorts that explain math through real-life examples.
Each scene must tell a STORY with concrete characters and situations — NOT abstract descriptions.
The video_prompt field must describe a vivid ANIMATED scene with motion and action, as it will
be fed to an AI video generator. Be very specific about what is happening visually.
Output valid JSON only. Never output JSON Schema."""

SCENES_ONLY_EXAMPLE = """[
  {
    "scene_number": 1,
    "title": "The restaurant problem",
    "duration_seconds": 18,
    "narration": "Riya and three friends are at a restaurant. The total bill is 110 rupees, but they already paid 30 as advance. How much does each person owe now?",
    "animation_description": "Four Indian kids sitting around a colorful restaurant table, a waiter brings a bill on a tray, the total amount glows",
    "manim_hint": "",
    "reveals_formula": false,
    "video_prompt": "3D Pixar cartoon, four Indian school children sitting at a vibrant restaurant table with plates of food, a cartoon waiter walks up carrying a glowing bill on a silver tray, warm colorful lighting, smooth camera push-in, vertical 9:16 portrait format",
    "math_overlay": null,
    "shot_type": "journey"
  },
  {
    "scene_number": 2,
    "title": "Setting up the equation",
    "duration_seconds": 20,
    "narration": "Let x be what each person pays. Four friends times x, minus the 30 rupee advance, equals 110. So 4x minus 30 equals 110!",
    "animation_description": "A giant glowing balance scale appears, blocks with 4x and -30 float onto the left pan, block with 110 floats onto right pan, scale tilts",
    "reveals_formula": false,
    "video_prompt": "3D cartoon animated golden balance scale floating in a magical classroom, colorful glowing number blocks labeled 4x and -30 smoothly fly onto the left pan while a block labeled 110 lands on the right pan, the scale tips and wobbles, sparkle particle effects, cinematic lighting, vertical 9:16",
    "math_overlay": "4x - 30 = 110",
    "shot_type": "journey"
  },
  {
    "scene_number": 3,
    "title": "Solving step by step",
    "duration_seconds": 22,
    "narration": "Add 30 to both sides — now 4x equals 140. Divide by 4 — x equals 35! Each friend pays 35 rupees!",
    "animation_description": "The balance scale transforms: 30 is added to both sides, blocks rearrange, then divides, scale balances perfectly with x=35 glowing golden",
    "reveals_formula": true,
    "video_prompt": "3D cartoon golden balance scale, magical transformation animation as glowing number 30 flies to both pans simultaneously making them change, the blocks rearrange smoothly, then the left side transforms to show a bright glowing x=35, the scale becomes perfectly level, golden celebration sparkles burst out, vertical 9:16",
    "math_overlay": "x = 35",
    "shot_type": "reveal"
  },
  {
    "scene_number": 4,
    "title": "Real-life connection",
    "duration_seconds": 15,
    "narration": "See? Equations help us split bills fairly! What if the bill was 200 rupees? Try it yourself and comment below!",
    "animation_description": "The four friends happily pay 35 each, coins fly into a pile, Arjun turns to camera and waves",
    "reveals_formula": false,
    "video_prompt": "3D Pixar cartoon, four happy Indian school children at a restaurant each placing golden coins on the table, coins stack up in a neat pile, the main character Arjun smiles and gives a thumbs up toward the camera, cheerful warm lighting, vertical 9:16",
    "math_overlay": null,
    "shot_type": "recap"
  }
]"""


def build_planner_prompt(
    concept_card: ConceptCard,
    hook_spec: HookSpec,
    extra_context: str = "",
    scenes_only: bool = False,
) -> str:
    if scenes_only:
        return f"""Create exactly 4 scenes for a Class {concept_card.grade} maths Short about: {concept_card.topic}

HOOK opening: "{hook_spec.opening_line}"
Visual metaphor: {concept_card.visual_metaphor}
Real-world contexts: {concept_card.real_world_hooks[:2]}
Answer this question by end: "{hook_spec.knowledge_gap_question}"

IMPORTANT RULES:
1. Tell a CONCRETE STORY with a real-life example (restaurant bill, cricket scores, shopping, etc.)
2. Use Indian names (Arjun, Riya, Priya) and Indian contexts
3. Scene 1: Set up the real-life problem (NO formula yet)
4. Scene 2: Show how to translate the problem into an equation
5. Scene 3: Solve the equation step by step (this is the REVEAL scene)
6. Scene 4: Connect back to real life + CTA

The video_prompt field will be fed to an AI video generator. Write DETAILED animated scene
descriptions with specific motions, camera angles, and visual actions. Include:
- Character actions (walking, pointing, placing objects)
- Camera movements (push-in, pan, zoom)
- Visual effects (glowing, sparkles, floating numbers)
- Always specify "vertical 9:16" at the end

Return ONLY a JSON ARRAY of 4 scene objects. No wrapper object. Start with [

Each scene needs: scene_number, title, duration_seconds, narration, animation_description,
video_prompt (detailed animated scene for AI video generation), math_overlay (LaTeX or null),
shot_type (journey/reveal/recap), reveals_formula (false except one reveal scene).

Scene 1 must NOT reveal formula. Total duration 65-85 seconds.

Example structure (write NEW content with a DIFFERENT story, do not copy):
{SCENES_ONLY_EXAMPLE}

{extra_context}"""

    example_block = json_instruction(STORY_ARC_EXAMPLE, "StoryArc") if use_example_prompts() else ""
    return f"""Design the story arc for a 60-90 second YouTube Short (9:16 vertical, 3D cartoon).

CONCEPT: {concept_card.topic} (Class {concept_card.grade})
Definition: {concept_card.definition}
Equations: {concept_card.latex_equations}
Visual metaphor: {concept_card.visual_metaphor}

HOOK:
Opening: "{hook_spec.opening_line}"
Question: "{hook_spec.knowledge_gap_question}"
Analogy: {hook_spec.analogy}

{extra_context}

RULES: 4 scenes in "scenes" array, 65-85s total, scene 1 reveals_formula=false.

{example_block}

IMPORTANT: Output ONE JSON object starting with {{"topic": ... NOT a single scene object."""


def _wrap_scenes_to_story_arc(
    scenes_data: list[dict],
    concept_card: ConceptCard,
    hook_spec: HookSpec,
) -> StoryArc:
    """Build full StoryArc from scenes array + card metadata."""
    scenes = [Scene.model_validate(s) for s in scenes_data]
    total = sum(s.duration_seconds for s in scenes)
    distractors = concept_card.common_errors[:3]
    while len(distractors) < 3:
        distractors.append("A common mistake students make")

    correct = concept_card.definition[:120]
    if concept_card.common_errors:
        correct = concept_card.common_errors[0][:120]

    return StoryArc(
        topic=concept_card.topic,
        grade=concept_card.grade,
        total_duration_seconds=total,
        hook_summary=f"Resolves: {hook_spec.knowledge_gap_question}",
        scenes=scenes,
        quiz_question=f"What best describes: {concept_card.topic[:50]}?",
        quiz_correct_answer=correct,
        quiz_distractors=distractors,
    )


def _default_scenes_template(concept_card: ConceptCard, hook_spec: HookSpec) -> list[dict]:
    """Fallback scenes if LLM returns too few."""
    from agents.story_helpers import default_equation

    eq = default_equation(concept_card)
    return [
        {
            "scene_number": 1,
            "title": "Hook journey",
            "duration_seconds": 18,
            "narration": hook_spec.opening_line[:120],
            "animation_description": hook_spec.visual_action[:200],
            "reveals_formula": False,
            "video_prompt": f"3D Pixar cartoon Arjun, {hook_spec.visual_action[:100]}, 9:16 vertical",
            "math_overlay": None,
            "shot_type": "journey",
        },
        {
            "scene_number": 2,
            "title": "See the metaphor",
            "duration_seconds": 20,
            "narration": f"Watch how {concept_card.visual_metaphor[:80]}",
            "animation_description": concept_card.visual_metaphor[:200],
            "reveals_formula": False,
            "video_prompt": f"3D educational cartoon explaining {concept_card.topic[:40]}, 9:16",
            "math_overlay": eq if eq else None,
            "shot_type": "journey",
        },
        {
            "scene_number": 3,
            "title": "The reveal",
            "duration_seconds": 22,
            "narration": "Now you can see why the maths works!",
            "animation_description": "Visual proof of the concept",
            "reveals_formula": True,
            "video_prompt": "3D cartoon maths reveal moment, glowing numbers, 9:16",
            "math_overlay": eq if eq else None,
            "shot_type": "reveal",
        },
        {
            "scene_number": 4,
            "title": "Recap",
            "duration_seconds": 15,
            "narration": "Which NCERT topic should we do next? Comment below!",
            "animation_description": "Student recap",
            "reveals_formula": False,
            "video_prompt": "3D cartoon Indian student thumbs up, classroom, 9:16",
            "math_overlay": None,
            "shot_type": "recap",
        },
    ]


def _merge_scenes(llm_scenes: list[dict], template: list[dict]) -> list[dict]:
    """Use LLM scenes where available, fill gaps from template."""
    by_num = {s.get("scene_number"): s for s in llm_scenes if "scene_number" in s}
    merged = []
    for t in template:
        n = t["scene_number"]
        merged.append(by_num.get(n, t))
    return merged[:4]


def _parse_scenes_array(text: str) -> list[dict]:
    """Parse JSON array of scenes from LLM output."""
    from utils.local_inference import repair_json

    text = repair_json(_extract_json(text))
    # Find array
    start = text.find("[")
    if start >= 0:
        depth = 0
        for j in range(start, len(text)):
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    data = json.loads(text[start : j + 1])
                    if isinstance(data, list) and data:
                        return data
    # Fallback: collect individual scene dicts
    scenes = extract_scene_objects(text)
    if scenes:
        return scenes
    raise ValueError(f"No scenes array found in: {text[:400]}")


def _generate_story_arc_local(
    concept_card: ConceptCard,
    hook_spec: HookSpec,
    extra_context: str = "",
) -> StoryArc:
    """Two-step friendly path for Qwen: scenes array only, wrap in Python."""
    prompt = build_planner_prompt(concept_card, hook_spec, extra_context, scenes_only=True)
    last_err = None

    for attempt in range(1, 4):
        retry = ""
        if attempt > 1:
            retry = "\n\nYou MUST return a JSON ARRAY [ {...}, {...}, {...}, {...} ] with 4 scenes."

        response = call_llm(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=prompt + retry,
            max_tokens=4096,
            temperature=config.LLM_TEMPERATURE_PLANNER,
        )
        try:
            scenes_data = _parse_scenes_array(response)
            template = _default_scenes_template(concept_card, hook_spec)
            if len(scenes_data) < 4:
                print(f"[Planner/local] Got {len(scenes_data)} scene(s), merging with template")
                scenes_data = _merge_scenes(scenes_data, template)
            arc = _wrap_scenes_to_story_arc(scenes_data, concept_card, hook_spec)
            print(f"[Planner/local] Wrapped {len(arc.scenes)} scenes")
            return arc
        except (ValueError, Exception) as e:
            last_err = e
            print(f"[Planner/local] Attempt {attempt} failed: {e}")

    raise ValueError(f"Local planner failed after 3 tries: {last_err}")


def generate_story_arc(
    concept_card: ConceptCard,
    hook_spec: HookSpec,
    extra_context: str = "",
) -> StoryArc:
    if config.VIDEO_UNIFIED_STORY:
        from agents.unified_planner import generate_unified_story_arc

        arc = generate_unified_story_arc(concept_card, hook_spec, extra_context)
    elif config.LLM_PROVIDER == "local":
        arc = _generate_story_arc_local(concept_card, hook_spec, extra_context)
    else:
        arc = _generate_story_arc_cloud(concept_card, hook_spec, extra_context)

    if arc.scenes and arc.scenes[0].reveals_formula:
        raise ValueError("Planner error: Scene 1 cannot have reveals_formula=True")

    total = sum(s.duration_seconds for s in arc.scenes)
    if total < 45 or total > 100:
        raise ValueError(f"Story arc duration {total}s out of bounds (45-100s)")

    print(f"[Planner] {len(arc.scenes)} scenes, {total}s total")
    for i, scene in enumerate(arc.scenes):
        print(f"  Scene {i+1}: '{scene.title}' ({scene.duration_seconds}s)")
    return arc


def _generate_story_arc_cloud(
    concept_card: ConceptCard,
    hook_spec: HookSpec,
    extra_context: str = "",
) -> StoryArc:
    prompt = build_planner_prompt(concept_card, hook_spec, extra_context, scenes_only=False)
    temperature = config.LLM_TEMPERATURE_PLANNER
    last_err = None

    for attempt in range(1, 4):
        retry_note = ""
        if attempt > 1:
            retry_note = (
                '\n\nOutput must start with {"topic": and include "scenes": [ array of 4 scenes ]}'
            )

        response = call_llm(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=prompt + retry_note,
            max_tokens=4096,
            temperature=temperature,
        )
        response = _extract_json(response)
        try:
            return parse_model_json(
                response, StoryArc, prefer_keys={"topic", "scenes", "grade"}
            )
        except ValueError as e:
            last_err = e
            print(f"[Planner] Attempt {attempt} failed: {e}")
            # Try scenes-only recovery
            try:
                scenes_data = _parse_scenes_array(response)
                if len(scenes_data) >= 3:
                    return _wrap_scenes_to_story_arc(scenes_data, concept_card, hook_spec)
            except Exception:
                pass

    raise ValueError(f"Planner invalid output after 3 tries: {last_err}")

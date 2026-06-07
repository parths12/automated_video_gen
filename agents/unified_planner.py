"""Planner for cohesive micro-story: 4 sequential video beats + narration."""

from __future__ import annotations

import json

import config
from agents.story_helpers import (
    default_beat_prompts,
    default_equation,
    sanitize_story_arc,
    story_example_json,
)
from agents.subject_config import planner_system
from agents.planner import (
    _merge_scenes,
    _wrap_scenes_to_story_arc,
)
from utils.json_parse import extract_scene_objects
from utils.llm_client import _extract_json, call_llm
from utils.local_inference import repair_json
from utils.schemas import ConceptCard, HookSpec, StoryArc


def build_unified_planner_prompt(
    concept_card: ConceptCard,
    hook_spec: HookSpec,
    extra_context: str = "",
) -> str:
    eq = default_equation(concept_card) or "(use a formula from the topic if needed)"
    hooks = "; ".join(concept_card.real_world_hooks[:5])
    subj = "physics" if getattr(config, "SUBJECT", "math") == "physics" else "mathematics"
    forbidden = ""
    if subj == "physics":
        forbidden = """
FORBIDDEN for physics (unless the topic is explicitly about trains):
- Vande Bharat, railway platforms, generic school canteen, mithai/sweets division stories
- math overlays like x = 5 or 30-2=28 unless they are real equations for THIS topic
"""
    return f"""Design ONE creative micro-story Short for Class {concept_card.grade} {subj}.

TOPIC: {concept_card.topic}
Definition: {concept_card.definition}
Key equation(s): {concept_card.latex_equations or "derive from definition"}
Visual metaphor (primary inspiration for what to SHOW): {concept_card.visual_metaphor}
Real-world hooks (pick ONE fresh setting — do not default to trains): {hooks}

HOOK opening: "{hook_spec.opening_line}"
Question to answer: "{hook_spec.knowledge_gap_question}"

DUAL LAYER (critical):
- Pick ONE visual setting for the entire video (e.g. only cricket pitch OR only city car — never switch).
- video_prompt = short summary of that beat in the same setting.
- chunk_prompts = array of 3-5 SIMPLE one-action prompts (~5s each). Example: "car at red light", then "car starts rolling", etc. No cramming multiple actions into one string.
- narration = voice explains the concept; audio can mention ideas not literally drawn if the setting stays consistent.

CRITICAL RULES:
1. Teach: {concept_card.definition}
2. ONE continuous visual world across beats 2–4 (same place, same main subject).
3. Pick a setting that fits THIS topic — be creative (sports, traffic, rockets, rivers, markets, lab, etc.).
4. math_overlay only on scenes 2–3 when a real formula applies: {eq}
5. video_prompt: one-line beat summary. chunk_prompts: list of simple 5s actions (optional in JSON; director fills if empty).
6. Scene 3: reveals_formula true. Scene 4: recap + CTA.
7. Total duration 65-85 seconds.
{forbidden}

Return ONE JSON: scenario_title, scenario_summary, master_video_prompt, scenes (array of 4).

Example JSON shape for {subj} — write a NEW story for "{concept_card.topic}", do NOT copy the example literally:
{story_example_json()}

{extra_context}"""


def _parse_unified_story(text: str) -> dict:
    text = repair_json(_extract_json(text))
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object in unified planner output")
    depth = 0
    for j in range(start, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                data = json.loads(text[start : j + 1])
                if isinstance(data, dict) and "scenes" in data:
                    return data
                break
    raise ValueError(f"Could not parse unified story JSON: {text[:400]}")


def _default_unified_template(concept_card: ConceptCard, hook_spec: HookSpec) -> dict:
    from agents.planner import _default_scenes_template

    scenes = _default_scenes_template(concept_card, hook_spec)
    beats = default_beat_prompts(concept_card, hook_spec)
    eq = default_equation(concept_card)
    for s, bp in zip(scenes, beats):
        s["video_prompt"] = bp
        if eq and s["scene_number"] in (2, 3):
            s["math_overlay"] = eq
        elif s["scene_number"] in (2, 3) and s.get("math_overlay") in (None, "x = 5"):
            s["math_overlay"] = None
    return {
        "scenario_title": concept_card.topic[:60],
        "scenario_summary": concept_card.definition[:200],
        "master_video_prompt": beats[0][:500],
        "scenes": scenes,
    }


def _ensure_beat_prompts(
    scenes_data: list[dict], concept_card: ConceptCard, hook_spec: HookSpec
) -> list[dict]:
    beats = default_beat_prompts(concept_card, hook_spec)
    for i, s in enumerate(scenes_data):
        if not (s.get("video_prompt") or "").strip():
            s["video_prompt"] = beats[min(i, len(beats) - 1)]
        if not (s.get("animation_description") or "").strip():
            s["animation_description"] = (s.get("video_prompt") or "")[:200]
    return scenes_data


def generate_unified_story_arc(
    concept_card: ConceptCard,
    hook_spec: HookSpec,
    extra_context: str = "",
) -> StoryArc:
    """Micro-story with 4 sequential video beats."""
    prompt = build_unified_planner_prompt(concept_card, hook_spec, extra_context)
    last_err = None

    for attempt in range(1, 4):
        retry = ""
        if attempt > 1:
            retry = "\n\nReturn JSON with scenario_title, scenario_summary, scenes[4] each with video_prompt."

        sys_prompt = planner_system(getattr(config, "SUBJECT", "math"))
        response = call_llm(
            system_prompt=sys_prompt,
            user_prompt=prompt + retry,
            max_tokens=4096,
            temperature=config.LLM_TEMPERATURE_PLANNER,
        )
        try:
            data = _parse_unified_story(response)
            scenes_data = _ensure_beat_prompts(
                data.get("scenes") or [], concept_card, hook_spec
            )
            if len(scenes_data) < 4:
                template = _default_unified_template(concept_card, hook_spec)
                scenes_data = _merge_scenes(scenes_data, template["scenes"])

            arc = _wrap_scenes_to_story_arc(scenes_data, concept_card, hook_spec)
            arc.unified_story = True
            arc.scenario_title = str(data.get("scenario_title", ""))[:120]
            arc.scenario_summary = str(data.get("scenario_summary", ""))[:500]
            arc.master_video_prompt = str(data.get("master_video_prompt", ""))[:1200]

            if config.CONCEPT_ANCHOR_MODE != "off":
                from agents.concept_story import apply_concept_anchor

                arc = apply_concept_anchor(arc, concept_card, hook_spec)

            arc = sanitize_story_arc(arc, concept_card, hook_spec)
            from agents.visual_director import apply_visual_director

            arc = apply_visual_director(arc, concept_card)
            print(f"[Planner/unified] Scenario: {arc.scenario_title}")
            for s in arc.scenes:
                print(f"  Beat {s.scene_number}: {s.title} — {(s.video_prompt or '')[:70]}...")
            return arc
        except (ValueError, json.JSONDecodeError, Exception) as e:
            last_err = e
            print(f"[Planner/unified] Attempt {attempt} failed: {e}")

    data = _default_unified_template(concept_card, hook_spec)
    arc = _wrap_scenes_to_story_arc(data["scenes"], concept_card, hook_spec)
    arc.unified_story = True
    arc.scenario_title = data["scenario_title"]
    arc.scenario_summary = data["scenario_summary"]
    arc.master_video_prompt = data["master_video_prompt"]
    arc = sanitize_story_arc(arc, concept_card, hook_spec)
    from agents.visual_director import apply_visual_director

    arc = apply_visual_director(arc, concept_card)
    print("[Planner/unified] Using topic-based fallback template")
    return arc

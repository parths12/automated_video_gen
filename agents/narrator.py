"""Narration script generator."""

import json

import config
from utils.json_parse import _find_balanced_json_chunks, parse_model_json
from utils.json_prompts import NARRATION_EXAMPLE, json_instruction, use_example_prompts
from utils.llm_client import _extract_json, call_llm
from utils.schemas import NarrationScript, StoryArc


NARRATOR_SYSTEM_PROMPT = """You write narration for animated math Shorts for Indian students.
Tone: enthusiastic storyteller — fun older sibling explaining maths through a real story.
Short punchy sentences. Return valid JSON only."""


NARRATION_LINES_EXAMPLE = """[
  {"scene_number": 1, "text": "Ever split a bill with friends? Let's see the maths!", "pause_before_seconds": 0},
  {"scene_number": 2, "text": "Left side is what Riya owes. Right side is what Arjun owes.", "pause_before_seconds": 0.5},
  {"scene_number": 3, "text": "When both pay the same, we get x equals 5!", "pause_before_seconds": 1.0},
  {"scene_number": 4, "text": "Which topic next? Comment below!", "pause_before_seconds": 0}
]"""


def _build_narration_from_arc(story_arc: StoryArc, language: str) -> NarrationScript:
    """Deterministic narration from planner scene text — reliable for local LLM."""
    scene_entries = []
    intro = (
        "Let's explore this physics idea clearly — step by step!"
        if getattr(config, "SUBJECT", "math") == "physics"
        else "Let's learn this NCERT idea clearly — step by step!"
    )
    spoken_parts = [intro]

    for s in story_arc.scenes:
        text = (s.narration or "").strip()
        if not text:
            text = f"Scene {s.scene_number}: {s.title}."
        if s.math_overlay and s.math_overlay not in text:
            text = f"{text} Look at the equation: {s.math_overlay}."
        scene_entries.append({
            "scene_number": s.scene_number,
            "text": text,
            "pause_before_seconds": 0.5 if s.scene_number > 1 else 0,
        })
        spoken_parts.append(text)

    spoken_parts.append("Which NCERT topic should we explore next? Tell me in the comments!")
    full_script = " ".join(spoken_parts)

    return NarrationScript(
        full_script=full_script,
        scenes=scene_entries,
        language=language,
        tone="curious_friend",
    )


def _parse_narration_lines(text: str) -> list[dict]:
    """Parse array of {scene_number, text, pause_before_seconds}."""
    from utils.local_inference import repair_json

    text = repair_json(_extract_json(text))
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
                    if isinstance(data, list) and data and "text" in data[0]:
                        return data

    # Collect individual line dicts
    lines = []
    for ch in _find_balanced_json_chunks(text):
        if not ch.startswith("{"):
            continue
        try:
            obj = json.loads(ch)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "text" in obj:
            lines.append(obj)
    if lines:
        return sorted(lines, key=lambda x: x.get("scene_number", 0))
    raise ValueError(f"No narration lines in: {text[:300]}")


def _wrap_narration_lines(lines: list[dict], story_arc: StoryArc, language: str) -> NarrationScript:
    by_num = {ln.get("scene_number"): ln for ln in lines}
    scene_entries = []
    spoken = ["Come on, let's enjoy the magic of maths together!"]

    for s in story_arc.scenes:
        ln = by_num.get(s.scene_number, {})
        text = ln.get("text", s.narration).strip()
        scene_entries.append({
            "scene_number": s.scene_number,
            "text": text,
            "pause_before_seconds": float(ln.get("pause_before_seconds", 0.5 if s.scene_number > 1 else 0)),
        })
        spoken.append(text)

    spoken.append("Which NCERT topic should we explore next? Tell me in the comments!")
    return NarrationScript(
        full_script=" ".join(spoken),
        scenes=scene_entries,
        language=language,
        tone="curious_friend",
    )


def _generate_narration_local(story_arc: StoryArc, language: str) -> NarrationScript:
    """Local path: try LLM for polished lines array; fallback to story_arc text."""
    scenes_text = "\n".join(
        f"Scene {s.scene_number} ({s.duration_seconds}s): {s.narration}"
        for s in story_arc.scenes
    )
    prompt = f"""Write spoken narration lines for a Class {story_arc.grade} maths Short.

Topic: {story_arc.topic}

Scene sketches:
{scenes_text}

Return ONLY a JSON ARRAY of {len(story_arc.scenes)} objects.
Each object: scene_number, text (what narrator SAYS, ~{story_arc.scenes[0].duration_seconds * 2} words max per scene), pause_before_seconds.

Start with [

Example format:
{NARRATION_LINES_EXAMPLE}"""

    try:
        response = call_llm(
            system_prompt=NARRATOR_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=2000,
            temperature=config.LLM_TEMPERATURE_NARRATOR,
        )
        lines = _parse_narration_lines(response)
        if len(lines) < len(story_arc.scenes):
            print(f"[Narrator/local] Got {len(lines)} lines, using story_arc fallback merge")
            base = _build_narration_from_arc(story_arc, language)
            by_num = {ln.get("scene_number"): ln for ln in lines}
            merged = []
            for entry in base.scenes:
                sn = entry["scene_number"]
                if sn in by_num:
                    entry = {**entry, "text": by_num[sn].get("text", entry["text"])}
                merged.append(entry)
            return NarrationScript(
                full_script=" ".join(["Come on, let's enjoy the magic of maths together!"]
                    + [e["text"] for e in merged]
                    + ["Which NCERT topic should we explore next? Tell me in the comments!"]),
                scenes=merged,
                language=language,
                tone="curious_friend",
            )
        script = _wrap_narration_lines(lines, story_arc, language)
        print(f"[Narrator/local] LLM polished {len(lines)} lines")
        return script
    except Exception as e:
        print(f"[Narrator/local] LLM skipped ({e}), using story_arc narration")
        return _build_narration_from_arc(story_arc, language)


def generate_narration(story_arc: StoryArc, language: str = "en") -> NarrationScript:
    if config.LLM_PROVIDER == "local":
        script = _generate_narration_local(story_arc, language)
        print(f"[Narrator] Script: {len(script.full_script.split())} words")
        return script

    example_block = json_instruction(NARRATION_EXAMPLE, "NarrationScript")
    scenes_text = "\n\n".join(
        f"SCENE {s.scene_number}: {s.title} ({s.duration_seconds}s)\n"
        f"Narration sketch: {s.narration}"
        for s in story_arc.scenes
    )

    prompt = f"""Write final narration for this video.

Topic: {story_arc.topic}
Grade: {story_arc.grade}
Language: {language}

STORY ARC:
{scenes_text}

Output JSON with "full_script" (all lines joined) AND "scenes" array.
{example_block}

Start with {{"full_script":"""

    for attempt in range(1, 4):
        response = call_llm(
            system_prompt=NARRATOR_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=2500,
            temperature=0.5,
        )
        response = _extract_json(response)
        try:
            script = parse_model_json(
                response, NarrationScript, prefer_keys={"full_script", "scenes"}
            )
            script = script.model_copy(update={"language": language})
            print(f"[Narrator] Script: {len(script.full_script.split())} words")
            return script
        except ValueError:
            try:
                lines = _parse_narration_lines(response)
                script = _wrap_narration_lines(lines, story_arc, language)
                print(f"[Narrator] Wrapped {len(lines)} narration lines")
                return script
            except Exception as e:
                if attempt == 3:
                    print(f"[Narrator] Fallback to story_arc text: {e}")
                    return _build_narration_from_arc(story_arc, language)

    return _build_narration_from_arc(story_arc, language)

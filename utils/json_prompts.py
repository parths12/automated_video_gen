"""Example-based JSON prompts for local LLMs (avoid dumping Pydantic JSON Schema)."""

import config

HOOK_SPEC_EXAMPLE = """{
  "hook_type": "mystery_opener",
  "opening_line": "What if both sides of a scale must always match — can you find the missing weight?",
  "visual_action": "3D cartoon Arjun shrinks and walks toward a giant glowing golden balance scale",
  "knowledge_gap_question": "What makes x=5 the correct solution?",
  "analogy": "An equation is a balance scale — both pans must stay equal",
  "india_context": "Arjun in a colourful Indian classroom before maths exam"
}"""

STORY_ARC_EXAMPLE = """{
  "topic": "LHS, RHS and solutions of linear equations",
  "grade": 8,
  "total_duration_seconds": 75,
  "hook_summary": "The magical scale balances when x=5, showing LHS equals RHS",
  "scenes": [
    {
      "scene_number": 1,
      "title": "Enter the scale",
      "duration_seconds": 18,
      "narration": "Let's shrink and step onto this giant balance scale!",
      "animation_description": "Arjun walks toward glowing golden scale",
      "manim_hint": "",
      "reveals_formula": false,
      "video_prompt": "3D Pixar cartoon Indian boy Arjun approaches giant golden balance scale in bright classroom, 9:16 vertical",
      "math_overlay": null,
      "shot_type": "journey"
    },
    {
      "scene_number": 2,
      "title": "LHS and RHS",
      "duration_seconds": 20,
      "narration": "Left pan is 2x minus 3. Right pan is 7.",
      "animation_description": "Labels appear on left and right pans",
      "reveals_formula": false,
      "video_prompt": "3D cartoon balance scale with left pan glowing LHS and right pan RHS, educational, 9:16",
      "math_overlay": "2x - 3 = 7",
      "shot_type": "journey"
    },
    {
      "scene_number": 3,
      "title": "The solution",
      "duration_seconds": 22,
      "narration": "When x equals 5, the scale is perfectly balanced!",
      "animation_description": "Scale levels, x=5 glows",
      "reveals_formula": true,
      "video_prompt": "3D cartoon balance scale perfectly level with glowing x=5, celebration, 9:16",
      "math_overlay": "x = 5",
      "shot_type": "reveal"
    },
    {
      "scene_number": 4,
      "title": "Recap",
      "duration_seconds": 15,
      "narration": "Which topic should we explore next? Comment below!",
      "animation_description": "Arjun smiles, question mark",
      "reveals_formula": false,
      "video_prompt": "3D cartoon student Arjun thumbs up with balanced scale behind, 9:16",
      "math_overlay": null,
      "shot_type": "recap"
    }
  ],
  "quiz_question": "For 2x-3=7, why is x=5 a solution?",
  "quiz_correct_answer": "Both sides are equal when x=5",
  "quiz_distractors": ["x can be any number", "Only LHS must equal 7", "We never check RHS"]
}"""

NARRATION_EXAMPLE = """{
  "full_script": "Come on, let's enjoy the magic of maths together! Today we enter a giant balance scale...",
  "scenes": [
    {"scene_number": 1, "text": "Let's shrink and step onto this scale!", "pause_before_seconds": 0},
    {"scene_number": 2, "text": "Left side: 2x minus 3. Right side: 7.", "pause_before_seconds": 0.5}
  ],
  "language": "en",
  "tone": "curious_friend"
}"""


def use_example_prompts() -> bool:
    """Local/smaller models confuse JSON Schema with output — use filled examples."""
    return config.LLM_PROVIDER in ("local", "mock")


def json_instruction(example: str, label: str = "JSON object") -> str:
    if use_example_prompts():
        return f"""Return ONE {label} with REAL content (strings, numbers, arrays of scenes).
Do NOT return JSON Schema. Do NOT return {{"type": "string"}} or property definitions.
Copy the STRUCTURE of this example and fill with new content for the task:

{example}"""
    return ""

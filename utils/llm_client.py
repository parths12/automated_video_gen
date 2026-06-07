"""Provider-agnostic LLM client with mock fallback for offline runs."""

import json
import os
import re

import config


def _extract_json(text: str) -> str:
    """Strip markdown fences and extract JSON from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4000,
    temperature: float | None = None,
    model: str | None = None,
) -> str:
    """
    Single LLM call. Returns raw text response.
    Uses LLM_PROVIDER from config: local | gemini | anthropic | openai | mock
    """
    provider = config.LLM_PROVIDER
    model = model or config.LLM_MODEL
    if temperature is None:
        temperature = config.LLM_TEMPERATURE_DEFAULT

    if provider == "mock":
        return _mock_response(system_prompt, user_prompt)

    if provider == "local":
        from utils.local_inference import generate_text_local, repair_json
        raw = generate_text_local(system_prompt, user_prompt, max_tokens=max_tokens, temperature=temperature)
        return repair_json(raw)

    if provider == "anthropic":
        if not config.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY required when LLM_PROVIDER=anthropic")
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text

    if provider == "openai":
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY required when LLM_PROVIDER=openai")
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""

    if provider == "gemini":
        if not config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY required when LLM_PROVIDER=gemini")
        import time

        from google.genai import types

        from utils.gemini_client import get_genai_client

        client = get_genai_client()
        last_err = None
        for attempt in range(4):
            try:
                response = client.models.generate_content(
                    model=model or config.GEMINI_MODEL,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    ),
                )
                return response.text or ""
            except Exception as e:
                last_err = e
                if "429" in str(e) and attempt < 3:
                    time.sleep(40 * (attempt + 1))
                    continue
                raise
        raise last_err

    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


def _mock_response(system_prompt: str, user_prompt: str) -> str:
    """Deterministic mock responses for offline pipeline testing."""
    up = user_prompt.lower()
    sp = system_prompt.lower()

    if "extract all distinct" in up or "concept cards" in up:
        return json.dumps(_MOCK_CONCEPT_CARDS)
    if "creative hook" in up or "hookspec" in up:
        return json.dumps(_MOCK_HOOK)
    if "final narration" in up or "narrationscript" in up or "write final narration" in up:
        return json.dumps(_MOCK_NARRATION)
    if "design the story arc" in up or ("story arc" in up and "scene" in up):
        return json.dumps(_MOCK_STORY_ARC)
    if "chosen_answer" in up or "class 8 student" in sp:
        return json.dumps(
            {
                "chosen_answer": "A",
                "chosen_text": "Both sides must stay equal — like a balance scale",
                "reasoning": "The video showed the scale staying balanced.",
                "what_was_unclear": "",
            }
        )
    return json.dumps({"status": "mock_ok"})


_MOCK_CONCEPT_CARDS = [
    {
        "topic": "Linear expressions vs linear equations",
        "grade": 8,
        "chapter_name": "Linear Equations in One Variable",
        "chapter_number": 2,
        "difficulty": "foundational",
        "definition": "A linear expression has one variable with power 1. An equation uses = and has expressions on both sides.",
        "latex_equations": ["2x - 3", "2x - 3 = 7", "x = 5"],
        "worked_examples": [
            {
                "problem_statement": "Is 2x - 3 = 7 an equation?",
                "solution_steps": ["It has an equality sign", "Left side is 2x-3, right side is 7"],
                "answer": "Yes, it is a linear equation in one variable",
            }
        ],
        "common_errors": ["Confusing expressions with equations", "Thinking x^2 terms are linear"],
        "prerequisites": ["Variables", "Algebraic expressions"],
        "real_world_hooks": [
            "A chaiwala charges ₹15 base plus ₹8 per km — students write total fare as 15+8k.",
            "Riya saves ₹50 per week starting with ₹200 — amount after w weeks is 200+50w.",
            "An auto meter shows ₹25 plus ₹12 per km — fare equation for a 5 km ride.",
        ],
        "visual_metaphor": "A balance scale where both pans must always stay level",
    },
    {
        "topic": "LHS, RHS and solutions of linear equations",
        "grade": 8,
        "chapter_name": "Linear Equations in One Variable",
        "chapter_number": 2,
        "difficulty": "core",
        "definition": "LHS is the left expression, RHS the right. A solution is the value of x that makes both sides equal.",
        "latex_equations": ["2x - 3 = 7", "x = 5", "LHS = RHS"],
        "worked_examples": [
            {
                "problem_statement": "Verify x=5 for 2x-3=7",
                "solution_steps": ["Substitute x=5", "LHS = 2(5)-3 = 7", "RHS = 7", "LHS = RHS"],
                "answer": "x=5 is a solution",
                "ncert_exercise_ref": "Section 2.1",
            }
        ],
        "common_errors": ["Checking only LHS", "Assuming any number is a solution"],
        "prerequisites": ["Linear expressions vs equations"],
        "real_world_hooks": [
            "Two friends split a ₹110 bill equally — find share using x.",
            "Train ticket: child pays half of adult fare, total ₹450 for 1 adult + 2 children.",
            "Diwali sale: price after ₹200 discount equals half original — find original.",
        ],
        "visual_metaphor": "A detective scale that lights up green only when LHS equals RHS",
    },
    {
        "topic": "Solving equations with variables on both sides",
        "grade": 8,
        "chapter_name": "Linear Equations in One Variable",
        "chapter_number": 2,
        "difficulty": "core",
        "definition": "Collect variable terms on one side and constants on the other, then solve.",
        "latex_equations": ["2x - 3 = x + 2", "x = 5", "5x + 7 = 3x - 14"],
        "worked_examples": [
            {
                "problem_statement": "Solve 2x - 3 = x + 2",
                "solution_steps": [
                    "Subtract x from both sides: x - 3 = 2",
                    "Add 3 to both sides: x = 5",
                ],
                "answer": "x = 5",
                "ncert_exercise_ref": "Example 1, Section 2.2",
            }
        ],
        "common_errors": [
            "Moving x without changing sign",
            "Applying operation to only one side",
        ],
        "prerequisites": ["LHS, RHS and solutions"],
        "real_world_hooks": [
            "Riya has ₹200+50w, Priya has ₹80+80w — when are savings equal?",
            "IPL: Virat scores 3× Rohit minus 10; together 90 runs.",
            "Two trains approach — find meeting time using distance equations.",
        ],
        "visual_metaphor": "Moving weights between pans of a balance scale to isolate x",
    },
    {
        "topic": "Reducing equations with fractions to simpler form",
        "grade": 8,
        "chapter_name": "Linear Equations in One Variable",
        "chapter_number": 2,
        "difficulty": "core",
        "definition": "Multiply both sides by the LCM of denominators to clear fractions, then solve.",
        "latex_equations": [
            r"\frac{5x}{2} + \frac{7}{2} = \frac{3x}{2} - 14",
            "10x + 7 = 3x - 28",
            "x = -5",
        ],
        "worked_examples": [
            {
                "problem_statement": "Solve 5x/2 + 7/2 = 3x/2 - 14",
                "solution_steps": [
                    "Multiply both sides by 2",
                    "5x + 7 = 3x - 28",
                    "2x = -35",
                    "x = -5",
                ],
                "answer": "x = -5",
                "ncert_exercise_ref": "Example 2, Section 2.2",
            }
        ],
        "common_errors": ["Forgetting to multiply every term", "Wrong LCM"],
        "prerequisites": ["Solving with variables on both sides"],
        "real_world_hooks": [
            "Sharing a pizza cut into 8 slices — 3/8 of pizza eaten.",
            "Mixing 1/3 milk and 2/3 water in a bottle.",
            "EMI: half payment now, half later with fraction interest.",
        ],
        "visual_metaphor": "Splitting a chocolate bar into equal pieces so every fraction becomes whole numbers",
    },
    {
        "topic": "Applications of linear equations in one variable",
        "grade": 8,
        "chapter_name": "Linear Equations in One Variable",
        "chapter_number": 2,
        "difficulty": "extension",
        "definition": "Translate word problems into linear equations, solve, and check if the answer fits the situation.",
        "latex_equations": ["ax + b = c", "x = \\frac{c-b}{a}"],
        "worked_examples": [
            {
                "problem_statement": "A number increased by 8 is 26. Find the number.",
                "solution_steps": ["Let number be x", "x + 8 = 26", "x = 18"],
                "answer": "18",
            }
        ],
        "common_errors": ["Wrong variable setup", "Not checking if answer is realistic"],
        "prerequisites": ["Reducing equations with fractions"],
        "real_world_hooks": [
            "Age puzzle: father is 3× son's age; in 12 years twice son's age.",
            "Shopkeeper profit: cost + 20% = selling price ₹240.",
            "Cricket: runs in two innings total 180, second is 30 more than first.",
        ],
        "visual_metaphor": "A story comic strip where each panel becomes one line of the equation",
    },
]

_MOCK_HOOK = {
    "hook_type": "real_world_anchor",
    "opening_line": "Arjun's balance scale is tilted — can you fix it before the exam bell rings?",
    "visual_action": "3D cartoon student Arjun peers at a golden balance scale tipping left, numbers glowing on each pan.",
    "knowledge_gap_question": "What does it mean for both sides of an equation to be equal?",
    "analogy": "An equation is a balance scale — both pans must stay level",
    "india_context": "Arjun preparing for Class 8 maths exam in a colourful Indian classroom",
}

_MOCK_STORY_ARC = {
    "topic": "LHS, RHS and solutions of linear equations",
    "grade": 8,
    "total_duration_seconds": 75,
    "hook_summary": "The tilted scale becomes balanced when x=5, answering why LHS must equal RHS.",
    "scenes": [
        {
            "scene_number": 1,
            "title": "Enter the scale",
            "duration_seconds": 18,
            "narration": "Let's shrink down and step onto this giant balance scale. Feel how it wobbles?",
            "animation_description": "Camera zooms into 3D golden balance scale in Indian classroom",
            "reveals_formula": False,
            "video_prompt": "3D cartoon educational style, Indian student avatar Arjun shrinks and walks toward a giant glowing golden balance scale in a bright classroom, Pixar-like lighting, vertical 9:16",
            "math_overlay": None,
            "shot_type": "journey",
        },
        {
            "scene_number": 2,
            "title": "LHS and RHS",
            "duration_seconds": 20,
            "narration": "Left pan holds 2x minus 3. Right pan holds 7. The scale only balances when both are equal.",
            "animation_description": "Labels LHS and RHS appear on pans with weights",
            "reveals_formula": False,
            "video_prompt": "3D cartoon balance scale, left pan labeled LHS with blocks 2x and -3, right pan labeled RHS with block 7, soft educational colours, 9:16 vertical",
            "math_overlay": "2x - 3 = 7",
            "shot_type": "journey",
        },
        {
            "scene_number": 3,
            "title": "Find the solution",
            "duration_seconds": 22,
            "narration": "Watch — when x equals 5, both sides weigh the same. That value is the solution!",
            "animation_description": "Scale balances, x=5 glows",
            "reveals_formula": True,
            "video_prompt": "3D cartoon balance scale perfectly level, glowing number x=5, celebration particles, Indian classroom background, 9:16",
            "math_overlay": "x = 5",
            "shot_type": "reveal",
        },
        {
            "scene_number": 4,
            "title": "Recap question",
            "duration_seconds": 15,
            "narration": "So what makes a value a solution? Comment below — which NCERT topic should we explore next?",
            "animation_description": "Arjun thumbs up, question mark",
            "reveals_formula": False,
            "video_prompt": "3D cartoon student Arjun smiling with question mark, balance scale balanced behind, YouTube Shorts end card style, 9:16",
            "math_overlay": None,
            "shot_type": "recap",
        },
    ],
    "quiz_question": "For 2x - 3 = 7, what makes x = 5 a solution?",
    "quiz_correct_answer": "Both sides must stay equal — like a balance scale",
    "quiz_distractors": [
        "x can be any number we like",
        "Only the left side needs to equal 7",
        "We never need to check RHS",
    ],
}

_MOCK_NARRATION = {
    "full_script": (
        "Come on, let's enjoy the magic of maths together! "
        "Today we're travelling inside a giant balance scale. "
        "The left pan shows 2x minus 3. The right pan shows 7. "
        "When x equals 5, both pans level out — that's the solution! "
        "An equation is balanced only when LHS equals RHS. "
        "Which topic should we explore next? Tell me in the comments!"
    ),
    "scenes": [
        {"scene_number": 1, "text": "Let's shrink and step onto this giant balance scale.", "pause_before_seconds": 0},
        {"scene_number": 2, "text": "Left pan: 2x minus 3. Right pan: 7.", "pause_before_seconds": 0.5},
        {"scene_number": 3, "text": "When x equals 5, both sides balance!", "pause_before_seconds": 1.0},
        {"scene_number": 4, "text": "Which topic next? Comment below!", "pause_before_seconds": 0},
    ],
    "language": "en",
    "tone": "curious_friend",
}

# Creative Agents — Hook, Planner, Narrator

## Overview

These three agents form the creative core of the pipeline. They run in sequence:

```
ConceptCard → [Hook Agent] → HookSpec → [Planner] → StoryArc → [Narrator] → NarrationScript
```

The Planner and Narrator can run in parallel after the Planner produces the `StoryArc`, but the Hook Agent must always run first.

---

## Agent 1: hook_agent.py

**File location:** `agents/hook_agent.py`

### Purpose

The Hook Agent is the novel research contribution of this project. It runs BEFORE the planner and is responsible for the opening 15 seconds of the video. Its job is to create a **knowledge gap** — something the student desperately wants to know the answer to — before any math is explained.

This is what separates a video students skip from one they finish.

### What Makes a Good Hook

A good hook does three things:
1. Creates a question the student doesn't have the answer to yet
2. Uses a context the student has personally experienced or cares about
3. Makes the resolution of that question feel important, not just academic

A bad hook is: "Today we will learn about linear equations."
A good hook is: "Riya and Priya are both saving money, but Priya starts with less. Who saves more? And when will they have the same amount? The answer requires something called a linear equation — and once you know it, you can answer any 'when will they be equal' question in 20 seconds."

### Implementation

```python
# agents/hook_agent.py

import json
from utils.schemas import ConceptCard, HookSpec, HookType
from utils.llm_client import call_llm
from pydantic import ValidationError


HOOK_AGENT_SYSTEM_PROMPT = """You are the Creative Hook Agent for an educational mathematics video pipeline.

Your ONLY job is to design the most compelling opening 15 seconds for a math video.
You are NOT explaining the concept — you are creating the moment that makes a student WANT to learn it.

You are writing for Indian students aged 12–18. Use Indian contexts, names, sports, and situations.
Common Indian names: Riya, Priya, Arjun, Rohan, Meera, Kavya, Siddharth, Ananya.
Indian contexts: IPL cricket, IRCTC train journeys, Diwali/festival sales, auto-rickshaw fares,
street vendors (chaiwala, fruitwala), agricultural land division, competitive exam preparation,
WhatsApp group problems, UPI transactions.

You must return ONLY valid JSON matching the HookSpec schema. No preamble, no explanation."""


HOOK_STRATEGIES_GUIDE = """
Hook strategy guide — pick the best ONE for this concept:

CURIOSITY_GAP: State that something surprising is true, but don't explain why yet.
  Works best for: geometry, number theory, probability
  Example: "Every even number greater than 2 is the sum of two primes. No one has ever proved why — 
  but you can verify it yourself in the next 60 seconds."

WTF_FACT: Lead with a fact that seems impossible until you do the math.
  Works best for: large numbers, exponential growth, fractions, percentages
  Example: "If you fold a piece of paper 42 times, it would reach the Moon. Let's prove it."

REAL_WORLD_ANCHOR: Open with a specific, concrete Indian situation the student can picture.
  Works best for: linear equations, ratios, percentages, mensuration
  Example: "Arjun runs a chai stall. He wants to know: how many cups must he sell to break even?"

MYSTERY_OPENER: Start in the middle of a story. Don't explain what's happening yet.
  Works best for: any concept where the application is more exciting than the concept itself
  Example: "A detective gets this clue: 'I am three times my son's age. In 12 years, 
  I'll be twice his age.' One equation. Two unknowns. How?"

CULTURAL_ANALOGY: Map the concept to something deeply familiar from Indian daily life.
  Works best for: abstract concepts, algebraic structures, geometric properties
  Example for variables: "In cricket, we say 'runs scored = x'. We don't know x yet — 
  it's the unknown that changes every match. Algebra is just cricket scorekeeping with unknowns."
"""


def generate_hook(concept_card: ConceptCard) -> HookSpec:
    """
    Generates a creative hook for a concept card.
    
    The hook must:
    1. Create a knowledge gap (a question the student wants answered)
    2. Use India-specific context
    3. NOT explain the concept — only create desire to learn it
    
    Args:
        concept_card: fully populated ConceptCard
        
    Returns:
        validated HookSpec
    """
    schema_str = json.dumps(HookSpec.model_json_schema(), indent=2)
    
    prompt = f"""Generate a creative hook for this NCERT concept:

TOPIC: {concept_card.topic}
CLASS: {concept_card.grade}
DEFINITION (do NOT use this in the hook — it's for your reference only): {concept_card.definition}
AVAILABLE REAL-WORLD CONTEXTS: {json.dumps(concept_card.real_world_hooks, indent=2)}
VISUAL METAPHOR AVAILABLE: {concept_card.visual_metaphor}
COMMON STUDENT ERRORS (hook should NOT address these — only create curiosity): {concept_card.common_errors}

{HOOK_STRATEGIES_GUIDE}

Now generate the hook. Return JSON matching this schema:
{schema_str}

Critical rules:
- opening_line: this is spoken aloud in the video. Max 40 words. Must end with a question or cliffhanger.
- visual_action: describes what MANIM ANIMATES in seconds 0–5. Must be visual, not textual.
  Example: "An auto-rickshaw drives across the screen. Fare meter ticks up. It stops at ₹55."
  NOT: "Text appears showing the problem."
- knowledge_gap_question: the ONE question the student now wants answered
- analogy: ONE concrete metaphor the ENTIRE video will use (the illustrator will animate this)
- india_context: the specific Indian situation you chose (empty string if hook_type is not real_world_anchor)"""

    response = call_llm(
        system_prompt=HOOK_AGENT_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=1500,
        temperature=0.7    # higher temperature = more creative hooks
    )
    
    try:
        hook_data = json.loads(response)
        hook = HookSpec.model_validate(hook_data)
        print(f"[Hook Agent] Generated '{hook.hook_type}' hook: '{hook.opening_line[:60]}...'")
        return hook
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Hook agent returned invalid output: {e}\nRaw: {response[:300]}")
```

---

## Agent 2: planner.py

**File location:** `agents/planner.py`

### Purpose

The Planner takes the `ConceptCard` and `HookSpec` and produces a `StoryArc` — the scene-by-scene blueprint for the entire video. 

The Planner must:
- Design scenes that resolve the knowledge gap the hook created
- Never put the formula/definition in the first scene
- Keep total video under 90 seconds
- Plant the quiz question's answer naturally somewhere in the video

### Implementation

```python
# agents/planner.py

import json
from utils.schemas import ConceptCard, HookSpec, StoryArc, Scene
from utils.llm_client import call_llm
from pydantic import ValidationError


PLANNER_SYSTEM_PROMPT = """You are a master educational video writer specialising in mathematics for Indian students.
You write in the style of 3Blue1Brown — visual, intuitive, story-driven, never dry or textbook-like.

You are given a concept card and a hook, and you must design the scene-by-scene story arc.
The video is 60–90 seconds long (Shorts/Reels format).

Core principle: The animation IS the explanation. The narration ACCOMPANIES it, not replaces it.
Never plan a scene where someone is just reading text. Every scene must have a VISUAL ACTION.

You must return ONLY valid JSON. No preamble, no explanation."""


def build_planner_prompt(
    concept_card: ConceptCard,
    hook_spec: HookSpec,
    schema_str: str
) -> str:
    return f"""Design the story arc for this educational video.

CONCEPT CARD:
Topic: {concept_card.topic}
Grade: {concept_card.grade}
Definition: {concept_card.definition}
Key equations (LaTeX): {concept_card.latex_equations}
Common errors: {concept_card.common_errors}
Visual metaphor: {concept_card.visual_metaphor}

HOOK ALREADY DESIGNED:
Hook type: {hook_spec.hook_type}
Opening line: "{hook_spec.opening_line}"
Visual action in first 5 seconds: {hook_spec.visual_action}
Knowledge gap question: "{hook_spec.knowledge_gap_question}"
Core analogy for the video: {hook_spec.analogy}

STORY ARC RULES:
1. Scene 1 must resolve DIRECTLY from the hook's visual_action. Do not restart.
2. Scene 1 must show the ANALOGY (visual_metaphor), NOT the formula.
3. The formula/equation appears in Scene 2 or later — after intuition is built.
4. Each scene must have a clear visual action (what Manim animates).
5. Scene transitions must feel CAUSAL — each scene answers the previous scene's implicit question.
6. Last scene = resolution. The hook's knowledge_gap_question gets answered here.
7. Total duration: 65–85 seconds. Allocate ~15s per scene.
8. Max 5 scenes.

SCENE NARRATION RULES:
- Use second-person ("you", "your") — speak directly to the student
- Ask rhetorical questions before revealing answers ("So what happens when...?")
- Pause before reveals: add "(pause)" in narration where Manim should animate silently
- Never say "In this video, we will learn..." or "Today's topic is..."

QUIZ QUESTION RULES:
- Must be a direct application of the core concept
- Must be answerable from watching the video
- Must have 3 distractors that each reflect one of the concept's common_errors

Return JSON matching this schema:
{schema_str}"""


def generate_story_arc(
    concept_card: ConceptCard,
    hook_spec: HookSpec
) -> StoryArc:
    """
    Generates the complete story arc for the video.
    
    Args:
        concept_card: the concept being explained
        hook_spec: the creative hook already generated
        
    Returns:
        validated StoryArc with 3–5 scenes
    """
    schema_str = json.dumps(StoryArc.model_json_schema(), indent=2)
    
    prompt = build_planner_prompt(concept_card, hook_spec, schema_str)
    
    response = call_llm(
        system_prompt=PLANNER_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=3000,
        temperature=0.3
    )
    
    try:
        arc_data = json.loads(response)
        arc = StoryArc.model_validate(arc_data)
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Planner returned invalid output: {e}\nRaw: {response[:300]}")
    
    # Validate that scene 1 doesn't reveal the formula
    if arc.scenes and arc.scenes[0].reveals_formula:
        raise ValueError("Planner error: Scene 1 cannot have reveals_formula=True")
    
    # Validate duration
    total = sum(s.duration_seconds for s in arc.scenes)
    if total < 45 or total > 100:
        raise ValueError(f"Story arc duration {total}s is out of bounds (45–100s)")
    
    print(f"[Planner] Story arc: {len(arc.scenes)} scenes, {total}s total")
    for i, scene in enumerate(arc.scenes):
        print(f"  Scene {i+1}: '{scene.title}' ({scene.duration_seconds}s)")
    
    return arc
```

---

## Agent 3: narrator.py

**File location:** `agents/narrator.py`

### Purpose

The Narrator writes the final spoken script, scene by scene, with timing cues. It takes the `StoryArc` (which has rough narration sketches) and polishes them into natural, engaging speech with deliberate pauses.

### Key Narration Principles

- **Pause before reveals**: silence before a visual reveal is more powerful than narrating it
- **Socratic beats**: ask a question, let Manim show the answer, then confirm it
- **Conversational, not formal**: "watch what happens" not "observe the following transformation"
- **Hinglish option**: for Class 6–8, mixing Hindi words increases relatability (optional)

### Implementation

```python
# agents/narrator.py

import json
from utils.schemas import StoryArc, NarrationScript
from utils.llm_client import call_llm
from pydantic import ValidationError


NARRATOR_SYSTEM_PROMPT = """You are writing the narration script for a 3Blue1Brown-style math explainer video for Indian students.

The narration must feel like a curious, excited friend explaining something cool — not a teacher reading from a textbook.

Tone guide:
- Use "you" and "your" — speak directly to the student
- Short sentences. Never more than 20 words in one breath.
- Build suspense: "What do you think happens next?" → (pause 1.5s) → "Exactly that."
- Celebrate aha moments: "And THAT is why this works every time."
- Mark deliberate pauses as "(pause Xs)" where X is seconds
- Mark animation cues as "[ANIMATE: brief description]" — these cue the renderer

Return ONLY valid JSON. No preamble."""


def generate_narration(story_arc: StoryArc, language: str = "en") -> NarrationScript:
    """
    Generates the polished narration script from the story arc.
    
    Args:
        story_arc: the planned story arc
        language: "en" for English, "hi" for Hindi, "en-hi" for Hinglish
        
    Returns:
        validated NarrationScript
    """
    schema_str = json.dumps(NarrationScript.model_json_schema(), indent=2)
    
    scenes_text = "\n\n".join([
        f"SCENE {s.scene_number}: {s.title} ({s.duration_seconds}s)\n"
        f"Animation happening: {s.animation_description}\n"
        f"Rough narration sketch: {s.narration}"
        for s in story_arc.scenes
    ])
    
    prompt = f"""Write the final narration script for this video.

Topic: {story_arc.topic}
Grade: {story_arc.grade}
Language: {language}

STORY ARC:
{scenes_text}

For each scene, write the FINAL narration. Requirements:
- Fit within the scene's duration (roughly 2.5 words per second for clear speech)
- Use "(pause Xs)" to mark deliberate pauses before visual reveals
- Use "[ANIMATE: ...]" to mark moments when you stop talking and let the animation speak
- End each scene with a bridge to the next ("but here's where it gets interesting...")
- The last scene must explicitly answer the opening hook question

Return JSON matching: {schema_str}"""
    
    response = call_llm(
        system_prompt=NARRATOR_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=2500,
        temperature=0.5
    )
    
    try:
        narration_data = json.loads(response)
        narration_data["language"] = language
        script = NarrationScript.model_validate(narration_data)
        print(f"[Narrator] Script: {len(script.full_script.split())} words")
        return script
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Narrator returned invalid output: {e}")
```

---

## Testing the Creative Agents

```python
# test_creative_agents.py

import json
from agents.hook_agent import generate_hook
from agents.planner import generate_story_arc
from agents.narrator import generate_narration
from utils.schemas import ConceptCard

# Load a saved concept card
with open("data/concept_cards/class8_ch2/class8_solving_equations_variables_both_sides.json") as f:
    card = ConceptCard.model_validate_json(f.read())

print("=== HOOK AGENT ===")
hook = generate_hook(card)
print(json.dumps(hook.model_dump(), indent=2))

print("\n=== PLANNER ===")
arc = generate_story_arc(card, hook)
print(json.dumps(arc.model_dump(), indent=2))

print("\n=== NARRATOR ===")
script = generate_narration(arc, language="en")
print(script.full_script)
```

### What to Evaluate Manually

When you run the test above, check:

1. Does the hook's `opening_line` make you want to know the answer? Would a 14-year-old keep watching?
2. Does scene 1 of the story arc show the analogy (balance scale, etc.) without showing equations?
3. Does the narration have natural pauses? Does it feel conversational?
4. Is the quiz question answerable from the video content (not from prior knowledge)?

If the hook feels like a textbook intro, increase the temperature of the hook agent to 0.8 and try again. The hook agent benefits most from high temperature.

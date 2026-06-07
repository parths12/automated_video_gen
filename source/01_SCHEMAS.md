# schemas.py — All Data Models

## Purpose

This file defines every data structure that flows between agents. All agents consume and produce these Pydantic models. If you change a schema, you must update the LLM prompts that produce that schema.

**File location:** `utils/schemas.py`

---

## Install Dependencies

```bash
pip install pydantic>=2.0
```

---

## Full Implementation

```python
# utils/schemas.py

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class Difficulty(str, Enum):
    FOUNDATIONAL = "foundational"   # prerequisite concept, e.g. "what is a variable"
    CORE = "core"                   # main exam concept, e.g. "solving linear equations"
    EXTENSION = "extension"         # beyond syllabus, for curious students


class HookType(str, Enum):
    CURIOSITY_GAP = "curiosity_gap"       # pose an unanswered question
    WTF_FACT = "wtf_fact"                 # counterintuitive true statement
    REAL_WORLD_ANCHOR = "real_world_anchor"  # India-specific real situation
    MYSTERY_OPENER = "mystery_opener"      # start mid-story, reveal what's happening later
    CULTURAL_ANALOGY = "cultural_analogy"  # map concept to familiar Indian cultural context


# ─────────────────────────────────────────────
# Phase 1: PDF Parsing Output
# ─────────────────────────────────────────────

class WorkedExample(BaseModel):
    """A single solved problem from the NCERT textbook."""
    problem_statement: str          # the question as written
    solution_steps: list[str]       # ordered list of steps, each step is one sentence
    answer: str                     # final answer
    ncert_exercise_ref: Optional[str] = None  # e.g. "Exercise 2.1, Q3"


class ConceptCard(BaseModel):
    """
    The atomic unit of knowledge extracted from an NCERT chapter.
    One chapter produces multiple ConceptCards.
    This is the input to ALL downstream agents.
    """
    # Identity
    topic: str                      # e.g. "Solving linear equations with variables on both sides"
    grade: int                      # 6 to 12
    chapter_name: str               # e.g. "Linear Equations in One Variable"
    chapter_number: int             # e.g. 2
    difficulty: Difficulty

    # Math content
    definition: str                 # 1–2 sentence plain English definition
    latex_equations: list[str]      # key equations in LaTeX, e.g. ["ax + b = c", "x = \\frac{c-b}{a}"]
    worked_examples: list[WorkedExample]
    common_errors: list[str]        # e.g. ["forgetting to apply the same operation to both sides"]

    # Prerequisites (used to order video generation)
    prerequisites: list[str]        # list of topic names that must be understood first

    # Creative inputs (used by hook_agent)
    real_world_hooks: list[str]     # 3+ India-specific real situations. e.g.:
                                    # "An auto-rickshaw driver charges ₹15 + ₹8/km"
                                    # "A cricket player needs X more runs to reach 1000"
                                    # "EMI calculation for a phone bought on loan"
    visual_metaphor: str            # ONE strong spatial analogy. e.g.:
                                    # "A balance scale — whatever you do to one side,
                                    #  you must do to the other"


# ─────────────────────────────────────────────
# Phase 2a: Hook Agent Output
# ─────────────────────────────────────────────

class HookSpec(BaseModel):
    """
    Output of the Creative Hook Agent.
    Defines the opening 15 seconds of the video.
    The entire story arc must resolve the knowledge_gap_question.
    """
    hook_type: HookType
    opening_line: str               # exact spoken words for first 15 seconds, max 40 words
    visual_action: str              # what Manim shows in seconds 0–5 (before any text appears)
                                    # e.g. "A balance scale animation. Left side: 2x+3. Right side: 11."
    knowledge_gap_question: str     # the ONE question this hook raises that the video answers
                                    # e.g. "What is x? And why does finding it matter?"
    analogy: str                    # core metaphor for the whole video, used by illustrator
                                    # e.g. "Solving an equation = balancing a scale"
    india_context: str              # the specific Indian real-world situation used (if any)


# ─────────────────────────────────────────────
# Phase 2b: Planner Output
# ─────────────────────────────────────────────

class Scene(BaseModel):
    """One scene in the video. A 60-90 second video has 3–5 scenes."""
    scene_number: int
    title: str                      # internal label, not shown in video
    duration_seconds: int           # target duration for this scene
    narration: str                  # what the narrator says during this scene
    animation_description: str      # plain English description of what Manim should show
                                    # Be very specific: "The balance scale tips left. 
                                    #  Numbers animate in on both sides. Scale balances 
                                    #  when x=4 appears."
    manim_hint: str                 # optional technical hint for the illustrator
                                    # e.g. "Use NumberLine, show x sliding to solution"
    reveals_formula: bool           # True only for the scene where the algebraic form appears
                                    # Formula scenes should NEVER be the first scene


class StoryArc(BaseModel):
    """
    Output of the Planner Agent.
    The complete narrative blueprint for the video.
    """
    topic: str
    grade: int
    total_duration_seconds: int     # target: 60–90 for Shorts format
    hook_summary: str               # one line describing how the hook is resolved
    scenes: list[Scene]             # ordered list of scenes
    quiz_question: str              # one MCQ question for TeachQuiz evaluation
    quiz_correct_answer: str
    quiz_distractors: list[str]     # 3 wrong answers that reflect common_errors


# ─────────────────────────────────────────────
# Phase 2c: Illustrator Output
# ─────────────────────────────────────────────

class ManimCode(BaseModel):
    """
    Output of the Illustrator Agent.
    Contains the full Manim Python code for the video.
    """
    scene_class_name: str           # always "VideoScene"
    code: str                       # complete, executable Manim Python code
    manim_version: str              # e.g. "0.18.0" — version it was written for
    estimated_render_seconds: int   # rough estimate
    dependencies: list[str]         # any non-standard imports used


# ─────────────────────────────────────────────
# Phase 2d: Narrator Output
# ─────────────────────────────────────────────

class NarrationScript(BaseModel):
    """
    Output of the Narrator Agent.
    Scene-by-scene narration with timing cues.
    """
    full_script: str                # complete narration text in order
    scenes: list[dict]              # list of {scene_number, text, pause_before_seconds}
                                    # pause_before_seconds: deliberate silence before a reveal
    language: str                   # "en" or "hi" or "en-hi" (Hinglish)
    tone: str                       # "curious_friend" | "excited_teacher" | "story_narrator"


# ─────────────────────────────────────────────
# Phase 3: Evaluation Output
# ─────────────────────────────────────────────

class TeachQuizResult(BaseModel):
    """Output of the TeachQuiz evaluator."""
    topic: str
    quiz_question: str
    correct_answer: str
    llm_answer: str                 # what a simulated student answered
    passed: bool                    # True if llm_answer matches correct_answer
    score: float                    # 0.0 to 1.0
    failure_reason: Optional[str]   # if failed, why — used to improve the next attempt
    replan_suggestion: Optional[str]  # specific instruction for planner on retry


# ─────────────────────────────────────────────
# Orchestrator State (tracks a full pipeline run)
# ─────────────────────────────────────────────

class PipelineRun(BaseModel):
    """Tracks the state of one full concept → video pipeline run."""
    run_id: str                     # uuid
    concept_card: ConceptCard
    hook_spec: Optional[HookSpec] = None
    story_arc: Optional[StoryArc] = None
    manim_code: Optional[ManimCode] = None
    narration_script: Optional[NarrationScript] = None
    quiz_result: Optional[TeachQuizResult] = None
    output_video_path: Optional[str] = None
    attempt_number: int = 1         # increments on retry
    status: str = "pending"         # "pending" | "generating" | "rendering" | "done" | "failed"
    errors: list[str] = []          # log of any errors encountered
```

---

## Important Notes for Cursor

1. All LLM prompts in the agents must instruct the model to return JSON that exactly matches these schemas. Use `model.model_json_schema()` to get the JSON schema string to paste into prompts.

2. Use Pydantic's `.model_validate_json()` to parse LLM output — it will raise a `ValidationError` if the LLM returned bad JSON. The orchestrator catches this and retries.

3. The `ConceptCard.real_world_hooks` list must always contain India-specific examples. This is enforced in the segmenter prompt.

4. `Scene.reveals_formula` must be `False` for the first scene. The orchestrator validates this before passing to the illustrator.

5. `StoryArc.total_duration_seconds` should be 60–90. The orchestrator rejects arcs shorter than 45s or longer than 100s.

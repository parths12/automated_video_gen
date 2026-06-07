"""Pydantic models for all pipeline data structures."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Difficulty(str, Enum):
    FOUNDATIONAL = "foundational"
    CORE = "core"
    EXTENSION = "extension"


class HookType(str, Enum):
    CURIOSITY_GAP = "curiosity_gap"
    WTF_FACT = "wtf_fact"
    REAL_WORLD_ANCHOR = "real_world_anchor"
    MYSTERY_OPENER = "mystery_opener"
    CULTURAL_ANALOGY = "cultural_analogy"


class ShotType(str, Enum):
    ESTABLISHING = "establishing"
    JOURNEY = "journey"
    REVEAL = "reveal"
    RECAP = "recap"


class WorkedExample(BaseModel):
    problem_statement: str
    solution_steps: list[str]
    answer: str
    ncert_exercise_ref: Optional[str] = None


class ConceptCard(BaseModel):
    topic: str
    grade: int
    chapter_name: str
    chapter_number: int
    difficulty: Difficulty
    definition: str
    latex_equations: list[str]
    worked_examples: list[WorkedExample]
    common_errors: list[str]
    prerequisites: list[str]
    real_world_hooks: list[str]
    visual_metaphor: str


class HookSpec(BaseModel):
    hook_type: HookType
    opening_line: str
    visual_action: str
    knowledge_gap_question: str
    analogy: str
    india_context: str = ""


class Scene(BaseModel):
    scene_number: int
    title: str
    duration_seconds: int
    narration: str
    animation_description: str
    manim_hint: str = ""
    reveals_formula: bool = False
    video_prompt: str = ""
    chunk_prompts: list[str] = Field(
        default_factory=list,
        description="One simple action per Wan chunk (~5s); same visual world",
    )
    math_overlay: Optional[str] = None
    shot_type: ShotType = ShotType.JOURNEY


class StoryArc(BaseModel):
    topic: str
    grade: int
    total_duration_seconds: int
    hook_summary: str
    scenes: list[Scene]
    quiz_question: str
    quiz_correct_answer: str
    quiz_distractors: list[str] = Field(default_factory=list)
    # Unified micro-story: one Wan clip for the whole narrative (not 4 separate gens)
    unified_story: bool = False
    scenario_title: str = ""
    scenario_summary: str = ""
    master_video_prompt: str = ""
    visual_setting: str = ""  # e.g. city_car | cricket_pitch — one world for all beats


class ManimCode(BaseModel):
    scene_class_name: str = "VideoScene"
    code: str
    manim_version: str = "0.19.0"
    estimated_render_seconds: int = 60
    dependencies: list[str] = Field(default_factory=list)


class NarrationScript(BaseModel):
    full_script: str
    scenes: list[dict]
    language: str = "en"
    tone: str = "curious_friend"


class TeachQuizResult(BaseModel):
    topic: str
    quiz_question: str
    correct_answer: str
    llm_answer: str
    passed: bool
    score: float
    failure_reason: Optional[str] = None
    replan_suggestion: Optional[str] = None


class PipelineRun(BaseModel):
    run_id: str
    concept_card: ConceptCard
    hook_spec: Optional[HookSpec] = None
    story_arc: Optional[StoryArc] = None
    manim_code: Optional[ManimCode] = None
    narration_script: Optional[NarrationScript] = None
    quiz_result: Optional[TeachQuizResult] = None
    output_video_path: Optional[str] = None
    attempt_number: int = 1
    status: str = "pending"
    errors: list[str] = Field(default_factory=list)

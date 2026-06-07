"""Full pipeline orchestrator with quality gates and retries."""

import uuid
from pathlib import Path

from agents.hook_agent import generate_hook
from agents.narrator import generate_narration
from agents.planner import generate_story_arc
from eval.teach_quiz import evaluate_comprehension
from render.composer import compose_final_short
from render.scene_renderer import render_all_scenes
from render.tts import generate_voiceover
from utils.logger import get_logger
from utils.schemas import (
    ConceptCard,
    HookSpec,
    ManimCode,
    PipelineRun,
    StoryArc,
    TeachQuizResult,
)

import config

logger = get_logger(__name__)

BAD_HOOK_WORDS = [
    "today",
    "we will learn",
    "this concept",
    "in this video",
    "introduction",
    "topic is",
    "we are going to",
]


def _save_artifact(content: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _generate_hook_with_gate(concept_card: ConceptCard, max_attempts: int = 2) -> HookSpec:
    hook = None
    for i in range(max_attempts):
        hook = generate_hook(concept_card)
        opening_lower = hook.opening_line.lower()
        if any(bad in opening_lower for bad in BAD_HOOK_WORDS):
            logger.warning(f"[Hook Gate] Failed attempt {i+1}: '{hook.opening_line[:50]}'")
            continue
        return hook
    logger.warning("[Hook Gate] Using last hook despite gate failure")
    return hook


def _generate_arc_with_gate(
    concept_card: ConceptCard,
    hook: HookSpec,
    run: PipelineRun,
) -> StoryArc:
    extra = ""
    if run.quiz_result and not run.quiz_result.passed:
        extra = (
            f"Previous attempt failed. Reason: {run.quiz_result.failure_reason}. "
            f"Fix: {run.quiz_result.replan_suggestion}"
        )
    return generate_story_arc(concept_card, hook, extra_context=extra)


def _story_arc_to_manim_proxy(arc: StoryArc) -> ManimCode:
    """Build a text proxy of visuals for TeachQuiz when not using Manim renderer."""
    lines = ["# Visual proxy from StoryArc"]
    for s in arc.scenes:
        lines.append(f"# Scene {s.scene_number}: {s.animation_description}")
        if s.math_overlay:
            lines.append(f"# Math: {s.math_overlay}")
    return ManimCode(code="\n".join(lines))


def run_pipeline(
    concept_card: ConceptCard,
    output_dir: str = "outputs/",
    language: str = "en",
    max_full_retries: int = 2,
    concept_index: int | None = None,
) -> PipelineRun:
    """Runs full concept -> video pipeline."""
    run = PipelineRun(
        run_id=str(uuid.uuid4()),
        concept_card=concept_card,
    )
    run.status = "generating"

    slug = concept_card.topic[:30].replace(" ", "_").replace("/", "_")
    if concept_index is not None:
        slug = f"{concept_index:02d}_{slug}"
    folder_prefix = "physics" if config.SUBJECT == "physics" else f"class{concept_card.grade}"
    out = Path(output_dir) / f"{folder_prefix}_{slug}"
    out.mkdir(parents=True, exist_ok=True)

    for full_attempt in range(1, max_full_retries + 1):
        run.attempt_number = full_attempt
        logger.info(f"[Orchestrator] Attempt {full_attempt} for '{concept_card.topic}'")

        try:
            hook = _generate_hook_with_gate(concept_card)
            run.hook_spec = hook
            _save_artifact(hook.model_dump_json(indent=2), out / "hook_spec.json")

            arc = _generate_arc_with_gate(concept_card, hook, run)
            run.story_arc = arc
            _save_artifact(arc.model_dump_json(indent=2), out / "story_arc.json")

            script = generate_narration(arc, language=language)
            run.narration_script = script
            _save_artifact(script.model_dump_json(indent=2), out / "narration.json")

            run.status = "rendering"
            scenes_out = out / "scene_clips"
            clip_paths = render_all_scenes(arc, scenes_out)

            if config.VIDEO_BACKEND == "storyboard_only":
                logger.info("[Orchestrator] storyboard_only — skipping video compose")
                run.status = "done"
                run.output_video_path = str(scenes_out)
                manim_proxy = _story_arc_to_manim_proxy(arc)
                run.manim_code = manim_proxy
                run.quiz_result = evaluate_comprehension(
                    arc, manim_proxy, narration_text=script.full_script
                )
                return run

            audio_path = generate_voiceover(
                script.full_script,
                out / "voiceover.mp3",
                language=language,
            )

            final_video = compose_final_short(
                arc=arc,
                scene_clip_paths=clip_paths,
                narration=script,
                audio_path=audio_path,
                output_dir=out / "compose",
            )
            run.output_video_path = final_video
            run.manim_code = _story_arc_to_manim_proxy(arc)

            quiz_result = evaluate_comprehension(
                arc, run.manim_code, narration_text=script.full_script
            )
            run.quiz_result = quiz_result

            if quiz_result.passed:
                run.status = "done"
                logger.info(f"[Orchestrator] SUCCESS score={quiz_result.score:.2f}")
                return run

            logger.warning(f"[Orchestrator] TeachQuiz failed: {quiz_result.failure_reason}")
            run.errors.append(f"Attempt {full_attempt} quiz: {quiz_result.failure_reason}")

        except Exception as e:
            logger.error(f"[Orchestrator] Error: {e}")
            run.errors.append(str(e))
            if full_attempt == max_full_retries:
                run.status = "failed"
                return run

    run.status = "failed"
    return run

# Orchestrator, TTS, TeachQuiz, and CLI

## Overview

This document covers the final pieces that wire everything together:
- `orchestrator.py` — coordinates all agents, handles errors, manages retries
- `tts.py` — converts the narration script to a voiceover audio file
- `teach_quiz.py` — evaluates video quality by testing comprehension
- `main.py` — the CLI entry point

---

## orchestrator.py

**File location:** `agents/orchestrator.py`

### What It Does

The orchestrator runs the full pipeline for one `ConceptCard` and produces one video. It:
1. Calls each agent in sequence
2. Validates outputs at each step (quality gates)
3. Retries the full generation if TeachQuiz fails
4. Logs everything to the `PipelineRun` state object

### Quality Gates

| Gate | What is checked | Action on fail |
|---|---|---|
| Hook gate | `opening_line` must not contain the word "today", "learn", "concept", or "equation" | Retry hook agent (up to 2x) |
| Scene 1 gate | `reveals_formula` must be False for scene 1 | Retry planner |
| Duration gate | Total video 45–100 seconds | Retry planner with stricter constraints |
| Manim syntax gate | Code must pass Python `compile()` | Retry illustrator with error feedback |
| Render gate | Manim must exit with code 0 | Retry illustrator with stderr as feedback |
| TeachQuiz gate | Score must be ≥ 0.7 | Retry full pipeline from planner |

### Implementation

```python
# agents/orchestrator.py

import uuid
import json
from pathlib import Path
from utils.schemas import (
    ConceptCard, HookSpec, StoryArc, ManimCode,
    NarrationScript, TeachQuizResult, PipelineRun
)
from agents.hook_agent import generate_hook
from agents.planner import generate_story_arc
from agents.narrator import generate_narration
from agents.illustrator import generate_manim_code, save_manim_code
from render.renderer import render_video
from render.tts import generate_voiceover
from render.subtitle_sync import create_subtitled_video
from eval.teach_quiz import evaluate_comprehension
from utils.logger import get_logger

logger = get_logger(__name__)


BAD_HOOK_WORDS = ["today", "we will learn", "this concept", "in this video", 
                   "introduction", "topic is", "we are going to"]


def run_pipeline(
    concept_card: ConceptCard,
    output_dir: str = "outputs/",
    language: str = "en",
    max_full_retries: int = 2
) -> PipelineRun:
    """
    Runs the full pipeline for one concept card.
    
    Returns a PipelineRun with status="done" on success, status="failed" on failure.
    """
    run = PipelineRun(
        run_id=str(uuid.uuid4()),
        concept_card=concept_card
    )
    run.status = "generating"
    
    output_dir = Path(output_dir) / f"class{concept_card.grade}_{concept_card.topic[:30].replace(' ', '_')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for full_attempt in range(1, max_full_retries + 1):
        run.attempt_number = full_attempt
        logger.info(f"[Orchestrator] Full attempt {full_attempt} for '{concept_card.topic}'")
        
        try:
            # ── STEP 1: Hook Agent ─────────────────────────────────────
            logger.info("[Orchestrator] Running Hook Agent...")
            hook = _generate_hook_with_gate(concept_card)
            run.hook_spec = hook
            _save_artifact(hook.model_dump_json(indent=2), output_dir / "hook_spec.json")
            
            # ── STEP 2: Planner ────────────────────────────────────────
            logger.info("[Orchestrator] Running Planner...")
            arc = _generate_arc_with_gate(concept_card, hook, run)
            run.story_arc = arc
            _save_artifact(arc.model_dump_json(indent=2), output_dir / "story_arc.json")
            
            # ── STEP 3: Illustrator + Narrator (both use arc) ──────────
            logger.info("[Orchestrator] Running Illustrator...")
            manim_code = generate_manim_code(arc, concept_card, hook, max_retries=3)
            run.manim_code = manim_code
            
            code_path = save_manim_code(manim_code, output_dir / "video_scene.py")
            
            logger.info("[Orchestrator] Running Narrator...")
            script = generate_narration(arc, language=language)
            run.narration_script = script
            _save_artifact(script.model_dump_json(indent=2), output_dir / "narration.json")
            
            # ── STEP 4: Render ─────────────────────────────────────────
            run.status = "rendering"
            logger.info("[Orchestrator] Rendering Manim...")
            
            raw_video = render_video(
                code_path,
                quality="medium_quality",
                output_dir=str(output_dir / "raw/")
            )
            
            # ── STEP 5: TTS Voiceover ──────────────────────────────────
            logger.info("[Orchestrator] Generating voiceover...")
            audio_path = generate_voiceover(
                script=script.full_script,
                output_path=str(output_dir / "voiceover.mp3"),
                language=language
            )
            
            # ── STEP 6: Combine video + audio + subtitles ──────────────
            final_video = create_subtitled_video(
                video_path=raw_video,
                audio_path=audio_path,
                narration_script=script,
                output_path=str(output_dir / "final_video.mp4")
            )
            run.output_video_path = final_video
            
            # ── STEP 7: TeachQuiz Evaluation ───────────────────────────
            logger.info("[Orchestrator] Running TeachQuiz...")
            quiz_result = evaluate_comprehension(arc, manim_code)
            run.quiz_result = quiz_result
            
            if quiz_result.passed:
                run.status = "done"
                logger.info(f"[Orchestrator] SUCCESS — score: {quiz_result.score:.2f}")
                return run
            else:
                logger.warning(
                    f"[Orchestrator] TeachQuiz FAILED (score: {quiz_result.score:.2f}): "
                    f"{quiz_result.failure_reason}"
                )
                run.errors.append(f"Attempt {full_attempt} quiz failed: {quiz_result.failure_reason}")
                # Loop continues — full retry with quiz failure as context
        
        except Exception as e:
            logger.error(f"[Orchestrator] Error on attempt {full_attempt}: {e}")
            run.errors.append(str(e))
            if full_attempt == max_full_retries:
                run.status = "failed"
                return run
    
    run.status = "failed"
    return run


def _generate_hook_with_gate(concept_card: ConceptCard, max_attempts: int = 2) -> HookSpec:
    """Generates hook and validates it passes the quality gate."""
    for i in range(max_attempts):
        hook = generate_hook(concept_card)
        opening_lower = hook.opening_line.lower()
        
        if any(bad in opening_lower for bad in BAD_HOOK_WORDS):
            logger.warning(f"[Hook Gate] Hook failed quality gate (attempt {i+1}): '{hook.opening_line[:60]}'")
            continue
        
        return hook
    
    # Return the last attempt even if it fails the gate
    logger.warning("[Hook Gate] All hook attempts failed quality gate — using last attempt")
    return hook


def _generate_arc_with_gate(
    concept_card: ConceptCard,
    hook: HookSpec,
    run: PipelineRun
) -> StoryArc:
    """Generates story arc with quiz failure context if this is a retry."""
    
    # On retries, add quiz failure as context to the planner
    quiz_context = ""
    if run.quiz_result and not run.quiz_result.passed:
        quiz_context = (
            f"Previous attempt failed comprehension test. "
            f"Reason: {run.quiz_result.failure_reason}. "
            f"Suggestion: {run.quiz_result.replan_suggestion}"
        )
    
    return generate_story_arc(concept_card, hook, extra_context=quiz_context)


def _save_artifact(content: str, path: Path):
    """Saves a JSON artifact to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
```

---

## tts.py — Text-to-Speech

**File location:** `render/tts.py`

```python
# render/tts.py

import os
from pathlib import Path


def generate_voiceover(
    script: str,
    output_path: str,
    language: str = "en",
    voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs "Rachel" voice
) -> str:
    """
    Converts narration script text to an MP3 audio file.
    
    Uses ElevenLabs if ELEVENLABS_API_KEY is set in environment.
    Falls back to gTTS (Google TTS, free) if not.
    
    Args:
        script: the full narration text
        output_path: where to save the MP3
        language: "en" or "hi"
        voice_id: ElevenLabs voice ID (only used with ElevenLabs)
        
    Returns:
        path to the generated MP3 file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Clean the script — remove animation cues like "[ANIMATE: ...]" and "(pause Xs)"
    clean_script = _clean_script_for_tts(script)
    
    if os.environ.get("ELEVENLABS_API_KEY"):
        return _generate_elevenlabs(clean_script, str(output_path), voice_id)
    else:
        print("[TTS] No ElevenLabs key found, falling back to gTTS")
        return _generate_gtts(clean_script, str(output_path), language)


def _clean_script_for_tts(script: str) -> str:
    """Removes Manim cue markers from the narration script."""
    import re
    # Remove [ANIMATE: ...] blocks
    script = re.sub(r'\[ANIMATE:[^\]]+\]', '', script)
    # Remove (pause Xs) markers
    script = re.sub(r'\(pause \d+(\.\d+)?s\)', '', script)
    # Clean up extra whitespace
    script = ' '.join(script.split())
    return script


def _generate_elevenlabs(script: str, output_path: str, voice_id: str) -> str:
    """Uses ElevenLabs API for high-quality TTS."""
    from elevenlabs import generate, save, set_api_key
    
    set_api_key(os.environ["ELEVENLABS_API_KEY"])
    
    audio = generate(
        text=script,
        voice=voice_id,
        model="eleven_multilingual_v2"
    )
    save(audio, output_path)
    print(f"[TTS] ElevenLabs audio saved to {output_path}")
    return output_path


def _generate_gtts(script: str, output_path: str, language: str) -> str:
    """Uses Google TTS (free) as fallback."""
    from gtts import gTTS
    
    lang_map = {"en": "en", "hi": "hi", "en-hi": "hi"}
    tts = gTTS(text=script, lang=lang_map.get(language, "en"), slow=False)
    tts.save(output_path)
    print(f"[TTS] gTTS audio saved to {output_path}")
    return output_path
```

---

## teach_quiz.py — Comprehension Evaluator

**File location:** `eval/teach_quiz.py`

### How It Works

TeachQuiz simulates a student watching the video by giving the LLM:
- The Manim code (as a proxy for what the student "saw")
- The narration script (as a proxy for what the student "heard")

Then it asks the quiz question from the `StoryArc`. If the LLM answers correctly, the video likely teaches the concept. If not, it generates a suggestion for the planner.

```python
# eval/teach_quiz.py

import json
from utils.schemas import StoryArc, ManimCode, TeachQuizResult
from utils.llm_client import call_llm


QUIZ_SYSTEM_PROMPT = """You are a Class 8 student who just watched an educational math video.
You understood everything shown in the video — you are not an expert, just an attentive student.
Answer the question based ONLY on what was explained in the video.
Return ONLY valid JSON."""


def evaluate_comprehension(arc: StoryArc, manim_code: ManimCode) -> TeachQuizResult:
    """
    Evaluates whether the video would teach the concept effectively.
    
    Simulates a student watching the video and answering a comprehension question.
    
    Args:
        arc: the story arc (contains quiz question)
        manim_code: the Manim code (proxy for what student saw)
        
    Returns:
        TeachQuizResult with pass/fail and suggestions for improvement
    """
    prompt = f"""You just watched this math video about: {arc.topic}

WHAT YOU SAW (the animation code describes the visuals):
{manim_code.code[:3000]}  

WHAT YOU HEARD (narration script):
{arc.scenes[-1].narration if arc.scenes else ""}

Now answer this question:
{arc.quiz_question}

Options:
A) {arc.quiz_correct_answer}
B) {arc.quiz_distractors[0] if arc.quiz_distractors else "wrong answer 1"}
C) {arc.quiz_distractors[1] if len(arc.quiz_distractors) > 1 else "wrong answer 2"}
D) {arc.quiz_distractors[2] if len(arc.quiz_distractors) > 2 else "wrong answer 3"}

Return JSON:
{{
  "chosen_answer": "A/B/C/D",
  "chosen_text": "the text of the answer you chose",
  "reasoning": "why you chose this based on the video",
  "what_was_unclear": "what part of the video did not explain this well (if you got it wrong)"
}}"""
    
    response = call_llm(
        system_prompt=QUIZ_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=500,
        temperature=0.0     # deterministic for evaluation
    )
    
    answer_data = json.loads(response)
    
    # Check if correct
    is_correct = answer_data["chosen_text"].strip().lower() == arc.quiz_correct_answer.strip().lower()
    score = 1.0 if is_correct else 0.0
    
    # Generate replan suggestion if wrong
    replan_suggestion = None
    if not is_correct:
        replan_suggestion = (
            f"The video failed to clearly explain the answer to: '{arc.quiz_question}'. "
            f"Student chose '{answer_data['chosen_text']}' instead of '{arc.quiz_correct_answer}'. "
            f"Unclear area: {answer_data.get('what_was_unclear', 'unknown')}. "
            f"Add a dedicated scene that directly demonstrates the answer to this question."
        )
    
    result = TeachQuizResult(
        topic=arc.topic,
        quiz_question=arc.quiz_question,
        correct_answer=arc.quiz_correct_answer,
        llm_answer=answer_data["chosen_text"],
        passed=is_correct,
        score=score,
        failure_reason=answer_data.get("what_was_unclear") if not is_correct else None,
        replan_suggestion=replan_suggestion
    )
    
    status = "PASS" if is_correct else "FAIL"
    print(f"[TeachQuiz] {status} — Student answered: '{answer_data['chosen_text']}'")
    return result
```

---

## main.py — CLI Entry Point

**File location:** `main.py`

```python
# main.py

import argparse
import json
import sys
from pathlib import Path
from agents.pdf_parser import parse_ncert_pdf
from agents.segmenter import segment_chapter, save_concept_cards
from agents.orchestrator import run_pipeline
from utils.schemas import ConceptCard
from utils.logger import get_logger

logger = get_logger(__name__)


def cmd_parse(args):
    """Parse a NCERT PDF into concept cards."""
    print(f"Parsing {args.pdf}...")
    text = parse_ncert_pdf(args.pdf, parsed_dir="data/parsed/")
    
    cards = segment_chapter(
        chapter_text=text,
        grade=args.grade,
        chapter_name=args.chapter,
        chapter_number=args.chapter_num
    )
    
    output_dir = f"data/concept_cards/class{args.grade}_ch{args.chapter_num}/"
    paths = save_concept_cards(cards, output_dir)
    
    print(f"\nSaved {len(paths)} concept cards to {output_dir}")
    print("Topics found:")
    for card in cards:
        print(f"  [{card.difficulty}] {card.topic}")


def cmd_generate(args):
    """Generate videos from concept cards."""
    cards_dir = Path(args.cards)
    card_files = list(cards_dir.glob("*.json"))
    
    if not card_files:
        print(f"No concept card JSON files found in {cards_dir}")
        sys.exit(1)
    
    print(f"Found {len(card_files)} concept cards. Generating videos...")
    
    for card_file in card_files:
        print(f"\n{'='*60}")
        print(f"Processing: {card_file.name}")
        print('='*60)
        
        with open(card_file, encoding="utf-8") as f:
            card = ConceptCard.model_validate_json(f.read())
        
        run = run_pipeline(
            concept_card=card,
            output_dir=args.output,
            language=args.language
        )
        
        if run.status == "done":
            print(f"Video: {run.output_video_path}")
            print(f"Quiz: {'PASS' if run.quiz_result.passed else 'FAIL'}")
        else:
            print(f"FAILED after {run.attempt_number} attempts")
            print(f"Errors: {run.errors}")


def cmd_run(args):
    """Full pipeline: parse PDF then generate videos."""
    # First parse
    args_parse = argparse.Namespace(
        pdf=args.pdf, grade=args.grade,
        chapter=args.chapter, chapter_num=args.chapter_num
    )
    cmd_parse(args_parse)
    
    # Then generate
    cards_dir = f"data/concept_cards/class{args.grade}_ch{args.chapter_num}/"
    args_gen = argparse.Namespace(cards=cards_dir, output=args.output, language=args.language)
    cmd_generate(args_gen)


def main():
    parser = argparse.ArgumentParser(description="NCERT Math Video Generator")
    subparsers = parser.add_subparsers(dest="command")
    
    # parse command
    p = subparsers.add_parser("parse", help="Parse NCERT PDF into concept cards")
    p.add_argument("--pdf", required=True, help="Path to NCERT PDF")
    p.add_argument("--grade", type=int, required=True, help="Class number (6-12)")
    p.add_argument("--chapter", required=True, help="Chapter name")
    p.add_argument("--chapter-num", type=int, default=1, dest="chapter_num")
    
    # generate command
    g = subparsers.add_parser("generate", help="Generate videos from concept cards")
    g.add_argument("--cards", required=True, help="Directory with concept card JSON files")
    g.add_argument("--output", default="outputs/", help="Output directory for videos")
    g.add_argument("--language", default="en", choices=["en", "hi", "en-hi"])
    
    # run command (full pipeline)
    r = subparsers.add_parser("run", help="Full pipeline: parse + generate")
    r.add_argument("--pdf", required=True)
    r.add_argument("--grade", type=int, required=True)
    r.add_argument("--chapter", required=True)
    r.add_argument("--chapter-num", type=int, default=1, dest="chapter_num")
    r.add_argument("--output", default="outputs/")
    r.add_argument("--language", default="en", choices=["en", "hi", "en-hi"])
    
    args = parser.parse_args()
    
    if args.command == "parse":
        cmd_parse(args)
    elif args.command == "generate":
        cmd_generate(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

---

## requirements.txt

```txt
# Core
anthropic>=0.25.0
pydantic>=2.0
python-dotenv>=1.0

# PDF parsing
PyMuPDF>=1.23.0
pdfplumber>=0.10.0
nougat-ocr>=0.1.17

# Animation
manim>=0.18.0

# TTS
gtts>=2.5.0
elevenlabs>=1.0.0   # optional, requires API key

# Video processing
ffmpeg-python>=0.2.0

# Math verification
sympy>=1.12

# Utilities
numpy>=1.24.0
Pillow>=10.0.0
tqdm>=4.65.0
```

---

## logger.py

**File location:** `utils/logger.py`

```python
# utils/logger.py

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
```

---

## config.py

**File location:** `config.py`

```python
# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

# Model settings
LLM_MODEL = "claude-sonnet-4-20250514"
LLM_MAX_TOKENS_DEFAULT = 4000

# Video settings
VIDEO_MAX_DURATION_SECONDS = 90
VIDEO_MIN_DURATION_SECONDS = 45
TEACHQUIZ_PASS_THRESHOLD = 0.7

# Manim settings
MANIM_QUALITY = "medium_quality"   # change to "high_quality" for production

# Paths
DATA_DIR = "data/"
OUTPUT_DIR = "outputs/"
PARSED_DIR = "data/parsed/"
CARDS_DIR = "data/concept_cards/"
```

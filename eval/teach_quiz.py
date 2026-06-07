"""TeachQuiz comprehension evaluation."""

import json

from utils.llm_client import _extract_json, call_llm
from utils.schemas import ManimCode, StoryArc, TeachQuizResult

import config

QUIZ_SYSTEM_PROMPT = """You are a Class 8 student who just watched an educational math video.
Answer based ONLY on what was explained. Return ONLY valid JSON."""


def evaluate_comprehension(
    arc: StoryArc,
    manim_code: ManimCode | None = None,
    narration_text: str = "",
) -> TeachQuizResult:
    """
    Simulates a student answering the quiz from video content proxies.
    """
    visual_proxy = ""
    if manim_code:
        visual_proxy = manim_code.code[:3000]
    else:
        visual_proxy = "\n".join(
            f"Scene {s.scene_number}: {s.animation_description}; overlay: {s.math_overlay}"
            for s in arc.scenes
        )

    heard = narration_text or " ".join(s.narration for s in arc.scenes)

    distractors = arc.quiz_distractors or ["wrong 1", "wrong 2", "wrong 3"]
    while len(distractors) < 3:
        distractors.append(f"wrong {len(distractors)+1}")

    prompt = f"""You watched this math video about: {arc.topic}

WHAT YOU SAW:
{visual_proxy}

WHAT YOU HEARD:
{heard}

Question: {arc.quiz_question}

Options:
A) {arc.quiz_correct_answer}
B) {distractors[0]}
C) {distractors[1]}
D) {distractors[2]}

Return JSON:
{{
  "chosen_answer": "A/B/C/D",
  "chosen_text": "exact text of chosen option",
  "reasoning": "why",
  "what_was_unclear": "if wrong"
}}"""

    response = call_llm(
        system_prompt=QUIZ_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=500,
        temperature=0.25,
    )
    response = _extract_json(response)
    answer_data = json.loads(response)

    chosen = answer_data.get("chosen_text", "").strip().lower()
    correct = arc.quiz_correct_answer.strip().lower()
    is_correct = chosen == correct or answer_data.get("chosen_answer", "").upper() == "A"

    score = 1.0 if is_correct else 0.0
    passed = score >= config.TEACHQUIZ_PASS_THRESHOLD

    replan_suggestion = None
    failure_reason = None
    if not passed:
        failure_reason = answer_data.get("what_was_unclear", "Quiz answer incorrect")
        replan_suggestion = (
            f"Video failed to explain: '{arc.quiz_question}'. "
            f"Student chose '{answer_data.get('chosen_text')}' not '{arc.quiz_correct_answer}'. "
            f"Add a scene demonstrating the correct answer."
        )

    result = TeachQuizResult(
        topic=arc.topic,
        quiz_question=arc.quiz_question,
        correct_answer=arc.quiz_correct_answer,
        llm_answer=answer_data.get("chosen_text", ""),
        passed=passed,
        score=score,
        failure_reason=failure_reason,
        replan_suggestion=replan_suggestion,
    )
    status = "PASS" if passed else "FAIL"
    print(f"[TeachQuiz] {status} — score={score:.2f}, answer='{result.llm_answer}'")
    return result

"""Creative hook agent — runs before planner."""

import json

import config
from agents.subject_config import hook_system, normalize_subject
from utils.json_parse import parse_model_json
from utils.json_prompts import HOOK_SPEC_EXAMPLE, json_instruction
from utils.llm_client import _extract_json, call_llm
from utils.schemas import ConceptCard, HookSpec


HOOK_AGENT_SYSTEM_PROMPT = """You are the Creative Hook Agent for an educational mathematics video pipeline.
Your ONLY job is to design the most compelling opening 15 seconds for a math video.
You are NOT explaining the concept — you are creating the moment that makes a student WANT to learn it.
You are writing for Indian students aged 12–18. Use Indian contexts, names, sports, and situations.
You must return ONLY valid JSON matching the HookSpec schema."""

HOOK_STRATEGIES_GUIDE = """
Hook strategies: CURIOSITY_GAP, WTF_FACT, REAL_WORLD_ANCHOR, MYSTERY_OPENER, CULTURAL_ANALOGY.
Use journey-style language like "let's shrink and go inside..." for 3D cartoon videos.
"""


def generate_hook(concept_card: ConceptCard, subject: str | None = None) -> HookSpec:
    subject = normalize_subject(subject or getattr(config, "SUBJECT", "math"))
    example_block = json_instruction(HOOK_SPEC_EXAMPLE, "HookSpec")
    prompt = f"""Generate a creative hook for this NCERT concept:

TOPIC: {concept_card.topic}
CLASS: {concept_card.grade}
DEFINITION (reference only): {concept_card.definition}
REAL-WORLD CONTEXTS: {json.dumps(concept_card.real_world_hooks, indent=2)}
VISUAL METAPHOR: {concept_card.visual_metaphor}

{HOOK_STRATEGIES_GUIDE}

{example_block}

Rules:
- opening_line: max 40 words, ends with question or cliffhanger
- visual_action: what 3D cartoon shows in seconds 0-5 (NOT plain text)
- knowledge_gap_question: ONE question the video answers
- analogy: ONE metaphor for the whole video"""

    response = call_llm(
        system_prompt=hook_system(subject),
        user_prompt=prompt,
        max_tokens=1500,
        temperature=config.LLM_TEMPERATURE_HOOK,
    )
    response = _extract_json(response)
    hook = parse_model_json(response, HookSpec)
    print(f"[Hook Agent] '{hook.hook_type}' hook: '{hook.opening_line[:60]}...'")
    return hook

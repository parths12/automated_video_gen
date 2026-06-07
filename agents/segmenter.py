"""Chapter text -> ConceptCard segmentation."""

import json
import re
from pathlib import Path

from pydantic import ValidationError

import config
from agents.subject_config import normalize_subject, segmenter_system, segmenter_user_intro
from utils.llm_client import _extract_json, call_llm
from utils.schemas import ConceptCard


def build_segmenter_prompt(
    chapter_text: str,
    grade: int,
    chapter_name: str,
    chapter_number: int,
    concept_card_schema: str,
    subject: str = "math",
) -> str:
    return f"""{segmenter_user_intro(subject, grade, chapter_name, chapter_number)}

CHAPTER TEXT:
{chapter_text[:12000]}

Extract ALL distinct concepts from this chapter as an array of concept cards.
Each card covers ONE atomic concept (not a whole chapter, not a single formula — one teachable idea).

For each concept card, populate every field in this JSON schema:
{concept_card_schema}

Rules for each field:
- topic: short name, max 8 words
- definition: plain English, max 2 sentences
- latex_equations: key formulas in LaTeX (use empty list only if none)
- worked_examples: AT LEAST 1 example with step-by-step solutions
- common_errors: SPECIFIC mistakes
- prerequisites: topic names from earlier chapters
- real_world_hooks: EXACTLY 3 India-specific entries
- visual_metaphor: ONE spatial analogy

Return a JSON array. First element is most foundational."""


def segment_chapter(
    chapter_text: str,
    grade: int,
    chapter_name: str,
    chapter_number: int,
    subject: str = "math",
) -> list[ConceptCard]:
    """Segments chapter text into validated ConceptCard objects."""
    subject = normalize_subject(subject)
    schema_str = json.dumps(ConceptCard.model_json_schema(), indent=2)
    prompt = build_segmenter_prompt(
        chapter_text, grade, chapter_name, chapter_number, schema_str, subject=subject
    )

    print(f"[Segmenter/{subject}] Calling LLM for {chapter_name}...")
    raw_response = call_llm(
        system_prompt=segmenter_system(subject),
        user_prompt=prompt,
        max_tokens=8000,
        temperature=config.LLM_TEMPERATURE_SEGMENTER,
    )

    raw_response = _extract_json(raw_response)
    try:
        cards_data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}\nRaw: {raw_response[:500]}") from e

    if not isinstance(cards_data, list):
        raise ValueError(f"Expected JSON array, got {type(cards_data)}")

    concept_cards = []
    for i, card_data in enumerate(cards_data):
        try:
            card_data["grade"] = grade
            card_data["chapter_name"] = chapter_name
            card_data["chapter_number"] = chapter_number
            card = ConceptCard.model_validate(card_data)
            concept_cards.append(card)
            print(f"[Segmenter] Card {i+1}: '{card.topic}'")
        except ValidationError as e:
            print(f"[Segmenter] Warning: Card {i+1} skipped: {e}")

    print(f"[Segmenter] Extracted {len(concept_cards)} concept cards")
    return concept_cards


def save_concept_cards(cards: list[ConceptCard], output_dir: str | Path) -> list[str]:
    """Saves each ConceptCard as a separate JSON file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = []
    for card in cards:
        safe_name = re.sub(r"[^\w]+", "_", card.topic.lower())[:50]
        filename = f"class{card.grade}_{safe_name}.json"
        filepath = output_dir / filename
        filepath.write_text(card.model_dump_json(indent=2), encoding="utf-8")
        saved_paths.append(str(filepath))
    return saved_paths

# PDF Parser + Segmenter — Phase 1

## Purpose

This phase converts a raw NCERT PDF file into an array of structured `ConceptCard` JSON objects. It has two steps:

1. **`pdf_parser.py`** — Extract clean text from the PDF, handling math equations specially
2. **`segmenter.py`** — Use an LLM to split the extracted text into atomic concept cards

---

## Step 1: pdf_parser.py

**File location:** `agents/pdf_parser.py`

### The Challenge with NCERT PDFs

NCERT PDFs come in two formats:
- **Typeset PDFs** (newer editions) — text is selectable, equations are embedded as MathML or images
- **Scanned PDFs** (older editions) — everything is an image, needs OCR

For both formats, the best tool is **Nougat** (Meta's academic paper OCR model). It outputs clean Markdown where equations become `$...$` (inline) or `$$...$$` (block) LaTeX.

### Install Nougat

```bash
pip install nougat-ocr
# Nougat downloads its model (~1.4GB) on first run
# Requires: torch, so install torch first if on a new machine
pip install torch torchvision
```

### Implementation

```python
# agents/pdf_parser.py

import subprocess
import os
from pathlib import Path


def parse_pdf_with_nougat(pdf_path: str, output_dir: str) -> str:
    """
    Runs Nougat OCR on a PDF and returns the path to the output markdown file.
    
    Nougat converts the PDF page by page and outputs a single .mmd (modified markdown) file.
    Math equations are wrapped in $...$ or $$...$$ LaTeX.
    
    Args:
        pdf_path: absolute path to the NCERT PDF
        output_dir: directory where Nougat saves its output
        
    Returns:
        path to the output .mmd markdown file
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Nougat CLI command
    # --no-skipping: don't skip pages that look like tables/figures
    # --recompute: force recompute even if cached output exists
    result = subprocess.run(
        [
            "nougat",
            str(pdf_path),
            "--out", str(output_dir),
            "--no-skipping",
        ],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"Nougat failed:\n{result.stderr}")

    # Nougat outputs a file with same name as PDF but .mmd extension
    output_file = output_dir / pdf_path.with_suffix(".mmd").name
    
    if not output_file.exists():
        raise FileNotFoundError(f"Nougat did not produce output at {output_file}")
    
    return str(output_file)


def load_parsed_text(mmd_path: str) -> str:
    """
    Reads the Nougat output markdown file and returns clean text.
    Does light cleanup of common Nougat artefacts.
    """
    with open(mmd_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    # Remove Nougat confidence warnings (lines starting with [MISSING_PAGE...])
    lines = text.split("\n")
    lines = [l for l in lines if not l.startswith("[MISSING_PAGE")]
    lines = [l for l in lines if not l.startswith("[IGNORED]")]
    
    return "\n".join(lines)


def parse_ncert_pdf(pdf_path: str, parsed_dir: str = "data/parsed/") -> str:
    """
    Full pipeline: PDF → clean markdown text.
    
    Args:
        pdf_path: path to NCERT PDF
        parsed_dir: where to save Nougat output
        
    Returns:
        clean markdown string ready for the segmenter
    """
    print(f"[PDF Parser] Running Nougat on {pdf_path}...")
    mmd_path = parse_pdf_with_nougat(pdf_path, parsed_dir)
    
    print(f"[PDF Parser] Nougat output saved to {mmd_path}")
    text = load_parsed_text(mmd_path)
    
    print(f"[PDF Parser] Extracted {len(text)} characters")
    return text
```

### Fallback: PyMuPDF for text-only PDFs

If Nougat is too slow (it can take 2–5 mins per chapter), use this fast fallback for chapters that are mostly text with few equations:

```python
# Add to pdf_parser.py

import fitz  # PyMuPDF

def parse_pdf_fast(pdf_path: str) -> str:
    """
    Fast text extraction using PyMuPDF. 
    Does NOT handle math equations well — use only for text-heavy sections.
    """
    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n\n"
    doc.close()
    return full_text
```

---

## Step 2: segmenter.py

**File location:** `agents/segmenter.py`

### What It Does

Takes the markdown text from a chapter and uses an LLM to extract structured `ConceptCard` objects. One chapter typically produces 5–10 concept cards.

### Key Principle

The LLM prompt must be very explicit about what makes a good `real_world_hooks` entry and `visual_metaphor`. These are the hardest fields to get right and the most important for the downstream creative agents.

### Implementation

```python
# agents/segmenter.py

import json
import os
from utils.schemas import ConceptCard, WorkedExample, Difficulty
from utils.llm_client import call_llm
from pydantic import ValidationError


SEGMENTER_SYSTEM_PROMPT = """You are an expert NCERT mathematics curriculum analyst.
Your job is to extract structured concept cards from chapter text.
You must return ONLY valid JSON — no preamble, no explanation, no markdown code fences.
Every real_world_hooks entry must be specific to India (IPL cricket, train journeys, 
street vendor pricing, auto-rickshaw fares, EMI calculations, agriculture yields, 
Diwali sale discounts, etc.). Never use American or European examples.
The visual_metaphor must be ONE concrete spatial analogy that a 13-year-old can picture."""


def build_segmenter_prompt(
    chapter_text: str,
    grade: int,
    chapter_name: str,
    chapter_number: int,
    concept_card_schema: str
) -> str:
    return f"""You are parsing NCERT Class {grade} Mathematics, Chapter {chapter_number}: "{chapter_name}".

CHAPTER TEXT:
{chapter_text}

Extract ALL distinct concepts from this chapter as an array of concept cards.
Each card covers ONE atomic concept (not a whole chapter, not a single formula — one teachable idea).

For each concept card, populate every field in this JSON schema:
{concept_card_schema}

Rules for each field:
- topic: short name, max 8 words. Start with a verb or noun, not "Understanding" or "Introduction to"
- definition: plain English, avoid jargon, max 2 sentences  
- latex_equations: include ALL key equations. Write raw LaTeX, e.g. "ax + b = c"
- worked_examples: include AT LEAST 2 examples with full step-by-step solutions
- common_errors: list SPECIFIC mistakes, not vague ones. Bad: "calculation mistakes". 
  Good: "Adding 3 to left side but forgetting to add 3 to right side"
- prerequisites: list topic names from EARLIER chapters/grades that are needed
- real_world_hooks: EXACTLY 3 entries. Must be India-specific. Must be situations where  
  this exact concept would help solve a real problem.
  Format: one sentence describing the situation + one sentence explaining what the student would calculate.
  Example: "A street vendor buys mangoes at ₹120 per dozen and sells at ₹15 each. 
  Students calculate profit per mango using linear equations."
- visual_metaphor: ONE spatial analogy. Must be concrete and visualisable by a 13-year-old.
  Example for linear equations: "A balance scale where both pans must always be equal — 
  whatever you add or remove from one side, you must do the same to the other."
  Example for fractions: "A pizza cut into equal slices — 3/8 means 3 slices out of 8 total."

Return a JSON array. First element is the most foundational concept in the chapter.
Last element is the most advanced. Order matters."""


def segment_chapter(
    chapter_text: str,
    grade: int,
    chapter_name: str,
    chapter_number: int
) -> list[ConceptCard]:
    """
    Segments a chapter's extracted text into ConceptCard objects.
    
    Args:
        chapter_text: full markdown text from Nougat
        grade: NCERT class number (6–12)
        chapter_name: e.g. "Linear Equations in One Variable"
        chapter_number: e.g. 2
        
    Returns:
        list of validated ConceptCard objects, ordered foundational → advanced
    """
    # Get JSON schema string to embed in prompt
    schema_str = json.dumps(ConceptCard.model_json_schema(), indent=2)
    
    prompt = build_segmenter_prompt(
        chapter_text=chapter_text,
        grade=grade,
        chapter_name=chapter_name,
        chapter_number=chapter_number,
        concept_card_schema=schema_str
    )
    
    print(f"[Segmenter] Calling LLM for {chapter_name}...")
    raw_response = call_llm(
        system_prompt=SEGMENTER_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=8000,       # chapters need a lot of tokens
        temperature=0.1        # low temperature for structured extraction
    )
    
    # Parse and validate
    try:
        cards_data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}\nRaw response:\n{raw_response[:500]}")
    
    if not isinstance(cards_data, list):
        raise ValueError(f"Expected JSON array, got {type(cards_data)}")
    
    concept_cards = []
    for i, card_data in enumerate(cards_data):
        try:
            # Add chapter metadata that the LLM might not fill in
            card_data["grade"] = grade
            card_data["chapter_name"] = chapter_name
            card_data["chapter_number"] = chapter_number
            
            card = ConceptCard.model_validate(card_data)
            concept_cards.append(card)
            print(f"[Segmenter] Card {i+1}: '{card.topic}'")
        except ValidationError as e:
            print(f"[Segmenter] Warning: Card {i+1} failed validation, skipping: {e}")
            continue
    
    print(f"[Segmenter] Extracted {len(concept_cards)} concept cards from {chapter_name}")
    return concept_cards


def save_concept_cards(cards: list[ConceptCard], output_dir: str) -> list[str]:
    """
    Saves each ConceptCard as a separate JSON file.
    Returns list of saved file paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    saved_paths = []
    for card in cards:
        # Create filename from topic name
        safe_name = card.topic.lower().replace(" ", "_").replace("/", "_")[:50]
        filename = f"class{card.grade}_{safe_name}.json"
        filepath = output_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(card.model_dump_json(indent=2))
        
        saved_paths.append(str(filepath))
    
    return saved_paths
```

---

## Step 3: llm_client.py

**File location:** `utils/llm_client.py`

This is a thin wrapper used by all agents. Build it once, use everywhere.

```python
# utils/llm_client.py

import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4000,
    temperature: float = 0.3,
    model: str = "claude-sonnet-4-20250514"
) -> str:
    """
    Single LLM call. Returns raw text response.
    All agents call this function — never call the Anthropic client directly.
    
    Raises:
        anthropic.APIError on API failures
    """
    client = get_client()
    
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )
    
    return message.content[0].text
```

---

## Testing Phase 1

Run this to verify the parser + segmenter work before building anything else:

```python
# test_phase1.py — run this to test PDF parsing and segmentation

from agents.pdf_parser import parse_ncert_pdf
from agents.segmenter import segment_chapter, save_concept_cards

# Parse a chapter
text = parse_ncert_pdf(
    pdf_path="data/pdfs/class8_ch2.pdf",
    parsed_dir="data/parsed/"
)
print(f"Extracted {len(text)} characters")
print("First 500 chars:\n", text[:500])

# Segment into concept cards
cards = segment_chapter(
    chapter_text=text,
    grade=8,
    chapter_name="Linear Equations in One Variable",
    chapter_number=2
)

# Save
paths = save_concept_cards(cards, "data/concept_cards/class8_ch2/")
print(f"\nSaved {len(paths)} concept cards:")
for p in paths:
    print(f"  {p}")

# Print first card to inspect
print("\nFirst concept card:")
print(cards[0].model_dump_json(indent=2))
```

### What Good Output Looks Like

A well-formed concept card for "Solving linear equations with variables on both sides" should look like:

```json
{
  "topic": "Solving equations with variables on both sides",
  "grade": 8,
  "chapter_name": "Linear Equations in One Variable",
  "chapter_number": 2,
  "difficulty": "core",
  "definition": "When a variable appears on both sides of an equation, we collect all variable terms on one side and all constant terms on the other before solving.",
  "latex_equations": ["3x + 5 = x + 13", "3x - x = 13 - 5", "2x = 8", "x = 4"],
  "worked_examples": [
    {
      "problem_statement": "Solve: 3x + 5 = x + 13",
      "solution_steps": [
        "Move x from right side to left: 3x - x + 5 = 13",
        "Simplify: 2x + 5 = 13",
        "Subtract 5 from both sides: 2x = 8",
        "Divide both sides by 2: x = 4"
      ],
      "answer": "x = 4",
      "ncert_exercise_ref": "Exercise 2.3, Q1"
    }
  ],
  "common_errors": [
    "Moving x from right to left but not changing its sign (writing 3x + x instead of 3x - x)",
    "Only subtracting 5 from one side instead of both sides"
  ],
  "prerequisites": ["Solving simple linear equations", "Transposition method"],
  "real_world_hooks": [
    "Riya and Priya both start saving money. Riya has ₹200 and saves ₹50/week. Priya has ₹80 and saves ₹80/week. Students find the week when both have the same amount.",
    "A train from Mumbai travels at 60 km/h. Another train from Pune (150 km away) travels at 40 km/h toward Mumbai. Students find when and where they meet.",
    "In an IPL match, Virat scores 3 times what Rohit scores, minus 10. Together they score 90 runs. Students find each player's score."
  ],
  "visual_metaphor": "A balance scale where both pans must always stay level — moving any number from one pan to the other means you must move the exact same number from the other pan to keep the scale balanced."
}
```

If your output looks like this, Phase 1 is working. Move to the hook agent.

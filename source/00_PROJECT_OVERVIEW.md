# NCERT Math Video Generation Pipeline — Project Overview

## What This Project Does

This project is an AI-powered pipeline that takes NCERT Class 6–12 Mathematics PDF textbooks as input and automatically generates short-form educational videos (60–90 seconds, optimised for YouTube Shorts / Instagram Reels format) for each concept.

The videos are designed to feel like 3Blue1Brown-style animated math explanations — not slideshows, not text narration, but genuine visual storytelling where the animation *is* the explanation.

---

## Why This Architecture

Most automated education video tools fail because they start from the formula and animate it. This pipeline starts from a **creative hook** — a curiosity gap, a real-world Indian context, a counterintuitive fact — and only then introduces the math. This is the novel research contribution of this project.

The pipeline has three major phases:

1. **PDF Parsing Phase** — Extract and structure knowledge from NCERT PDFs into `ConceptCard` JSON objects
2. **Creative Generation Phase** — Multi-agent system that generates hook, story arc, Manim animation code, and narration script
3. **Rendering Phase** — Execute Manim code, synthesise voice, sync subtitles, export video

---

## Project Directory Structure

```
ncert_video_gen/
│
├── data/
│   ├── pdfs/                    # Raw NCERT PDF files go here
│   ├── parsed/                  # Nougat OCR output (markdown files)
│   └── concept_cards/           # Structured JSON concept cards (one per topic)
│
├── agents/
│   ├── pdf_parser.py            # PDF → clean markdown text
│   ├── segmenter.py             # Markdown → ConceptCard JSON array
│   ├── hook_agent.py            # ConceptCard → HookSpec (the creative layer)
│   ├── planner.py               # HookSpec + ConceptCard → StoryArc JSON
│   ├── illustrator.py           # StoryArc → Manim Python code
│   ├── narrator.py              # StoryArc → narration script
│   └── orchestrator.py          # Runs all agents, quality gates, retry logic
│
├── eval/
│   └── teach_quiz.py            # Post-generation comprehension probe
│
├── render/
│   ├── renderer.py              # Executes Manim code → MP4
│   ├── tts.py                   # Text-to-speech voiceover (ElevenLabs / gTTS)
│   └── subtitle_sync.py         # Aligns subtitles to audio timestamps
│
├── utils/
│   ├── llm_client.py            # Wrapper around Anthropic / OpenAI API
│   ├── schemas.py               # Pydantic models for all JSON structures
│   └── logger.py                # Structured logging
│
├── config.py                    # All configurable constants and API keys
├── main.py                      # CLI entry point — run end-to-end pipeline
├── requirements.txt
└── README.md
```

---

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| PDF parsing | PyMuPDF + pdfplumber | Text extraction with layout awareness |
| Math OCR | Nougat (Meta, open-source) | Converts math PDFs to LaTeX markdown |
| LLM | Claude claude-sonnet-4-20250514 via Anthropic API | All agent reasoning |
| Animation | Manim Community Edition (ManimCE) | Programmatic math animations |
| TTS | ElevenLabs API (or gTTS for free tier) | Natural voiceover |
| Data validation | Pydantic v2 | Schema enforcement for all JSON outputs |
| Config | python-dotenv | API key management |

---

## Data Flow Summary

```
NCERT PDF
    ↓ [pdf_parser.py — Nougat OCR]
Clean Markdown text
    ↓ [segmenter.py — LLM call]
ConceptCard[] JSON
    ↓ [hook_agent.py — LLM call]         ← THE NOVEL PIECE
HookSpec JSON
    ↓ [planner.py — LLM call]
StoryArc JSON
    ↓ [illustrator.py — LLM call]   [narrator.py — LLM call]
Manim Python code                    Narration script
    ↓ [orchestrator — quality gate]
Validated + corrected code
    ↓ [renderer.py — Manim execution]
Raw MP4 + audio
    ↓ [tts.py + subtitle_sync.py]
Final video (Shorts format)
    ↓ [teach_quiz.py — LLM eval]
Quality score + re-plan trigger
```

---

## Key Design Decisions

### 1. Concept cards are the foundation
Every agent downstream depends on the quality of the ConceptCard. The card includes not just the math content but also `real_world_hooks`, `visual_metaphor`, and `common_errors`. These fields are what make the downstream creative agents work well.

### 2. The hook agent runs before the planner
This is intentional and unconventional. Most pipelines plan first, then style. Here, the creative hook constrains the plan — the story arc must *resolve* the knowledge gap that the hook opens. This forces narrative coherence.

### 3. Animate the analogy, not the formula
The illustrator agent is explicitly instructed: the first scene must show the analogy/metaphor, not the equation. The formula appears only after the intuition is established visually. This is the 3Blue1Brown principle.

### 4. Retry loops exist at two levels
- **Illustrator level**: if Manim code throws a syntax/runtime error, the illustrator agent auto-fixes with error context (up to 3 retries)
- **Orchestrator level**: if TeachQuiz score is below threshold, the full generation re-runs with the quiz failure as additional context for the planner

---

## Environment Variables Required

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=your_key_here
ELEVENLABS_API_KEY=your_key_here        # optional, gTTS works without this
MATHPIX_APP_ID=your_id_here             # optional, only if using Mathpix instead of Nougat
MATHPIX_APP_KEY=your_key_here           # optional
```

---

## How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Parse a single NCERT chapter PDF
python main.py parse --pdf data/pdfs/class8_ch2.pdf --grade 8 --chapter "Linear Equations in One Variable"

# 3. Generate videos from all parsed concept cards in a chapter
python main.py generate --cards data/concept_cards/class8_ch2/ --output outputs/

# 4. Full pipeline (parse + generate)
python main.py run --pdf data/pdfs/class8_ch2.pdf --grade 8 --chapter "Linear Equations in One Variable" --output outputs/
```

---

## Build Order (Important)

Do NOT try to build all of this at once. Follow this sequence:

1. `schemas.py` — define all data models first, everything else references them
2. `pdf_parser.py` + `segmenter.py` — get clean concept cards out of one chapter
3. `hook_agent.py` — build and test the creative hook in isolation
4. `illustrator.py` — get one working Manim animation
5. `planner.py` + `narrator.py`
6. `orchestrator.py` + retry logic
7. `renderer.py` + `tts.py` + `subtitle_sync.py`
8. `teach_quiz.py` + feedback loop
9. `main.py` CLI wiring

---

## First Target Chapter

Start with: **NCERT Class 8, Chapter 2 — Linear Equations in One Variable**

Why this chapter:
- Self-contained (minimal prerequisites)
- Has excellent real-world hook potential (balance scale analogy, EMI problems, age puzzles)
- 6–8 distinct concepts (enough to test the pipeline, not so many it's overwhelming)
- Students commonly struggle with it (common errors are well-documented)

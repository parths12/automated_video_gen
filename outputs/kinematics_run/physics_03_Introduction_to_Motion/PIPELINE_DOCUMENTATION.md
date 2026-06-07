# NCERT Physics Video Pipeline — Technical Documentation

**Project:** AI-generated educational Shorts from NCERT Class 11 Physics (Kinematics)  
**Example run:** `physics_03_Introduction_to_Motion`  
**Command being run (video re-render only):**

```bash
export SUBJECT=physics VIDEO_BACKEND=local_video VISUAL_SETTING=city_car \
  WAN_HEIGHT=1280 WAN_WIDTH=704 WAN_STEPS=60

CUDA_VISIBLE_DEVICES=0 bash /mnt/data0/parth/ai_ed/ncert_fixed/scripts/rerender_scenes.sh \
  /mnt/data0/parth/ai_ed/ncert_fixed/outputs/kinematics_run/physics_03_Introduction_to_Motion
```

This document explains **what the system does**, **how data flows through it**, **what every file means**, and **what appears on disk at each stage**.

---

## 1. High-Level Goal

The pipeline turns a single NCERT physics concept (e.g. *Introduction to Motion*) into a **60–90 second vertical video Short** (9:16, 1080×1920) suitable for platforms like YouTube Shorts or Instagram Reels.

The video has four narrative beats:

1. **Hook** — grab attention with a real-world question  
2. **Metaphor** — show motion visually (here: a white car on an Indian city road)  
3. **Reveal** — connect the visual to the physics equation  
4. **Recap** — close with a call to action  

Unlike a slideshow, the system generates **AI-animated 3D cartoon footage** using diffusion video models (Wan 2.1), with **frame-to-frame continuity** so the same car and road persist across the whole story.

---

## 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INPUTS (one-time setup)                           │
│  NCERT PDF  →  Concept Cards  →  Hook + Story Plan  →  Narration Script    │
│  (data/pdfs)   (data/concept_cards)   (LLM agents)      (LLM + TTS)        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     VIDEO GENERATION (GPU-heavy, slow)                      │
│  Visual Director  →  Wan T2V/I2V chunks  →  Hybrid teaching overlay        │
│  (chunk prompts)     (scene_clips/)         (equation strip on bottom)      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COMPOSE (ffmpeg, fast)                              │
│  Concat scenes  →  Mux voiceover  →  Burn subtitles  →  final_short.mp4    │
│  (compose/)                                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Two ways to run the pipeline:**

| Script | When to use | LLM? | TTS? | Video? | Compose? |
|--------|-------------|------|------|--------|----------|
| `scripts/generate_kinematics.sh` | First full generation from PDF/cards | Yes | Yes | Yes | Yes |
| `scripts/rerender_scenes.sh` | Re-render video only (your current command) | Visual director only | No (reuses `voiceover.mp3`) | Yes | Yes |

Current command **skips** hook planning, story planning, and TTS. It reloads the existing `story_arc.json`, refreshes chunk prompts via the visual director, re-generates all scene clips, and re-composes the final video.

---

## 3. Repository Structure (Key Directories)

```
/mnt/data0/parth/ai_ed/ncert_fixed/
│
├── main.py                    # CLI entry: parse | generate | run
├── config.py                  # All environment-variable defaults
│
├── agents/                    # LLM-based creative agents
│   ├── orchestrator.py        # Full pipeline coordinator
│   ├── hook_agent.py          # Opening hook from concept card
│   ├── unified_planner.py     # 4-beat story arc (physics micro-story)
│   ├── visual_director.py     # One visual world + per-chunk Wan prompts
│   ├── narrator.py            # Spoken script per scene
│   ├── pdf_parser.py          # PDF → plain text
│   └── segmenter.py           # Chapter text → concept card JSON files
│
├── render/                    # Video generation and assembly
│   ├── unified_story.py       # Renders all 4 beats sequentially
│   ├── local_hf.py            # Wan T2V / I2V chunk generation
│   ├── hybrid_beat.py         # Animation + equation strip overlay
│   ├── equation_panel.py      # Renders LaTeX teaching strip as PNG
│   ├── composer.py            # Final concat, audio mux, subtitles
│   ├── subtitle_sync.py       # SRT generation and burn-in
│   └── tts.py                 # Text-to-speech → voiceover.mp3
│
├── utils/
│   ├── schemas.py             # Pydantic models (StoryArc, Scene, etc.)
│   ├── local_inference.py     # Loads Qwen LLM, SDXL, Wan T2V, Wan I2V
│   ├── video_io.py            # extract_last_frame (continuity seeds)
│   └── video_frames.py        # Frame-count snapping for Wan
│
├── scripts/
│   ├── generate_kinematics.sh # Full pipeline: PDF → video
│   └── rerender_scenes.sh     # Video-only re-render (your command)
│
├── data/
│   ├── pdfs/                  # Source NCERT PDFs
│   ├── parsed/                # Extracted text from PDFs
│   └── concept_cards/
│       └── physics_ch2/       # One JSON per kinematics concept
│
└── outputs/
    └── kinematics_run/        # Generated videos per concept
        └── physics_03_Introduction_to_Motion/   ← this run
```

---

## 4. Input Data (Before Any Video Is Generated)

### 4.1 Concept Card — `data/concept_cards/physics_ch2/class11_introduction_to_motion.json`

Structured knowledge extracted from the NCERT chapter. Fields include:

| Field | Purpose |
|-------|---------|
| `topic` | "Introduction to Motion" |
| `definition` | Core NCERT definition |
| `latex_equations` | e.g. speed = distance/time |
| `worked_examples` | NCERT-style problems |
| `common_errors` | Typical student mistakes |
| `real_world_hooks` | India-relevant scenarios (traffic, flyover) |
| `visual_metaphor` | "A car starting from rest and gradually increasing its speed" |

This card is the **factual anchor** — the LLM must not invent physics beyond what is here.

### 4.2 Parsed Text — `data/parsed/`

Plain text extracted from `data/kinematics.pdf` by the PDF parser. Used only during the `parse` step to create concept cards.

---

## 5. Output Folder Structure — `physics_03_Introduction_to_Motion/`

After a **full** run (`generate_kinematics.sh`), the output directory looks like this:

```
physics_03_Introduction_to_Motion/
│
├── hook_spec.json              # Stage A: creative hook (LLM)
├── story_arc.json              # Stage B: 4-scene story plan (LLM + visual director)
├── narration.json              # Stage C: spoken script (LLM)
├── voiceover.mp3               # Stage C: TTS audio (gTTS or ElevenLabs)
│
├── scene_clips/                # Stage D: per-scene video generation
│   ├── scene_01/
│   ├── scene_02/
│   ├── scene_03/
│   └── scene_04/
│
└── compose/                    # Stage E: final assembly
    ├── scenes/
    ├── raw_concat.mp4
    ├── with_audio.mp4
    ├── subtitles.srt
    └── final_short.mp4         ← DELIVERABLE
```

During a **re-render** (your current command), only `story_arc.json` is updated (visual director refresh), then `scene_clips/` and `compose/` are regenerated. `hook_spec.json`, `narration.json`, and `voiceover.mp3` are reused as-is.

---

## 6. Pipeline Stages in Detail

### Stage A — Hook Generation (`hook_spec.json`)

**Agent:** `agents/hook_agent.py`  
**Model:** Qwen 2.5 7B (local LLM)  
**When:** Full generate only (skipped in rerender)

Creates an attention-grabbing opening tied to Indian context.

**Example content (this run):**

```json
{
  "hook_type": "real_world_anchor",
  "opening_line": "Have you ever seen a cricket player sprinting to catch a ball? Let's shrink and dive into the action!",
  "visual_action": "3D cartoon Arjun shrinks and enters a small, detailed cricket field...",
  "knowledge_gap_question": "How does the ball's movement relate to motion in physics?",
  "analogy": "Motion is like the ball's journey — it has speed, direction, and path",
  "india_context": "Arjun in a vibrant cricket ground, surrounded by cheering spectators"
}
```

Note: The **visual** for this run uses a **city car** metaphor (not cricket), chosen by the visual director from the concept card's `visual_metaphor` field. The hook narration still references cricket; the video shows the car story.

---

### Stage B — Story Arc (`story_arc.json`)

**Agents:** `unified_planner.py` → `visual_director.py`  
**When:** Full generate creates it; rerender **re-applies** visual director and overwrites this file

The story arc is the **master plan** for the entire Short. It defines:

| Top-level field | Meaning |
|-----------------|---------|
| `topic` | NCERT concept name |
| `total_duration_seconds` | Sum of all scene durations (45–100s) |
| `unified_story` | `true` = one continuous visual world across 4 beats |
| `visual_setting` | `city_car` or `cricket_pitch` — same location all scenes |
| `master_video_prompt` | Continuity anchor string for the whole video |
| `scenes` | Array of exactly 4 scene objects |
| `quiz_question` / `quiz_correct_answer` | Post-generation quality check (TeachQuiz) |

**Per-scene fields (`scenes[]`):**

| Field | Meaning |
|-------|---------|
| `scene_number` | 1–4 |
| `title` | Internal label (Hook journey, See the metaphor, The reveal, Recap) |
| `duration_seconds` | Target length of this beat |
| `narration` | What the narrator says during this beat |
| `video_prompt` | One-line summary for the video model |
| `chunk_prompts` | List of ~5-second action prompts (one per Wan generation pass) |
| `math_overlay` | LaTeX equation shown in hybrid teaching strip (null if none) |
| `reveals_formula` | Whether this beat introduces the formula |
| `shot_type` | `journey` \| `reveal` \| `recap` \| `establishing` |

**This run's scene breakdown:**

| Scene | Duration | Chunks | Narration theme | Equation strip? |
|-------|----------|--------|-----------------|-----------------|
| 1 — Hook journey | 18s | 4 | Traffic light, car starts moving | No |
| 2 — See the metaphor | 20s | 4 | Car accelerates on city road | Yes: speed = d/t |
| 3 — The reveal | 22s | 5 | Formula connection | Yes: speed = d/t |
| 4 — Recap | 15s | 3 | Call to action | No |
| **Total** | **75s** | **16 Wan passes** | | |

The `chunk_prompts` are deliberately simple and repetitive ("Same white car, same road...") so the diffusion model maintains visual consistency.

---

### Stage C — Narration (`narration.json` + `voiceover.mp3`)

**Agent:** `agents/narrator.py`  
**TTS:** `render/tts.py` (gTTS by default; ElevenLabs if API key set)  
**When:** Full generate only (rerender reuses existing files)

| File | Purpose |
|------|---------|
| `narration.json` | Structured script: `full_script` + per-scene `text` and `pause_before_seconds` |
| `voiceover.mp3` | Synthesized speech audio muxed into the final video |

The compose step aligns subtitles to scene durations from `story_arc.json`, not to word-level timestamps.

---

### Stage D — Scene Video Generation (`scene_clips/`)

**Modules:** `render/unified_story.py` → `render/local_hf.py` → `render/hybrid_beat.py`  
**When:** Both full generate and rerender (this is the slow GPU step)

This is the stage your command is currently running. It takes ~**8–10 hours** at `WAN_STEPS=60`, `WAN_HEIGHT=1280`, because each Wan pass takes ~35 minutes on a single GPU.

#### D.1 — How a scene is built

Each scene is longer than Wan can generate in one pass (~5 seconds max). The pipeline **splits** the scene into chunks:

```
Scene duration (e.g. 20s)
        │
        ▼
┌───────────────────────────────────────────────────┐
│  Chunk 0 (~5s)  │  Chunk 1 (~5s)  │  Chunk 2  │  Chunk 3  │
│  Wan T2V or I2V │  Wan I2V        │  Wan I2V  │  Wan I2V  │
│  from prompt    │  from last frame│  from last│  from last│
│                 │  of chunk 0     │  frame    │  frame    │
└───────────────────────────────────────────────────┘
        │
        ▼
   anim_raw.mp4  (all chunks concatenated)
        │
        ▼
   clip.mp4  (hybrid overlay if equation present)
        │
        ▼
   last_frame.png  (seeds Scene N+1, chunk 0)
```

**Models used:**

| Pass type | Model | When |
|-----------|-------|------|
| **T2V** (text → video) | `Wan-AI/Wan2.1-T2V-1.3B-Diffusers` | Scene 1, chunk 0 only (no prior frame) |
| **I2V** (image → video) | `Wan-AI/Wan2.1-I2V-14B-480P-Diffusers` | All subsequent chunks; Scene 2+ chunk 0 seeds from previous scene's `last_frame.png` |
| **Fallback** | `stabilityai/sdxl-turbo` (static image + Ken Burns) | Only if Wan generation fails |

**Cross-scene continuity:** With `WAN_USE_PREV_FRAME=1` (default for physics), the last frame of Scene 1's `clip.mp4` becomes the seed image for Scene 2's first chunk. This keeps the same car/road appearance across the whole video.

#### D.2 — Files inside `scene_clips/scene_XX/`

| File | Stage within scene | Description |
|------|-------------------|-------------|
| `t2v_chunk_NN.mp4` | During chunk N generation | Raw Wan diffusion output at 704×1264. **Deleted** after trimming to save disk space. |
| `t2v_chunk_NN_trim.mp4` | After chunk N postprocess | Scaled/padded to 1080×1920, trimmed to exact chunk duration, H.264 re-encoded. |
| `chunk_NN_last.png` | After chunk N trim | Last frame of trimmed chunk; used as I2V seed for chunk N+1. |
| `t2v_concat.txt` | Multi-chunk scenes | ffmpeg concat demuxer list (only when scene has >1 chunk). |
| `anim_raw.mp4` | After all chunks done | All `*_trim.mp4` files joined — pure animation, no equation overlay. |
| `strip_NN.png` | Hybrid overlay step | PNG teaching strip: LaTeX equation + concept caption (matplotlib). |
| `clip.mp4` | Scene complete | **Final per-scene deliverable.** Animation with equation strip overlaid at bottom (if `HYBRID_TEACHING=1` and scene has `math_overlay`). |
| `last_frame.png` | After clip.mp4 done | Last frame extracted from `clip.mp4`; seeds I2V for the **next scene's** first chunk. |

**Important:** You will **not** see `clip.mp4` for a scene until **all** its chunks finish. You will **not** see raw `t2v_chunk_NN.mp4` after trimming — those are intentionally removed.

#### D.3 — Hybrid teaching overlay

**Module:** `render/hybrid_beat.py`  
**Enabled when:** `HYBRID_TEACHING=1` (default for `SUBJECT=physics`)

For scenes with a `math_overlay` field (scenes 2 and 3 in this run), the pipeline:

1. Renders a bottom strip PNG with the LaTeX equation and a concept line  
2. Overlays it on `anim_raw.mp4` using ffmpeg  
3. Writes the result to `clip.mp4`

This keeps the animation full-screen while showing the formula at the bottom — a teaching-friendly layout for physics Shorts.

---

### Stage E — Final Composition (`compose/`)

**Module:** `render/composer.py`  
**When:** After all 4 scenes have `clip.mp4` (both full generate and rerender)

| Step | Output file | What happens |
|------|-------------|--------------|
| 1. Copy scenes | `compose/scenes/scene_NN_processed.mp4` | Each `clip.mp4` copied (math overlay skipped here because hybrid already applied it) |
| 2. Concatenate | `compose/concat_list.txt` | Manifest for ffmpeg |
| 2. Concatenate | `compose/raw_concat.mp4` | All 4 scenes joined with **1.2s crossfade** dissolve between beats |
| 3. Mux audio | `compose/with_audio.mp4` | `raw_concat.mp4` + existing `voiceover.mp3`, padded to 75s total |
| 4. Subtitles | `compose/subtitles.srt` | Timed captions from `narration.json` aligned to scene durations |
| 5. Burn-in | `compose/final_short.mp4` | Subtitles burned into video — **this is the final deliverable** |

**Note:** `compose/raw_concat.mp4` from a **previous** run may still exist on disk while a re-render is in progress. It is **not** updated until the current run completes all scenes and reaches the compose step.

---

## 7. Environment Variables (Your Command)

| Variable | Your value | Effect |
|----------|------------|--------|
| `SUBJECT` | `physics` | Enables hybrid teaching overlay; physics-specific LLM prompts |
| `VIDEO_BACKEND` | `local_video` | Use local Wan models (not Gemini/SANA cloud) |
| `VISUAL_SETTING` | `city_car` | Force city-car visual world (overrides concept card default) |
| `WAN_HEIGHT` | `1280` | Render height (must be divisible by 16); upscaled to 1920 in compose |
| `WAN_WIDTH` | `704` | Render width (9:16 aspect ratio) |
| `WAN_STEPS` | `60` | Diffusion denoising steps per chunk (~35 min/chunk on single GPU) |
| `WAN_USE_PREV_FRAME` | `1` (default) | I2V continuity: last frame of scene N → seed for scene N+1 |
| `WAN_MAX_FRAMES_PER_PASS` | `81` (default) | Max frames per Wan pass ≈ 5 seconds at 16 fps |
| `HYBRID_TEACHING` | `1` (default for physics) | Equation strip at bottom of animated scenes |
| `CUDA_VISIBLE_DEVICES` | `0` (in your terminal) | GPU device for all models |

**Speed vs quality tradeoffs:**

| Change | Speed impact | Quality impact |
|--------|-------------|----------------|
| `WAN_STEPS=30` | ~2× faster | Slightly softer detail |
| `WAN_HEIGHT=832 WAN_WIDTH=480` | ~2× faster | Lower resolution (still upscaled in compose) |
| Render one scene at a time | Same total time | Easier to inspect intermediate results |

---

## 8. AI Models Used

| Role | Model | Size | Purpose |
|------|-------|------|---------|
| Story planning | `Qwen/Qwen2.5-7B-Instruct` | 7B | Hook, story arc, narration, quiz |
| Video (first chunk) | `Wan-AI/Wan2.1-T2V-1.3B-Diffusers` | 1.3B | Text → 5s video clip |
| Video (continuity) | `Wan-AI/Wan2.1-I2V-14B-480P-Diffusers` | 14B | Image → 5s video clip (maintains appearance) |
| Image fallback | `stabilityai/sdxl-turbo` | — | Static keyframe if Wan fails |
| Speech | gTTS (Google TTS) | — | `voiceover.mp3` |
| Assembly | ffmpeg + libass | — | Concat, mux, subtitle burn-in |

Models are cached at `HF_HOME=/mnt/data0/parth/hf_models_cache`.

---

## 9. Timeline: What Exists on Disk at Each Point

This table shows what you should expect to see **during** a re-render of this run:

| Progress | Files present | Files NOT yet present |
|----------|---------------|----------------------|
| Script starts | `hook_spec.json`, `story_arc.json`, `narration.json`, `voiceover.mp4` | New scene clips |
| Scene 1, chunk 0 running | `scene_01/t2v_chunk_00_trim.mp4` (after chunk 0 finishes) | `scene_01/clip.mp4` |
| Scene 1 complete | `scene_01/clip.mp4`, `scene_01/last_frame.png`, trim files | Scene 2+ anything |
| Scene 2, chunk 2 running | `scene_02/t2v_chunk_00_trim.mp4` … `_01_trim.mp4`, `chunk_*_last.png` | `scene_02/clip.mp4`, `scene_03/`, `scene_04/` |
| All 4 scenes done | All `scene_XX/clip.mp4` and `last_frame.png` | Updated `compose/` |
| Compose complete | `compose/final_short.mp4` | — |

**Estimated total GPU time for this run:** ~16 Wan passes × ~35 min ≈ **9 hours** on a single GPU at current settings.

---

## 10. Quality Gate — TeachQuiz

**Module:** `eval/teach_quiz.py`  
**When:** End of full generate (not rerender)

After the video is composed, the LLM is asked the quiz question from `story_arc.json`. If it cannot answer correctly, the pipeline may replan and retry (configurable). This checks that the narrative actually teaches the concept.

---

## 11. How to Explain This to a Professor (Summary)

> We built an automated pipeline that converts NCERT Class 11 Physics concepts into short-form educational videos. Starting from a structured concept card extracted from the textbook, local LLMs (Qwen 7B) plan a four-beat narrative with India-relevant hooks and LaTeX equations. A visual director assigns consistent ~5-second animation prompts set in a single visual world (a white car on an Indian city road). Each prompt is rendered by Wan 2.1 diffusion video models running locally on GPU — text-to-video for the opening clip, then image-to-video for continuity so the same car persists across 16 generation passes totaling 75 seconds. Physics equations are composited as a teaching strip at the bottom of relevant scenes. Finally, ffmpeg concatenates the four scenes with crossfade transitions, muxes synthesized narration, and burns in subtitles. The deliverable is a 1080×1920 vertical MP4 ready for Short-form platforms. The re-render command regenerates only the video layers from an existing story plan, allowing iterative quality improvement without re-running the LLM planning steps.

---

## 12. Quick Reference — File Glossary

| File | One-line description |
|------|------------------------|
| `hook_spec.json` | Creative opening hook (question + analogy) |
| `story_arc.json` | Master plan: 4 scenes, durations, prompts, equations |
| `narration.json` | Spoken script with per-scene timing hints |
| `voiceover.mp3` | Synthesized narration audio |
| `scene_clips/scene_XX/t2v_chunk_NN_trim.mp4` | One ~5s trimmed Wan chunk |
| `scene_clips/scene_XX/chunk_NN_last.png` | Last frame of chunk N (I2V seed) |
| `scene_clips/scene_XX/anim_raw.mp4` | All chunks joined, no overlay |
| `scene_clips/scene_XX/strip_NN.png` | Equation teaching strip PNG |
| `scene_clips/scene_XX/clip.mp4` | Final scene video (animation + optional equation strip) |
| `scene_clips/scene_XX/last_frame.png` | Last frame of scene (cross-scene I2V seed) |
| `compose/raw_concat.mp4` | All 4 scenes crossfaded together |
| `compose/with_audio.mp4` | Video + voiceover muxed |
| `compose/subtitles.srt` | Timed subtitle file |
| `compose/final_short.mp4` | **Final deliverable** with burned-in subtitles |

---

*Generated for run `physics_03_Introduction_to_Motion` — NCERT Class 11, Chapter 2: Motion in a Straight Line.*

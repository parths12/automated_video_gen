# NCERT Math Shorts Video Pipeline

AI pipeline for NCERT Class 6–12 Mathematics → 60–90 second YouTube Shorts with 3D-cartoon narrative style and accurate math overlays.

## Quick start

```bash
conda activate /mnt/data0/parth/ai_ed/ai_ed
cd /mnt/data0/parth/ai_ed/ncert_video_gen
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set LLM_PROVIDER=anthropic + API key, or keep mock for offline test
```

### Parse Chapter 2 PDF

```bash
python main.py parse --pdf ../source/ncert_ch2_maths.pdf --grade 8 \
  --chapter "Linear Equations in One Variable" --chapter-num 2
```

### Generate pilot Short (concept 1 = balance scale / LHS-RHS)

```bash
python main.py generate --cards data/concept_cards/class8_ch2 \
  --output outputs/ --concept 1
```

### Full pipeline

```bash
python main.py run --pdf ../source/ncert_ch2_maths.pdf --grade 8 \
  --chapter "Linear Equations in One Variable" --chapter-num 2 --concept 1
```

## Configuration (`.env`)

| Variable | Options | Purpose |
|----------|---------|---------|
| `LLM_PROVIDER` | `gemini`, `anthropic`, `openai`, `mock` | Creative agents (hooks, story, narration) |
| `GEMINI_API_KEY` | From [Google AI Studio](https://aistudio.google.com/apikey) | Required for Gemini |
| `GEMINI_MODEL` | `gemini-2.5-flash` (recommended) | Text / JSON generation |
| `VIDEO_BACKEND` | See below | How scene clips are rendered |

### Video backends (creative quality)

| Backend | What you get | Requirements |
|---------|----------------|--------------|
| **`gemini_image`** | 3 AI illustrations per scene + zoom/crossfade motion | `gemini-2.5-flash-image` quota |
| **`gemini_veo`** | Real 8s animated video per scene (best) | Veo quota / billing ([docs](https://ai.google.dev/gemini-api/docs/video)) |
| `kenburns` | Placeholder text slides (dev only) | None |
| `mock` + `kenburns` | Fixed demo script | None |

**Recommended for creative Shorts:**

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
VIDEO_BACKEND=gemini_image
```

For full AI animation (like the stomata Short):

```env
VIDEO_BACKEND=gemini_veo
GEMINI_VEO_MODEL=veo-3.1-fast-generate-preview
```

### Quick creative generate

```bash
chmod +x scripts/generate_creative.sh
./scripts/generate_creative.sh 1   # concept index 1 = LHS/RHS balance scale
```

**Note:** Veo and Imagen may require paid quota on your Google account. If you see `429 RESOURCE_EXHAUSTED`, wait ~1 minute and retry, or enable billing in AI Studio.

---

## Fully local (no API keys) — Hugging Face

Your machine has **H200 GPUs** — you can run everything offline:

| Component | Default model | VRAM (approx) |
|-----------|---------------|---------------|
| LLM (hooks, story, quiz) | `Qwen/Qwen2.5-7B-Instruct` | ~15 GB |
| Scene images | `stabilityai/sdxl-turbo` | ~8 GB |
| Optional T2V | `Wan-AI/Wan2.1-T2V-1.3B-Diffusers` (not raw `Wan2.1-T2V-1.3B`) | ~24 GB+ |

### One-time setup (cache: `/mnt/data0/parth/hf_models_cache`)

```bash
conda activate /mnt/data0/parth/ai_ed/ai_ed
cd /mnt/data0/parth/ai_ed/ncert_video_gen

# 1) Hugging Face token (create at https://huggingface.co/settings/tokens)
export HF_TOKEN=hf_your_token_here
# Accept licenses on model pages: Qwen2.5-7B, SDXL-Turbo, Wan2.1 (if using video)

# 2) Download all weights (~15–40 GB depending on --with-video)
chmod +x scripts/download_models.sh scripts/generate_local.sh
export HF_HOME=/mnt/data0/parth/hf_models_cache
./scripts/download_models.sh              # LLM + image
./scripts/download_models.sh --with-video  # optional: + Wan T2V

# 3) Configure pipeline
cp .env.local.example .env
```

Or use Python directly:

```bash
export HF_TOKEN=hf_xxx
export HF_HOME=/mnt/data0/parth/hf_models_cache
python scripts/download_models.py --with-video
```

### Generate without any API key

```bash
./scripts/generate_local.sh 1
```

Uses GPU `cuda:1` by default (leave `cuda:0` free if another job is running). Override:

```bash
LOCAL_DEVICE=cuda:0 ./scripts/generate_local.sh 1
```

### Trade-offs vs Gemini/Veo

| | Local HF | Cloud API |
|--|----------|-----------|
| Cost | Free after download | Quota / billing |
| Creative LLM | Good (7B Qwen) | Excellent (Gemini) |
| Scene visuals | SDXL illustrations + motion | Veo = real animation |
| Setup | ~15 GB download | API key only |

## Architecture

1. **PDF** → `pdf_parser` → `segmenter` → `ConceptCard` JSON
2. **Creative** → `hook_agent` → `planner` → `narrator`
3. **Render** → `scene_renderer` → `math_overlay` → `composer` + `tts`
4. **QA** → `teach_quiz` (retry if score &lt; 0.7)

## Output

Videos saved to `outputs/class8_<topic>/final_short.mp4` (9:16, 1080×1920).

#!/usr/bin/env bash
# Generate NCERT Short using local Hugging Face models — tuned for H200 (141GB VRAM).
#
# Animated storytelling (default): 4 Wan2.1 clips — beat 1 T2V, beats 2–4 I2V from last frame.
#   Creative LLM stories (CONCEPT_ANCHOR_MODE=off). Optional FramePack for longer beats.
#   Fallback: SDXL keyframe motion. EDUCATIONAL_BEATS=1 only for text panels.
#
# Env overrides:
#   WAN_HEIGHT=832    rendered height  (default: 832 — fast 9:16, divisible by 16)
#   WAN_WIDTH=480     rendered width   (default: 480; upscaled to 1080x1920 in compose)
#   WAN_STEPS=50      inference steps  (raise to 75 for max quality)
#   WAN_GUIDANCE=6.0  guidance scale
#   WAN_PROGRESS=1    per-step logs + tqdm (set 0 to disable)
#   NCERT_OUTPUT_DIR  write videos here (default: <project>/outputs)
#   TMPDIR            temp for ffmpeg/imageio (default: /home/jovyan/tmp/ncert_pipeline)
#   LOCAL_DEVICE=cuda:0  which GPU (default: cuda:0 for H200)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export LLM_PROVIDER=local
export VIDEO_BACKEND="${VIDEO_BACKEND:-local_video}"
export CONCEPT_ANCHOR_MODE="${CONCEPT_ANCHOR_MODE:-off}"
export WAN_USE_PREV_FRAME="${WAN_USE_PREV_FRAME:-1}"
export LLM_TEMPERATURE_PLANNER="${LLM_TEMPERATURE_PLANNER:-0.75}"
export LOCAL_DEVICE="${LOCAL_DEVICE:-cuda:0}"
export HF_HOME="${HF_HOME:-/mnt/data0/parth/hf_models_cache}"
export HF_HUB_CACHE="$HF_HOME"

export TMPDIR="${TMPDIR:-/home/jovyan/tmp/ncert_pipeline}"
export NCERT_OUTPUT_DIR="${NCERT_OUTPUT_DIR:-$ROOT/outputs}"
mkdir -p "$TMPDIR" "$NCERT_OUTPUT_DIR/local_run"

# Wan video settings (480x832 default — ~3x faster than 832x1472)
export WAN_HEIGHT="${WAN_HEIGHT:-832}"
export WAN_WIDTH="${WAN_WIDTH:-480}"
export WAN_STEPS="${WAN_STEPS:-50}"
export WAN_GUIDANCE="${WAN_GUIDANCE:-6.0}"
export WAN_PROGRESS="${WAN_PROGRESS:-1}"
export VIDEO_UNIFIED_STORY="${VIDEO_UNIFIED_STORY:-1}"
export VIDEO_LOOP_UNIFIED="${VIDEO_LOOP_UNIFIED:-0}"
export SANA_STEPS="${SANA_STEPS:-40}"
export SANA_MAX_BEAT_SECONDS="${SANA_MAX_BEAT_SECONDS:-10}"
export EDUCATIONAL_BEATS="${EDUCATIONAL_BEATS:-0}"
export STORY_FALLBACK="${STORY_FALLBACK:-local_image}"
export VIDEO_LOOP_UNIFIED="${VIDEO_LOOP_UNIFIED:-0}"

PY="${PY:-/mnt/data0/parth/ai_ed/ai_ed/bin/python}"
CONCEPT="${1:-1}"

echo "H200 pipeline: LLM=$LLM_PROVIDER VIDEO=$VIDEO_BACKEND DEVICE=$LOCAL_DEVICE"
echo "  Output dir: $NCERT_OUTPUT_DIR/local_run/  TMPDIR=$TMPDIR"
echo "  Wan2.1 settings: ${WAN_WIDTH}x${WAN_HEIGHT}, ${WAN_STEPS} steps, guidance=${WAN_GUIDANCE}, progress=${WAN_PROGRESS}"
echo "  Animated story beats  edu_panels=$EDUCATIONAL_BEATS  fallback=$STORY_FALLBACK  Sana≤${SANA_MAX_BEAT_SECONDS}s/beat"
"$PY" main.py generate \
  --cards data/concept_cards/class8_ch2 \
  --output "$NCERT_OUTPUT_DIR/local_run/" \
  --concept "$CONCEPT"

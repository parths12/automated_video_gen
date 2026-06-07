#!/usr/bin/env bash
# Kinematics PDF → animated story Short (4 Wan2.1 beats, I2V continuity, NO loop)
#
# Usage:
#   LOCAL_DEVICE=cuda:1 bash scripts/generate_kinematics.sh        # parse PDF + generate concept 0
#   LOCAL_DEVICE=cuda:1 bash scripts/generate_kinematics.sh --skip-parse  # use existing cards
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export SUBJECT=physics
export LLM_PROVIDER=local
export VIDEO_BACKEND="${VIDEO_BACKEND:-local_video}"
export CONCEPT_ANCHOR_MODE="${CONCEPT_ANCHOR_MODE:-off}"
# Optional: VISUAL_SETTING=city_car or cricket_pitch (default: from concept card)
export VISUAL_SETTING="${VISUAL_SETTING:-city_car}"
export WAN_USE_PREV_FRAME="${WAN_USE_PREV_FRAME:-1}"
export LLM_TEMPERATURE_PLANNER="${LLM_TEMPERATURE_PLANNER:-0.75}"
export LOCAL_DEVICE="${LOCAL_DEVICE:-cuda:0}"
export HF_HOME="${HF_HOME:-/mnt/data0/parth/hf_models_cache}"
export HF_HUB_CACHE="$HF_HOME"

export TMPDIR="${TMPDIR:-/home/jovyan/tmp/ncert_pipeline}"
export NCERT_OUTPUT_DIR="${NCERT_OUTPUT_DIR:-$ROOT/outputs}"
mkdir -p "$TMPDIR" "$NCERT_OUTPUT_DIR/kinematics_run"

export VIDEO_UNIFIED_STORY=1
export VIDEO_LOOP_UNIFIED=0
export EDUCATIONAL_BEATS=0
export HYBRID_TEACHING=1
export STORY_FALLBACK=local_image
export CROSSFADE_SECONDS=1.2
# 720p-class 9:16 Wan render (better than 480x832); upscaled to 1080x1920 in compose
export WAN_HEIGHT="${WAN_HEIGHT:-1280}"
export WAN_WIDTH="${WAN_WIDTH:-704}"
export WAN_STEPS="${WAN_STEPS:-60}"
export WAN_MAX_FRAMES_PER_PASS="${WAN_MAX_FRAMES_PER_PASS:-81}"
export WAN_CRF="${WAN_CRF:-18}"
export SANA_MAX_BEAT_SECONDS="${SANA_MAX_BEAT_SECONDS:-12}"
# Optional: clone FramePack and set FRAMEPACK_ENABLED=1 FRAMEPACK_ROOT=/path/to/FramePack
export FRAMEPACK_ENABLED="${FRAMEPACK_ENABLED:-0}"

PY="${PY:-/mnt/data0/parth/ai_ed/ai_ed/bin/python}"
PDF="${PDF:-$ROOT/data/kinematics.pdf}"
CARDS_DIR="${CARDS_DIR:-$ROOT/data/concept_cards/physics_ch2}"
CONCEPT="${CONCEPT:-0}"
SKIP_PARSE=false

for arg in "$@"; do
  case "$arg" in
    --skip-parse) SKIP_PARSE=true ;;
    --concept=*) CONCEPT="${arg#*=}" ;;
  esac
done

echo "Kinematics pipeline: SUBJECT=$SUBJECT VIDEO=$VIDEO_BACKEND DEVICE=$LOCAL_DEVICE"
echo "  PDF=$PDF"
echo "  Output: $NCERT_OUTPUT_DIR/kinematics_run/"

if [[ "$SKIP_PARSE" != "true" ]]; then
  echo ""
  echo "=== Step 1: Parse kinematics.pdf into concept cards ==="
  "$PY" main.py parse \
    --pdf "$PDF" \
    --grade 11 \
    --chapter "Motion in a Straight Line" \
    --chapter-num 2 \
    --subject physics \
    --cards-dir "$CARDS_DIR"
fi

echo ""
echo "=== Step 2: Generate animated story video (no loop) ==="
"$PY" main.py generate \
  --cards "$CARDS_DIR" \
  --output "$NCERT_OUTPUT_DIR/kinematics_run/" \
  --concept "$CONCEPT" \
  --subject physics

echo ""
echo "Done. Check outputs under: $NCERT_OUTPUT_DIR/kinematics_run/"

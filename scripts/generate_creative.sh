#!/usr/bin/env bash
# Generate a creative NCERT Short with Gemini (real LLM + AI visuals).
set -euo pipefail

cd "$(dirname "$0")/.."
PY="${PY:-/mnt/data0/parth/ai_ed/ai_ed/bin/python}"

export LLM_PROVIDER="${LLM_PROVIDER:-gemini}"
export VIDEO_BACKEND="${VIDEO_BACKEND:-gemini_image}"

CONCEPT="${1:-1}"
echo "Using LLM_PROVIDER=$LLM_PROVIDER VIDEO_BACKEND=$VIDEO_BACKEND concept=$CONCEPT"

"$PY" main.py generate \
  --cards data/concept_cards/class8_ch2 \
  --output outputs/ \
  --concept "$CONCEPT"

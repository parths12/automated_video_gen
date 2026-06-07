#!/usr/bin/env bash
# One-time setup: install PyTorch + download Hugging Face models (no API keys).
set -euo pipefail

PY="${PY:-/mnt/data0/parth/ai_ed/ai_ed/bin/python}"
PIP="${PIP:-/mnt/data0/parth/ai_ed/ai_ed/bin/pip}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Installing local inference dependencies..."
"$PIP" install -r "$ROOT/requirements.txt" -q
"$PIP" install -r "$ROOT/requirements-local.txt" -q

export HF_HOME="${HF_HOME:-/mnt/data0/parth/hf_models_cache}"
export HF_HUB_CACHE="$HF_HOME"
export LOCAL_DEVICE="${LOCAL_DEVICE:-cuda:1}"
mkdir -p "$HF_HOME"

echo "Downloading models to $HF_HOME (requires HF_TOKEN for some repos)..."
"$PY" "$ROOT/scripts/download_models.py" --cache-dir "$HF_HOME" "$@"

echo "Done. Copy .env.local.example to .env and run: ./scripts/generate_local.sh 1"

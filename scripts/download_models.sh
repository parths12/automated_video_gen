#!/usr/bin/env bash
# Download all pipeline models to /mnt/data0/parth/hf_models_cache
#
# Before running:
#   export HF_TOKEN=hf_your_token_here
#   # Accept licenses on huggingface.co for Qwen, SDXL, Wan if prompted
#
set -euo pipefail

export HF_HOME="${HF_HOME:-/mnt/data0/parth/hf_models_cache}"
export HF_HUB_CACHE="$HF_HOME"
mkdir -p "$HF_HOME"

PY="${PY:-/mnt/data0/parth/ai_ed/ai_ed/bin/python}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Cache directory: $HF_HOME"
if [[ -z "${HF_TOKEN:-}" && -z "${HUGGING_FACE_HUB_TOKEN:-}" ]]; then
  echo "WARNING: HF_TOKEN not set. Public weights only."
fi

"$PY" "$ROOT/scripts/download_models.py" --cache-dir "$HF_HOME" "$@"
echo ""
echo "Add to your shell or .env:"
echo "  export HF_HOME=$HF_HOME"
echo "  export HF_TOKEN=<your token>"

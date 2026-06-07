#!/usr/bin/env bash
# Clone FramePack for longer next-frame video extension.
# https://github.com/lllyasviel/FramePack
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TARGET="${FRAMEPACK_ROOT:-$ROOT/../FramePack}"
if [[ -d "$TARGET/.git" ]]; then
  echo "FramePack already at $TARGET"
  exit 0
fi
git clone https://github.com/lllyasviel/FramePack.git "$TARGET"
echo "Cloned FramePack to $TARGET"
echo "Install deps: pip install -r $TARGET/requirements.txt"
echo "Then run with: export FRAMEPACK_ROOT=$TARGET FRAMEPACK_ENABLED=1"

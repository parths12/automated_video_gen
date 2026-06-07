#!/usr/bin/env bash
# Re-render scene clips + compose from existing story_arc.json (no LLM replan).
#
# GPU (pick one):
#   CUDA_VISIBLE_DEVICES=5 bash scripts/rerender_scenes.sh outputs/kinematics_run/physics_03_...
#   LOCAL_CUDA_DEVICE=5 bash scripts/rerender_scenes.sh ...   # sets CUDA_VISIBLE_DEVICES=5
#   LOCAL_DEVICE=cuda:0 CUDA_VISIBLE_DEVICES=5 bash ...     # explicit (cuda:0 = only visible GPU)
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OUT="${1:?pass output dir e.g. outputs/kinematics_run/physics_03_Introduction_to_Motion}"

export SUBJECT=physics
export VIDEO_BACKEND=local_video
export PYTHONPATH=.

# Map physical GPU → process sees one device as cuda:0
if [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
  export LOCAL_DEVICE=cuda:0
elif [[ -n "${LOCAL_CUDA_DEVICE:-}" ]]; then
  export CUDA_VISIBLE_DEVICES="${LOCAL_CUDA_DEVICE}"
  export LOCAL_DEVICE=cuda:0
fi
export LOCAL_DEVICE="${LOCAL_DEVICE:-cuda:0}"

export WAN_HEIGHT="${WAN_HEIGHT:-1280}"
export WAN_WIDTH="${WAN_WIDTH:-704}"
export WAN_STEPS="${WAN_STEPS:-60}"
export VISUAL_SETTING="${VISUAL_SETTING:-city_car}"

PY="${PY:-/mnt/data0/parth/ai_ed/ai_ed/bin/python}"

echo "Rerender: OUT=$OUT"
echo "  LOCAL_DEVICE=$LOCAL_DEVICE  CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-all}"

"$PY" - <<PY
from pathlib import Path
from agents.visual_director import apply_visual_director
from agents.narrator import _build_narration_from_arc
from render.unified_story import render_story_beats
from render.composer import compose_final_short
from utils.schemas import StoryArc, ConceptCard, NarrationScript

out = Path("$OUT")
arc = StoryArc.model_validate_json((out / "story_arc.json").read_text())
cards = list(Path("data/concept_cards/physics_ch2").glob("*.json"))
card = ConceptCard.model_validate_json(cards[0].read_text())
for c in cards:
    cc = ConceptCard.model_validate_json(c.read_text())
    if cc.topic == arc.topic:
        card = cc
        break
arc = apply_visual_director(arc, card)
(out / "story_arc.json").write_text(arc.model_dump_json(indent=2), encoding="utf-8")
clips = render_story_beats(arc, out / "scene_clips")
script = NarrationScript.model_validate_json((out / "narration.json").read_text()) if (out / "narration.json").exists() else _build_narration_from_arc(arc, "en")
final = compose_final_short(arc, clips, script, str(out / "voiceover.mp3"), out / "compose")
print("Done:", final)
PY

"""Central configuration for NCERT video pipeline."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _configure_gpu_env() -> None:
    """
    GPU selection (in priority order):
    1. CUDA_VISIBLE_DEVICES already set → use logical cuda:0 on that GPU only.
    2. Else LOCAL_CUDA_DEVICE=N → set CUDA_VISIBLE_DEVICES=N and cuda:0.
    3. Else LOCAL_DEVICE from env / .env (e.g. cuda:1).
    """
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    physical = os.environ.get("LOCAL_CUDA_DEVICE", "").strip()

    if visible:
        os.environ["LOCAL_DEVICE"] = "cuda:0"
        return
    if physical:
        os.environ["CUDA_VISIBLE_DEVICES"] = physical
        os.environ["LOCAL_DEVICE"] = "cuda:0"


_configure_gpu_env()

PROJECT_ROOT = Path(__file__).resolve().parent
AI_ED_ROOT = PROJECT_ROOT.parent

# Subject: math | physics (affects PDF segmentation, hooks, story templates)
SUBJECT = os.environ.get("SUBJECT", "math").lower()

# API
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "mock").lower()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_VEO_MODEL = os.environ.get("GEMINI_VEO_MODEL", "veo-2.0-generate-001")
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.0-flash-preview-image-generation")

# Video backends: storyboard_only | kenburns | local_image | local_video | local_sana | gemini_* | api
VIDEO_BACKEND = os.environ.get("VIDEO_BACKEND", "local_video").lower()
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")
VEO_POLL_SECONDS = int(os.environ.get("VEO_POLL_SECONDS", "15"))
VEO_MAX_DURATION = int(os.environ.get("VEO_MAX_DURATION", "8"))

# Local Hugging Face models (no API keys) — LLM_PROVIDER=local
LOCAL_LLM_MODEL = os.environ.get("LOCAL_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
LOCAL_IMAGE_MODEL = os.environ.get("LOCAL_IMAGE_MODEL", "stabilityai/sdxl-turbo")
# Must be the *-Diffusers* repo (has model_index.json). Raw Wan2.1-T2V-1.3B will 404.
LOCAL_VIDEO_MODEL = os.environ.get("LOCAL_VIDEO_MODEL", "Wan-AI/Wan2.1-T2V-1.3B-Diffusers")
# I2V for beats 2+ (last frame of previous scene). 480P fits 9:16 on H200.
WAN_I2V_MODEL = os.environ.get(
    "WAN_I2V_MODEL", "Wan-AI/Wan2.1-I2V-14B-480P-Diffusers"
)
WAN_USE_PREV_FRAME = os.environ.get("WAN_USE_PREV_FRAME", "1").lower() in ("1", "true", "yes")
WAN_I2V_SECTION_SECONDS = float(os.environ.get("WAN_I2V_SECTION_SECONDS", "8"))
# Wan quality (1.3B degrades above ~81 frames — chunk or continue clips for longer beats)
WAN_MAX_FRAMES_PER_PASS = int(os.environ.get("WAN_MAX_FRAMES_PER_PASS", "81"))
WAN_STEPS = int(os.environ.get("WAN_STEPS", "60"))
WAN_GUIDANCE = float(os.environ.get("WAN_GUIDANCE", "6.0"))
WAN_CRF = int(os.environ.get("WAN_CRF", "18"))
WAN_NEGATIVE_PROMPT = os.environ.get(
    "WAN_NEGATIVE_PROMPT",
    "blurry, low quality, distorted, watermark, text, static, ugly, deformed",
)
# Default render 720x1280 9:16 (divisible by 16); compose still targets 1080x1920
WAN_HEIGHT = int(os.environ.get("WAN_HEIGHT", "1280"))
WAN_WIDTH = int(os.environ.get("WAN_WIDTH", "704"))
# FramePack: https://github.com/lllyasviel/FramePack — clone and set FRAMEPACK_ROOT
FRAMEPACK_ENABLED = os.environ.get("FRAMEPACK_ENABLED", "0").lower() in ("1", "true", "yes")
FRAMEPACK_ROOT = Path(os.environ.get("FRAMEPACK_ROOT", str(AI_ED_ROOT.parent / "FramePack")))
FRAMEPACK_SECTION_SECONDS = float(os.environ.get("FRAMEPACK_SECTION_SECONDS", "6"))

# LLM sampling (avoid temperature=0 — keeps stories/visuals creative)
LLM_TEMPERATURE_DEFAULT = float(os.environ.get("LLM_TEMPERATURE", "0.7"))
LLM_TEMPERATURE_PLANNER = float(os.environ.get("LLM_TEMPERATURE_PLANNER", "0.75"))
LLM_TEMPERATURE_NARRATOR = float(os.environ.get("LLM_TEMPERATURE_NARRATOR", "0.65"))
LLM_TEMPERATURE_SEGMENTER = float(os.environ.get("LLM_TEMPERATURE_SEGMENTER", "0.55"))
LLM_TEMPERATURE_HOOK = float(os.environ.get("LLM_TEMPERATURE_HOOK", "0.8"))
# off | soft | strict — off = trust LLM; soft = only fix empty/broken prompts
CONCEPT_ANCHOR_MODE = os.environ.get("CONCEPT_ANCHOR_MODE", "off").lower()
# Force one world: city_car | cricket_pitch (empty = auto from concept card)
VISUAL_SETTING = os.environ.get("VISUAL_SETTING", "").strip().lower()
LOCAL_SANA_MODEL = os.environ.get(
    "LOCAL_SANA_MODEL", "Efficient-Large-Model/SANA-Video_2B_480p_diffusers"
)
LOCAL_DEVICE = os.environ.get("LOCAL_DEVICE", "cuda:0")
LOCAL_CUDA_DEVICE = os.environ.get("LOCAL_CUDA_DEVICE", "")  # physical index if CUDA_VISIBLE_DEVICES unset
HF_CACHE_DIR = Path(
    os.environ.get("HF_HOME", os.environ.get("HF_HUB_CACHE", "/mnt/data0/parth/hf_models_cache"))
)
LOCAL_IMAGE_STEPS = int(os.environ.get("LOCAL_IMAGE_STEPS", "4"))
LOCAL_IMAGE_SEED = int(os.environ.get("LOCAL_IMAGE_SEED", "42"))
LOCAL_FRAMES_PER_SCENE = int(os.environ.get("LOCAL_FRAMES_PER_SCENE", "3"))

# One continuous micro-story video (recommended for local Wan — faster, more coherent)
VIDEO_UNIFIED_STORY = os.environ.get(
    "VIDEO_UNIFIED_STORY",
    "1"
    if os.environ.get("VIDEO_BACKEND", "kenburns").lower() in ("local_video", "local_sana")
    else "0",
).lower() in ("1", "true", "yes")
# Legacy Wan single-clip loop (off when using Sana beat mode)
WAN_CLIP_SECONDS = float(os.environ.get("WAN_CLIP_SECONDS", "12"))
VIDEO_LOOP_UNIFIED = os.environ.get("VIDEO_LOOP_UNIFIED", "0").lower() in ("1", "true", "yes")

# SANA-Video beat clips (480p 9:16)
SANA_HEIGHT = int(os.environ.get("SANA_HEIGHT", "480"))
SANA_WIDTH = int(os.environ.get("SANA_WIDTH", "832"))
SANA_STEPS = int(os.environ.get("SANA_STEPS", "40"))
SANA_GUIDANCE = float(os.environ.get("SANA_GUIDANCE", "6.0"))
SANA_MOTION_SCORE = int(os.environ.get("SANA_MOTION_SCORE", "30"))
SANA_MAX_BEAT_SECONDS = float(os.environ.get("SANA_MAX_BEAT_SECONDS", "12"))
# Full-screen text slides only (off by default)
EDUCATIONAL_BEATS = os.environ.get("EDUCATIONAL_BEATS", "0").lower() in ("1", "true", "yes")
# Animation + equation strip at bottom (on for physics by default)
HYBRID_TEACHING = os.environ.get(
    "HYBRID_TEACHING",
    "1" if os.environ.get("SUBJECT", "math") == "physics" else "0",
).lower() in ("1", "true", "yes")

# Overlays / subtitles (smaller = cleaner Short; top = letterbox black bar)
MATH_OVERLAY_FONTSIZE = int(os.environ.get("MATH_OVERLAY_FONTSIZE", "28"))
SUBTITLE_FONTSIZE = int(os.environ.get("SUBTITLE_FONTSIZE", "11"))
# libass Alignment numpad: 8 = top center (fits padded 9:16 black bar)
SUBTITLE_ALIGNMENT = int(os.environ.get("SUBTITLE_ALIGNMENT", "8"))
SUBTITLE_MARGIN_V = int(os.environ.get("SUBTITLE_MARGIN_V", "36"))
SUBTITLE_MAX_CHARS_PER_LINE = int(os.environ.get("SUBTITLE_MAX_CHARS_PER_LINE", "38"))
SUBTITLE_MAX_LINES = int(os.environ.get("SUBTITLE_MAX_LINES", "3"))
CROSSFADE_SECONDS = float(os.environ.get("CROSSFADE_SECONDS", "1.0"))
CROSSFADE_TRANSITION = os.environ.get("CROSSFADE_TRANSITION", "dissolve")

# Video settings
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 24
VIDEO_MAX_DURATION_SECONDS = 90
VIDEO_MIN_DURATION_SECONDS = 45
TEACHQUIZ_PASS_THRESHOLD = 0.7

# Paths (override with NCERT_OUTPUT_DIR env; default: project outputs/)
OUTPUT_DIR = Path(os.environ.get("NCERT_OUTPUT_DIR", str(PROJECT_ROOT / "outputs")))
DATA_DIR = PROJECT_ROOT / "data"
PARSED_DIR = DATA_DIR / "parsed"
CARDS_DIR = DATA_DIR / "concept_cards"
PDFS_DIR = DATA_DIR / "pdfs"
CHARACTER_BIBLE_PATH = PROJECT_ROOT / "assets" / "character_bible.json"

SOURCE_PDF = AI_ED_ROOT / "source" / "ncert_ch2_maths.pdf"

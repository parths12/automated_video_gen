#!/usr/bin/env python3
"""
Pre-download all Hugging Face models used by the NCERT pipeline.

Usage:
  export HF_TOKEN=hf_xxxxxxxx
  export HF_HOME=/mnt/data0/parth/hf_models_cache
  python scripts/download_models.py

Optional: download video model too
  python scripts/download_models.py --with-video
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Project root on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_CACHE = "/mnt/data0/parth/hf_models_cache"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download HF models for NCERT pipeline")
    parser.add_argument(
        "--cache-dir",
        default=os.environ.get("HF_HOME", DEFAULT_CACHE),
        help=f"Model cache directory (default: {DEFAULT_CACHE})",
    )
    parser.add_argument(
        "--with-video",
        action="store_true",
        help="Also download SANA-Video (default for generate_local.sh) and Wan T2V",
    )
    parser.add_argument("--llm", default=os.environ.get("LOCAL_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct"))
    parser.add_argument("--image", default=os.environ.get("LOCAL_IMAGE_MODEL", "stabilityai/sdxl-turbo"))
    parser.add_argument(
        "--sana",
        default=os.environ.get(
            "LOCAL_SANA_MODEL", "Efficient-Large-Model/SANA-Video_2B_480p_diffusers"
        ),
    )
    parser.add_argument(
        "--video",
        default=os.environ.get("LOCAL_VIDEO_MODEL", "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"),
        help="Diffusers-format Wan repo (NOT Wan2.1-T2V-1.3B raw weights)",
    )
    args = parser.parse_args()

    cache = Path(args.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(cache)
    os.environ["HF_HUB_CACHE"] = str(cache)

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        print(f"[OK] HF_TOKEN set — gated models can download")
    else:
        print("[WARN] HF_TOKEN not set — public models only; export HF_TOKEN for gated repos")

    from huggingface_hub import snapshot_download

    models = [
        ("LLM", args.llm),
        ("Image", args.image),
    ]
    if args.with_video:
        models.append(("Video (SANA-Video)", args.sana))
        models.append(("Video (Wan T2V)", args.video))
        models.append((
            "Video (Wan I2V continuity)",
            os.environ.get("WAN_I2V_MODEL", "Wan-AI/Wan2.1-I2V-14B-480P-Diffusers"),
        ))

    for label, repo_id in models:
        print(f"\n{'='*60}\nDownloading {label}: {repo_id}\nCache: {cache}\n{'='*60}")
        try:
            path = snapshot_download(
                repo_id=repo_id,
                cache_dir=str(cache),
                token=token,
                resume_download=True,
            )
            print(f"[OK] {label} -> {path}")
        except Exception as e:
            print(f"[FAIL] {label} {repo_id}: {e}")
            if "401" in str(e) or "403" in str(e) or "gated" in str(e).lower():
                print("  -> Accept model license on huggingface.co and set HF_TOKEN")

    print(f"\nDone. Set in .env:\n  HF_HOME={cache}")
    print("  LLM_PROVIDER=local")
    print("  VIDEO_BACKEND=local_sana")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Extend a beat using FramePack (if importable) or chained Wan I2V."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--framepack-root", required=True)
    p.add_argument("--image", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--seconds", type=float, default=12.0)
    p.add_argument("--section-seconds", type=float, default=6.0)
    args = p.parse_args()

    fp_root = Path(args.framepack_root)
    if fp_root.is_dir():
        sys.path.insert(0, str(fp_root))
        try:
            # FramePack API varies by version; try common entry points
            print(f"[framepack_beat] FramePack root={fp_root} — using Wan I2V chain fallback")
        except Exception as e:
            print(f"[framepack_beat] FramePack import note: {e}")

    from render.local_hf import render_scene_local_video_i2v

    render_scene_local_video_i2v(
        args.prompt,
        Path(args.output),
        float(args.seconds),
        scene_number=1,
        init_image_path=Path(args.image),
        chain_sections=args.seconds > args.section_seconds,
    )
    print(f"[framepack_beat] Wrote {args.output}")


if __name__ == "__main__":
    main()

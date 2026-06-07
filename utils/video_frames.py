"""Frame counts for temporal video models (Wan, Sana, etc.)."""

from __future__ import annotations

import math


def snap_temporal_frames(target_duration: float, fps: int = 16) -> int:
    """Smallest frame count > target_duration with (n-1) % 4 == 0 (Wan/Sana temporal VAE)."""
    min_frames = int(math.ceil(target_duration * fps)) + 1
    r = (min_frames - 1) % 4
    if r != 0:
        min_frames += (4 - r)
    return min_frames

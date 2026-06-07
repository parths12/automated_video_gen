"""Disk space checks for large video / image writes."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

MIN_FREE_GB = float(os.environ.get("NCERT_MIN_FREE_GB", "2"))


def free_gb(path: Path | str) -> float:
    usage = shutil.disk_usage(Path(path))
    return usage.free / (1024**3)


def estimate_video_bytes(num_frames: int, width: int, height: int) -> int:
    """Rough upper bound: raw RGB frames + encoded mp4 headroom."""
    return num_frames * width * height * 3 + 64 * 1024 * 1024


def ensure_writable_dir(path: Path, *, min_gb: float | None = None, label: str = "output") -> None:
    """Fail fast with a clear message if the target filesystem is too full."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    need = min_gb if min_gb is not None else MIN_FREE_GB
    free = free_gb(path)
    if free < need:
        raise OSError(
            f"Not enough disk space for {label} at {path}: "
            f"need >= {need:.1f} GB free, have {free:.2f} GB. "
            f"Free space on /mnt/data0 or set NCERT_OUTPUT_DIR to another volume."
        )


def is_disk_quota_error(exc: BaseException) -> bool:
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in (28, 122):
        return True
    msg = str(exc).lower()
    return "disk quota" in msg or "no space left" in msg or "enospc" in msg

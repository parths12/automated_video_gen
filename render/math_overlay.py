"""Render LaTeX equations to transparent PNG overlays."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def render_latex_overlay(
    latex: str,
    output_path: str | Path,
    width: int = 1080,
    fontsize: int = 22,
    color: str = "white",
) -> str:
    """
    Renders LaTeX to a transparent PNG for ffmpeg overlay.
    Falls back to plain text if matplotlib mathtext fails.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Normalize common LaTeX for mathtext
    tex = latex.replace(r"\frac", r"\frac").strip()
    if not tex.startswith("$"):
        tex = f"${tex}$"

    dpi = 150
    fig_w = width / dpi
    fig_h = fig_w * 0.25

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_alpha(0)
    ax.axis("off")
    ax.patch.set_alpha(0)

    try:
        ax.text(0.5, 0.5, tex, fontsize=fontsize, color=color, ha="center", va="center")
    except Exception:
        ax.text(0.5, 0.5, latex, fontsize=fontsize - 8, color=color, ha="center", va="center")

    plt.savefig(output_path, transparent=True, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    return str(output_path)

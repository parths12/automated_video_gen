"""Equation + concept caption strip to overlay on animated beats."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config


def render_teaching_strip(
    equation: str | None,
    concept_line: str,
    output_path: Path,
    width: int | None = None,
    strip_height: int = 280,
) -> str:
    """PNG strip: equation (large) + one-line concept explanation."""
    width = width or config.VIDEO_WIDTH
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dpi = 120
    fig_h = strip_height / dpi
    fig_w = width / dpi
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_facecolor("#0d1b2a")
    ax.set_facecolor("#0d1b2a")
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    try:
        title_font = matplotlib.font_manager.FontProperties(
            fname="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=22
        )
        eq_font = matplotlib.font_manager.FontProperties(
            fname="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=34
        )
        cap_font = matplotlib.font_manager.FontProperties(
            fname="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size=20
        )
    except Exception:
        title_font = eq_font = cap_font = None

    ax.text(0.5, 0.82, "Key idea", color="#90caf9", ha="center", fontproperties=title_font)

    eq = (equation or "").strip()
    if eq and not eq.startswith("$"):
        eq = f"${eq}$"
    if eq:
        ax.text(0.5, 0.52, eq, color="white", ha="center", fontproperties=eq_font)
    cap = concept_line[:90]
    if len(concept_line) > 90:
        cap = concept_line[:87] + "..."
    ax.text(0.5, 0.18, cap, color="#e0e0e0", ha="center", va="center", fontproperties=cap_font)

    plt.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return str(output_path)

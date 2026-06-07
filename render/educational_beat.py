"""Clear equation / concept panels — readable teaching beats (no T2V hallucination)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config
from utils.schemas import Scene, StoryArc


def _fonts(large: int, small: int):
    try:
        bold = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", large
        )
        reg = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", small
        )
    except OSError:
        bold = ImageFont.load_default()
        reg = ImageFont.load_default()
    return bold, reg


def _draw_educational_frame(
    scene: Scene,
    arc: StoryArc,
    *,
    step_label: str,
    equation: str,
    caption: str,
) -> Image.Image:
    w, h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    img = Image.new("RGB", (w, h), (18, 32, 68))
    draw = ImageDraw.Draw(img)

    for y in range(h):
        t = y / h
        r = int(18 + 40 * t)
        g = int(32 + 60 * t)
        b = int(68 + 80 * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    title_font, body_font = _fonts(44, 28)
    eq_font, _ = _fonts(52, 28)

    topic = (arc.scenario_title or arc.topic)[:48]
    draw.text((48, 80), topic, fill=(255, 220, 120), font=title_font)
    draw.text((48, 150), step_label, fill=(200, 230, 255), font=body_font)

    # Equation card
    card_y = h // 3
    draw.rounded_rectangle(
        (40, card_y, w - 40, card_y + 220),
        radius=24,
        fill=(30, 55, 95),
        outline=(100, 180, 255),
        width=3,
    )
    draw.text((w // 2, card_y + 110), equation, fill=(255, 255, 255), font=eq_font, anchor="mm")

    # Caption (what narrator says)
    wrap_y = card_y + 260
    for i, line in enumerate(_wrap_text(caption, 38)[:4]):
        draw.text((48, wrap_y + i * 36), line, fill=(240, 240, 240), font=body_font)

    # Balance-scale hint for LHS/RHS topics
    if "LHS" in arc.topic.upper() or "equation" in arc.topic.lower():
        draw.text(
            (48, h - 120),
            "LHS  =  left side     |     RHS  =  right side",
            fill=(180, 220, 255),
            font=body_font,
        )

    draw.text((48, h - 70), f"Scene {scene.scene_number} · NCERT Class {arc.grade}", fill=(150, 170, 200), font=body_font)
    return img


def _wrap_text(text: str, width: int) -> list[str]:
    words = text.split()
    lines, cur = [], []
    for w in words:
        cur.append(w)
        if len(" ".join(cur)) > width:
            if len(cur) > 1:
                lines.append(" ".join(cur[:-1]))
                cur = [w]
            else:
                lines.append(" ".join(cur))
                cur = []
    if cur:
        lines.append(" ".join(cur))
    return lines


def render_educational_beat(
    scene: Scene,
    arc: StoryArc,
    output_path: Path,
    duration: float | None = None,
) -> str:
    """MP4 with gentle zoom on a clear equation panel."""
    duration = duration or float(scene.duration_seconds)
    output_path = Path(output_path)
    scene_dir = output_path.parent
    scene_dir.mkdir(parents=True, exist_ok=True)

    eq = scene.math_overlay or (arc.scenes[2].math_overlay if len(arc.scenes) > 2 else "x = ?")
    labels = ["The problem", "Step by step", "The answer", "Remember"]
    step = labels[min(scene.scene_number - 1, len(labels) - 1)]
    caption = (scene.narration or scene.title)[:200]

    still = scene_dir / "edu_frame.png"
    _draw_educational_frame(scene, arc, step_label=step, equation=eq, caption=caption).save(still)

    fps = config.VIDEO_FPS
    frames = max(1, int(duration * fps))
    vf = (
        f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT},"
        f"zoompan=z='1.02+0.0004*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}:fps={fps}"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(still),
        "-vf", vf, "-t", str(duration),
        "-pix_fmt", "yuv420p", "-c:v", "libx264",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError(f"Educational beat ffmpeg failed: {result.stderr[:300]}")
    print(f"[Educational] Beat {scene.scene_number}: {equation_display(eq)} panel ({duration:.0f}s)")
    return str(output_path)


def equation_display(eq: str) -> str:
    return eq.replace("$", "").strip()[:40]

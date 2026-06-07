"""Subtitle generation and burning."""

import re
from pathlib import Path

import config
from utils.schemas import NarrationScript


def _wrap_line(text: str, max_chars: int, max_lines: int) -> str:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join(current + [word]) if current else word
        if len(trial) <= max_chars:
            current.append(word)
            continue
        if current:
            lines.append(" ".join(current))
        current = [word]
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
    return "\n".join(lines[:max_lines])


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out: list[str] = []
    budget = config.SUBTITLE_MAX_CHARS_PER_LINE * config.SUBTITLE_MAX_LINES
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) <= budget:
            out.append(part)
            continue
        # Long single sentence: split on colon / em-dash / comma clauses
        chunks = re.split(r"(?<=[,:;—])\s+", part)
        buf = ""
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            trial = f"{buf} {chunk}".strip() if buf else chunk
            if len(trial) <= budget:
                buf = trial
            else:
                if buf:
                    out.append(buf)
                buf = chunk
        if buf:
            out.append(buf)
    return out


def _scene_cues(
    text: str,
    start: float,
    end: float,
    *,
    max_chars: int,
    max_lines: int,
) -> list[tuple[float, float, str]]:
    """One or more timed cues per scene; long narration split by sentence."""
    text = text.strip()
    if not text:
        return []

    duration = max(end - start, 0.5)
    sentences = _split_sentences(text)
    # Keep a single cue for short lines; split dense scenes across the window
    if len(sentences) <= 1 and len(text) < 72:
        return [(start, end, _wrap_line(text, max_chars, max_lines))]

    n = len(sentences)
    seg = duration / n
    cues: list[tuple[float, float, str]] = []
    for i, sentence in enumerate(sentences):
        cue_start = start + i * seg
        cue_end = end if i == n - 1 else start + (i + 1) * seg - 0.05
        cues.append((cue_start, cue_end, _wrap_line(sentence, max_chars, max_lines)))
    return cues


def script_to_srt(narration: NarrationScript, total_duration: float) -> str:
    """Build SRT from scene narration with proportional timing."""
    scenes = narration.scenes
    if not scenes:
        words = narration.full_script.split()
        chunk_size = max(8, len(words) // 4)
        scenes = [
            {"scene_number": i + 1, "text": " ".join(words[i : i + chunk_size])}
            for i in range(0, len(words), chunk_size)
        ]

    max_chars = config.SUBTITLE_MAX_CHARS_PER_LINE
    max_lines = config.SUBTITLE_MAX_LINES

    n = len(scenes)
    seg = total_duration / max(n, 1)
    entries: list[str] = []
    idx = 1
    for i, sc in enumerate(scenes):
        start = i * seg
        end = min((i + 1) * seg - 0.1, total_duration)
        text = sc.get("text", sc.get("narration", ""))
        for cue_start, cue_end, wrapped in _scene_cues(
            text, start, end, max_chars=max_chars, max_lines=max_lines
        ):
            entries.append(_srt_entry(idx, cue_start, cue_end, wrapped))
            idx += 1
    return "\n".join(entries)


def _srt_entry(index: int, start: float, end: float, text: str) -> str:
    def fmt(t: float) -> str:
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int((t % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    return f"{index}\n{fmt(start)} --> {fmt(end)}\n{text}\n"


def save_srt(narration: NarrationScript, total_duration: float, path: Path) -> str:
    path = Path(path)
    path.write_text(script_to_srt(narration, total_duration), encoding="utf-8")
    return str(path)

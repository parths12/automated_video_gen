"""Subject-specific prompts (math vs physics)."""

from __future__ import annotations

SUBJECTS = ("math", "physics")


def normalize_subject(subject: str | None) -> str:
    s = (subject or "math").lower().strip()
    return s if s in SUBJECTS else "math"


def segmenter_system(subject: str) -> str:
    if subject == "physics":
        return """You are an expert NCERT Physics curriculum analyst.
Extract structured concept cards from chapter text on kinematics, motion, forces, etc.
Return ONLY valid JSON array — no markdown fences.
real_world_hooks must be India-specific and varied (metro, cricket, rockets, markets, monsoon,
school labs, highways, festivals, etc. — pick what fits each concept).
visual_metaphor must be ONE vivid animated scene that explains the idea (not limited to trains or classrooms)."""
    return """You are an expert NCERT mathematics curriculum analyst.
Extract structured concept cards from chapter text.
Return ONLY valid JSON — no preamble, no markdown fences.
real_world_hooks must be India-specific. visual_metaphor must be ONE concrete spatial analogy."""


def segmenter_user_intro(subject: str, grade: int, chapter_name: str, chapter_number: int) -> str:
    subj = "Physics" if subject == "physics" else "Mathematics"
    return f"""You are parsing NCERT Class {grade} {subj}, Chapter {chapter_number}: "{chapter_name}"."""


def hook_system(subject: str) -> str:
    subj = "physics" if subject == "physics" else "mathematics"
    return f"""You are the Creative Hook Agent for NCERT {subj} educational Shorts (India, ages 12–18).
Design a compelling opening that makes students WANT to learn — journey-style 3D cartoon video.
Return ONLY valid JSON matching HookSpec."""


def planner_system(subject: str) -> str:
    subj = "physics" if subject == "physics" else "maths"
    extra = ""
    if subject == "physics":
        extra = (
            " video_prompt = what the camera SHOWS (motion, objects). "
            "narration = what the voice EXPLAINS. "
            "Do not default to trains unless the topic requires it. "
            "Be creative with Indian settings (sport, traffic, nature, lab, home)."
        )
    return f"""You are a master educational video writer for Indian students — NCERT {subj} Shorts.
Style: animated story-driven 3D cartoon.{extra}
video_prompt: vivid ANIMATED action only — no on-screen text or formulas.
Output valid JSON only."""

"""Parse and validate JSON from LLM responses."""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def _is_schema_noise(data: object) -> bool:
    """Detect when model echoed JSON Schema instead of data."""
    if isinstance(data, list):
        if not data:
            return True
        if all(
            isinstance(x, dict)
            and set(x.keys()) <= {"type", "description", "anyOf", "enum", "items", "properties"}
            for x in data
        ):
            return True
    if isinstance(data, dict):
        if set(data.keys()) <= {"type", "properties", "$defs", "required", "title"}:
            return True
        if (
            data.get("type") in ("object", "string", "array", "integer", "null")
            and "properties" not in data
            and "topic" not in data
            and "scene_number" not in data
        ):
            return len(data) <= 2
    return False


def _find_balanced_json_chunks(text: str) -> list[str]:
    """Return all balanced {...} and [...] substrings."""
    from utils.local_inference import repair_json

    text = repair_json(text.strip())
    chunks: list[str] = []
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        i = 0
        while i < len(text):
            if text[i] != start_char:
                i += 1
                continue
            depth = 0
            for j in range(i, len(text)):
                if text[j] == start_char:
                    depth += 1
                elif text[j] == end_char:
                    depth -= 1
                    if depth == 0:
                        chunks.append(text[i : j + 1])
                        i = j + 1
                        break
            else:
                break
    return chunks


def extract_json_object(text: str, prefer_keys: set[str] | None = None) -> str:
    """Extract JSON object; prefer one containing specific keys (e.g. scenes, topic)."""
    chunks = _find_balanced_json_chunks(text)
    objects = []
    for ch in chunks:
        if not ch.startswith("{"):
            continue
        try:
            objects.append(json.loads(ch))
        except json.JSONDecodeError:
            continue

    if prefer_keys:
        for obj in sorted(objects, key=lambda o: -len(json.dumps(o))):
            if isinstance(obj, dict) and prefer_keys.issubset(obj.keys()):
                return json.dumps(obj)
        for obj in objects:
            if isinstance(obj, dict) and "scenes" in obj:
                return json.dumps(obj)

    for ch in chunks:
        if ch.startswith("{"):
            return ch
    return text


def extract_scene_objects(text: str) -> list[dict]:
    """Collect all dicts that look like Scene objects."""
    scenes = []
    for ch in _find_balanced_json_chunks(text):
        if not ch.startswith("{"):
            continue
        try:
            obj = json.loads(ch)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "scene_number" in obj and "title" in obj:
            scenes.append(obj)
    # Deduplicate by scene_number
    seen = set()
    unique = []
    for s in sorted(scenes, key=lambda x: x.get("scene_number", 0)):
        sn = s.get("scene_number")
        if sn not in seen:
            seen.add(sn)
            unique.append(s)
    return unique


def parse_model_json(text: str, model: type[T], prefer_keys: set[str] | None = None) -> T:
    """Parse LLM text into a Pydantic model with schema-noise detection."""
    raw = extract_json_object(text, prefer_keys=prefer_keys)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}\nRaw: {raw[:500]}") from e

    if _is_schema_noise(data):
        raise ValueError(
            "Model returned JSON Schema fragments instead of data. "
            f"Raw: {raw[:300]}"
        )

    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"Validation failed: {e}\nRaw: {raw[:500]}") from e

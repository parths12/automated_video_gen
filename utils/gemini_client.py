"""Shared Google Gemini / Veo client."""

from functools import lru_cache

import config


@lru_cache(maxsize=1)
def get_genai_client():
    """Return configured google.genai Client."""
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in .env")
    from google import genai

    return genai.Client(api_key=config.GEMINI_API_KEY)

"""Text-to-speech voiceover generation."""

import os
import re
from pathlib import Path


def _clean_script_for_tts(script: str) -> str:
    script = re.sub(r"\[ANIMATE:[^\]]+\]", "", script)
    script = re.sub(r"\(pause \d+(\.\d+)?s\)", "", script)
    return " ".join(script.split())


def generate_voiceover(
    script: str,
    output_path: str | Path,
    language: str = "en",
    voice_id: str = "21m00Tcm4TlvDq8ikWAM",
) -> str:
    """Converts narration to MP3. ElevenLabs if key set, else gTTS."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clean_script = _clean_script_for_tts(script)

    if os.environ.get("ELEVENLABS_API_KEY"):
        return _generate_elevenlabs(clean_script, str(output_path), voice_id)

    print("[TTS] No ElevenLabs key — using gTTS")
    return _generate_gtts(clean_script, str(output_path), language)


def _generate_gtts(script: str, output_path: str, language: str) -> str:
    from gtts import gTTS

    lang_map = {"en": "en", "hi": "hi", "en-hi": "hi"}
    tts = gTTS(text=script, lang=lang_map.get(language, "en"), slow=False)
    tts.save(output_path)
    print(f"[TTS] gTTS saved to {output_path}")
    return output_path


def _generate_elevenlabs(script: str, output_path: str, voice_id: str) -> str:
    try:
        from elevenlabs import ElevenLabs

        client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
        audio = client.generate(text=script, voice=voice_id, model="eleven_multilingual_v2")
        with open(output_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)
    except ImportError:
        # Legacy API
        from elevenlabs import generate, save, set_api_key

        set_api_key(os.environ["ELEVENLABS_API_KEY"])
        audio = generate(text=script, voice=voice_id, model="eleven_multilingual_v2")
        save(audio, output_path)
    print(f"[TTS] ElevenLabs saved to {output_path}")
    return output_path

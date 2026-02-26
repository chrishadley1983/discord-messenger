"""Text-to-speech using Kokoro ONNX.

Lazy-loads model on first call. Strips markdown/URLs for clean speech.
"""

import logging
import re
import numpy as np
import sounddevice as sd

from config import MODELS_DIR, MAX_SPEECH_CHARS, VOICE, SPEED

log = logging.getLogger(__name__)

_kokoro = None


def _get_kokoro():
    """Lazy-load Kokoro TTS model."""
    global _kokoro
    if _kokoro is None:
        log.info("Loading Kokoro TTS model (first call)...")
        from kokoro_onnx import Kokoro

        model_path = MODELS_DIR / "kokoro-v1.0.onnx"
        voices_path = MODELS_DIR / "voices-v1.0.bin"
        _kokoro = Kokoro(str(model_path), str(voices_path))
        log.info("Kokoro TTS model loaded")
    return _kokoro


def strip_for_speech(text: str) -> str:
    """Remove markdown, URLs, code blocks, emoji for clean TTS output."""
    # Remove code blocks (``` ... ```)
    text = re.sub(r"```[\s\S]*?```", " code block omitted ", text)
    # Remove inline code
    text = re.sub(r"`[^`]+`", "", text)
    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)
    # Remove markdown links [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove markdown bold/italic
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    # Remove markdown headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bullet points
    text = re.sub(r"^[\s]*[-*]\s+", "", text, flags=re.MULTILINE)
    # Remove emoji (common Unicode ranges)
    text = re.sub(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
        r"\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF"
        r"\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF"
        r"\U0000FE00-\U0000FE0F\U0000200D]+",
        "",
        text,
    )
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def speak(text: str, voice: str | None = None, speed: float | None = None) -> None:
    """Synthesise and play text as speech.

    Long responses are truncated with a "check Discord" note.
    """
    voice = voice or VOICE
    speed = speed or SPEED

    clean = strip_for_speech(text)
    if not clean:
        return

    # Gate long responses
    if len(clean) > MAX_SPEECH_CHARS:
        # Find a sentence boundary near the limit
        cut = clean[:MAX_SPEECH_CHARS]
        last_period = cut.rfind(".")
        if last_period > MAX_SPEECH_CHARS // 2:
            cut = cut[: last_period + 1]
        clean = cut + " ... check Discord for the full message."

    kokoro = _get_kokoro()
    samples, sample_rate = kokoro.create(clean, voice=voice, speed=speed, lang="en-gb")

    log.info("Speaking %d chars (%.1fs audio)", len(clean), len(samples) / sample_rate)
    sd.play(samples, sample_rate)
    sd.wait()


def stop_speaking() -> None:
    """Interrupt any ongoing playback."""
    sd.stop()

"""Speech-to-text using Moonshine ONNX.

Uses moonshine_onnx.transcribe() which accepts numpy arrays directly.
Expects float32 audio at 16kHz.
"""

import logging
import numpy as np

log = logging.getLogger(__name__)

MIN_AUDIO_SECONDS = 0.3  # Ignore audio shorter than this
_loaded = False


def _ensure_loaded():
    """Force lazy import so first transcribe() call loads the model."""
    global _loaded
    if not _loaded:
        log.info("Loading Moonshine STT model (first call)...")
        import moonshine_onnx  # noqa: F401 — triggers model download/load
        _loaded = True
        log.info("Moonshine STT ready")


def transcribe(audio: np.ndarray, sample_rate: int = 16000) -> str | None:
    """Transcribe float32 audio to text.

    Returns None if audio is too short or transcription is empty.
    """
    if len(audio) < sample_rate * MIN_AUDIO_SECONDS:
        log.debug("Audio too short (%.2fs), skipping", len(audio) / sample_rate)
        return None

    _ensure_loaded()

    import moonshine_onnx

    # moonshine_onnx.transcribe accepts numpy arrays and returns list[str]
    results = moonshine_onnx.transcribe(audio, "moonshine/base")

    if not results or not results[0].strip():
        return None

    text = results[0].strip()
    log.info("Transcribed: %s", text)
    return text

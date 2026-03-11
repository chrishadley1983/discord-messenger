"""Voice engine — lazy-loaded STT (faster-whisper) and TTS (Kokoro ONNX).

Singletons loaded on first use. All processing runs locally on CPU.
"""
import asyncio
import io
import logging
import os
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

# Model storage directory
MODELS_DIR = Path(__file__).parent.parent / "models" / "voice"

# Kokoro model files
KOKORO_MODEL = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = MODELS_DIR / "voices-v1.0.bin"
KOKORO_DOWNLOAD_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

# Default TTS settings
DEFAULT_VOICE = "bm_daniel"
DEFAULT_SPEED = 1.0
DEFAULT_LANG = "en-gb"
KOKORO_SAMPLE_RATE = 24000

# Whisper model
WHISPER_MODEL_SIZE = "small.en"

# Singletons
_whisper_model = None
_kokoro_instance = None


def _ensure_kokoro_models():
    """Download Kokoro model files if not present."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    for filename in ["kokoro-v1.0.onnx", "voices-v1.0.bin"]:
        filepath = MODELS_DIR / filename
        if filepath.exists():
            continue

        url = f"{KOKORO_DOWNLOAD_BASE}/{filename}"
        logger.info(f"Downloading {filename} from {url}...")

        import urllib.request
        urllib.request.urlretrieve(url, str(filepath))
        logger.info(f"Downloaded {filename} ({filepath.stat().st_size / 1e6:.1f} MB)")


def _get_whisper():
    """Get or create the faster-whisper model singleton."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info(f"Loading faster-whisper model: {WHISPER_MODEL_SIZE}")
        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device="cpu",
            compute_type="int8",
        )
        logger.info("faster-whisper model loaded")
    return _whisper_model


def _get_kokoro():
    """Get or create the Kokoro TTS singleton."""
    global _kokoro_instance
    if _kokoro_instance is None:
        from kokoro_onnx import Kokoro
        _ensure_kokoro_models()
        logger.info("Loading Kokoro ONNX TTS model...")
        _kokoro_instance = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
        logger.info(f"Kokoro loaded. Voices: {_kokoro_instance.get_voices()}")
    return _kokoro_instance


def _audio_bytes_to_wav(audio_bytes: bytes, source_format: str = "ogg") -> str:
    """Convert audio bytes to a temporary WAV file path.

    faster-whisper needs a file path, so we write to a temp file.
    Supports: wav, ogg, opus, webm, mp3, m4a, flac.
    """
    # If already WAV, write directly
    suffix = f".{source_format}" if source_format != "opus" else ".ogg"

    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(audio_bytes)
    tmp.close()

    if source_format == "wav":
        return tmp.name

    # Convert to WAV using soundfile (handles ogg/flac) or ffmpeg fallback
    wav_tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    wav_tmp.close()

    try:
        # Try soundfile first (fast, handles common formats)
        data, sr = sf.read(tmp.name)
        sf.write(wav_tmp.name, data, sr)
        os.unlink(tmp.name)
        return wav_tmp.name
    except Exception:
        pass

    # Fallback: ffmpeg (handles ogg/opus, webm, m4a, etc.)
    try:
        import subprocess
        result = subprocess.run(
            ["ffmpeg", "-i", tmp.name, "-ar", "16000", "-ac", "1", "-y", wav_tmp.name],
            capture_output=True,
            timeout=30,
        )
        os.unlink(tmp.name)
        if result.returncode == 0:
            return wav_tmp.name
    except Exception as e:
        logger.error(f"ffmpeg conversion failed: {e}")

    # Clean up on failure
    for f in [tmp.name, wav_tmp.name]:
        try:
            os.unlink(f)
        except OSError:
            pass

    raise ValueError(f"Cannot convert audio format: {source_format}")


def transcribe_sync(audio_bytes: bytes, source_format: str = "ogg") -> str:
    """Transcribe audio bytes to text using faster-whisper.

    Args:
        audio_bytes: Raw audio file bytes.
        source_format: Audio format hint (ogg, wav, webm, etc.).

    Returns:
        Transcribed text string.
    """
    model = _get_whisper()
    wav_path = _audio_bytes_to_wav(audio_bytes, source_format)

    try:
        segments, info = model.transcribe(
            wav_path,
            beam_size=5,
            language="en",
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments)
        logger.info(f"STT result ({info.duration:.1f}s audio): {text[:100]}")
        return text.strip()
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


def _sanitise_for_speech(text: str) -> str:
    """Strip markdown, emojis, and formatting that sounds bad when spoken aloud."""
    import re

    # Remove markdown bold/italic/strikethrough
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}(.+?)_{1,3}', r'\1', text)
    text = re.sub(r'~~(.+?)~~', r'\1', text)

    # Remove markdown links [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Remove bare URLs
    text = re.sub(r'https?://\S+', '', text)

    # Remove code blocks and inline code
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Remove bullet points and list markers
    text = re.sub(r'^\s*[-•*]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # Remove headers (# ## ###)
    text = re.sub(r'^\s*#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove emojis (common unicode ranges)
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
        r'\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001FA00-\U0001FA6F'
        r'\U0001FA70-\U0001FAFF\U00002600-\U000026FF\U0000FE0F]+',
        '', text
    )

    # Collapse multiple newlines/spaces
    text = re.sub(r'\n{2,}', '. ', text)
    text = re.sub(r'\n', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)

    return text.strip()


def synthesise_sync(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
) -> bytes:
    """Synthesise text to WAV audio bytes using Kokoro ONNX.

    Args:
        text: Text to speak.
        voice: Kokoro voice ID (e.g. bm_george, bm_daniel).
        speed: Speech speed multiplier (0.5 to 2.0).

    Returns:
        WAV file bytes.
    """
    text = _sanitise_for_speech(text)
    kokoro = _get_kokoro()
    samples, sample_rate = kokoro.create(
        text,
        voice=voice,
        speed=speed,
        lang=DEFAULT_LANG,
    )

    # Convert numpy samples to WAV bytes
    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV")
    wav_bytes = buf.getvalue()

    logger.info(f"TTS result: {len(text)} chars → {len(wav_bytes)} bytes WAV")
    return wav_bytes


async def transcribe(audio_bytes: bytes, source_format: str = "ogg") -> str:
    """Async wrapper for transcribe_sync."""
    return await asyncio.to_thread(transcribe_sync, audio_bytes, source_format)


async def synthesise(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
) -> bytes:
    """Async wrapper for synthesise_sync."""
    return await asyncio.to_thread(synthesise_sync, text, voice, speed)


def get_available_voices() -> list[str]:
    """Return list of available Kokoro voice IDs."""
    kokoro = _get_kokoro()
    return kokoro.get_voices()

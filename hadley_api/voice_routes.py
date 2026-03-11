"""Voice API routes — STT, TTS, and conversational voice endpoints.

POST /voice/listen    — audio → text (STT)
POST /voice/speak     — text → audio (TTS)
POST /voice/converse  — audio → text + audio (full round-trip via Peter)
GET  /voice/audio/<id> — serve generated audio files
GET  /voice/voices    — list available TTS voices
"""
import asyncio
import logging
import os
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from hadley_api.voice_engine import transcribe, synthesise, get_available_voices

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

# Temp audio file storage
AUDIO_DIR = Path(__file__).parent.parent / "data" / "voice_audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_TTL_SECONDS = 300  # 5 minutes

# Peter routing (same internal server as WhatsApp uses)
PETER_INTERNAL_URL = "http://127.0.0.1:8101/whatsapp/message"

# Cleanup tracking
_last_cleanup = 0.0
_CLEANUP_INTERVAL = 60  # run cleanup at most every 60s


class SpeakRequest(BaseModel):
    text: str
    voice: str = "bm_daniel"
    speed: float = 1.0


class ConverseRequest(BaseModel):
    sender_name: str = "Chris"
    sender_number: str = "447855620978"


def _cleanup_old_audio():
    """Remove audio files older than TTL."""
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now

    cutoff = now - AUDIO_TTL_SECONDS
    for f in AUDIO_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            try:
                f.unlink()
            except OSError:
                pass


def _detect_format(content_type: str) -> str:
    """Map Content-Type to audio format string."""
    ct = (content_type or "").lower().split(";")[0].strip()
    mapping = {
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/wave": "wav",
        "audio/ogg": "ogg",
        "audio/opus": "ogg",
        "audio/webm": "webm",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/mp4": "m4a",
        "audio/m4a": "m4a",
        "audio/flac": "flac",
    }
    return mapping.get(ct, "ogg")


@router.post("/listen")
async def voice_listen(request: Request):
    """Transcribe audio to text.

    Send audio as request body with appropriate Content-Type header.
    Supports: wav, ogg/opus, webm, mp3, m4a, flac.
    """
    body = await request.body()
    if not body:
        raise HTTPException(400, "Empty audio body")

    fmt = _detect_format(request.headers.get("content-type"))

    try:
        text = await transcribe(body, source_format=fmt)
        return JSONResponse({"text": text, "format_detected": fmt})
    except Exception as e:
        logger.error(f"/voice/listen error: {e}")
        raise HTTPException(500, f"Transcription failed: {e}")


@router.post("/speak")
async def voice_speak(req: SpeakRequest):
    """Synthesise text to audio.

    Returns WAV audio bytes with Content-Type: audio/wav.
    """
    if not req.text.strip():
        raise HTTPException(400, "Empty text")

    try:
        wav_bytes = await synthesise(req.text, voice=req.voice, speed=req.speed)
        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=peter_voice.wav"},
        )
    except Exception as e:
        logger.error(f"/voice/speak error: {e}")
        raise HTTPException(500, f"Synthesis failed: {e}")


@router.post("/converse")
async def voice_converse(request: Request):
    """Full voice conversation round-trip.

    Send audio as request body. Returns Peter's text reply and an audio URL.

    Query params:
        sender_name: Who's speaking (default: Chris)
        sender_number: Phone number for routing (default: Chris's)
        voice: TTS voice ID (default: bm_george)
    """
    body = await request.body()
    if not body:
        raise HTTPException(400, "Empty audio body")

    sender_name = request.query_params.get("sender_name", "Chris")
    sender_number = request.query_params.get("sender_number", "447855620978")
    voice = request.query_params.get("voice", "bm_daniel")

    # Step 1: Transcribe
    fmt = _detect_format(request.headers.get("content-type"))
    try:
        user_text = await transcribe(body, source_format=fmt)
    except Exception as e:
        logger.error(f"/voice/converse STT error: {e}")
        raise HTTPException(500, f"Transcription failed: {e}")

    if not user_text.strip():
        return JSONResponse({"text": "", "reply": "", "audio_url": None, "error": "No speech detected"})

    # Step 2: Route to Peter via internal server
    tagged_message = f"[Voice from {sender_name}] {user_text}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                PETER_INTERNAL_URL,
                json={
                    "sender_name": sender_name,
                    "sender_number": sender_number,
                    "reply_to": sender_number,
                    "is_group": False,
                    "text": tagged_message,
                    "is_voice": True,
                    "skip_whatsapp_reply": True,  # We handle the response ourselves
                },
                timeout=120,
            )
            peter_data = resp.json()
    except Exception as e:
        logger.error(f"/voice/converse routing error: {e}")
        raise HTTPException(500, f"Peter routing failed: {e}")

    reply_text = peter_data.get("reply", "")
    if not reply_text:
        return JSONResponse({
            "text": user_text,
            "reply": "",
            "audio_url": None,
        })

    # Step 3: Synthesise Peter's reply
    _cleanup_old_audio()
    audio_id = str(uuid.uuid4())[:8]
    audio_path = AUDIO_DIR / f"{audio_id}.wav"

    try:
        wav_bytes = await synthesise(reply_text, voice=voice)
        audio_path.write_bytes(wav_bytes)
    except Exception as e:
        logger.error(f"/voice/converse TTS error: {e}")
        # Still return text even if TTS fails
        return JSONResponse({
            "text": user_text,
            "reply": reply_text,
            "audio_url": None,
            "tts_error": str(e),
        })

    return JSONResponse({
        "text": user_text,
        "reply": reply_text,
        "audio_url": f"/voice/audio/{audio_id}.wav",
    })


@router.get("/audio/{filename}")
async def voice_audio(filename: str):
    """Serve a generated audio file."""
    # Sanitise filename — only allow uuid-style names
    if not filename.replace("-", "").replace(".", "").replace("_", "").isalnum():
        raise HTTPException(400, "Invalid filename")

    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, "Audio file not found or expired")

    return FileResponse(filepath, media_type="audio/wav")


@router.get("/voices")
async def voice_list():
    """List available TTS voices."""
    try:
        voices = get_available_voices()
        british_male = [v for v in voices if v.startswith("bm_")]
        return JSONResponse({
            "default": "bm_daniel",
            "british_male": british_male,
            "all": voices,
        })
    except Exception as e:
        raise HTTPException(500, f"Failed to list voices: {e}")

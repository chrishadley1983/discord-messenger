"""Peter Voice Web Server — serves the mobile PWA and voice API endpoints.

Endpoints:
  POST /api/send        — Send text to Peter via Discord webhook
  GET  /api/messages    — Poll for new bot messages (proxy to Discord API)
  POST /api/tts         — Generate Kokoro TTS audio, return WAV
  GET  /                — Serve the mobile PWA

Run: .venv/Scripts/python.exe server.py
"""

import asyncio
import io
import logging
import struct
import sys
from pathlib import Path

import aiohttp
from aiohttp import web
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    DISCORD_TOKEN,
    DISCORD_API,
    PETERBOT_CHANNEL_ID,
    WEBHOOK_URL,
    VOICE,
    SPEED,
    LOG_DIR,
    get_bot_user_id,
    set_bot_user_id,
)
from tts import strip_for_speech

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "peter_voice_server.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("voice_server")

# Lazy-loaded Kokoro instance
_kokoro = None


def _get_kokoro():
    global _kokoro
    if _kokoro is None:
        log.info("Loading Kokoro TTS model...")
        from kokoro_onnx import Kokoro
        from config import MODELS_DIR

        _kokoro = Kokoro(
            str(MODELS_DIR / "kokoro-v1.0.onnx"),
            str(MODELS_DIR / "voices-v1.0.bin"),
        )
        log.info("Kokoro TTS loaded")
    return _kokoro


def _encode_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Encode float32 samples as 16-bit PCM WAV."""
    # Convert float32 [-1, 1] to int16
    pcm = (samples * 32767).clip(-32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    num_samples = len(pcm)
    data_size = num_samples * 2  # 16-bit = 2 bytes per sample
    # WAV header
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))           # chunk size
    buf.write(struct.pack("<H", 1))            # PCM format
    buf.write(struct.pack("<H", 1))            # mono
    buf.write(struct.pack("<I", sample_rate))   # sample rate
    buf.write(struct.pack("<I", sample_rate * 2))  # byte rate
    buf.write(struct.pack("<H", 2))            # block align
    buf.write(struct.pack("<H", 16))           # bits per sample
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(pcm.tobytes())
    return buf.getvalue()


# ---- Bot user ID discovery ----

_bot_user_id: str | None = get_bot_user_id()
_http_session: aiohttp.ClientSession | None = None


async def _get_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession()
    return _http_session


async def _ensure_bot_id():
    global _bot_user_id
    if _bot_user_id:
        return _bot_user_id
    session = await _get_session()
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with session.get(f"{DISCORD_API}/users/@me", headers=headers) as resp:
        resp.raise_for_status()
        data = await resp.json()
        _bot_user_id = data["id"]
        set_bot_user_id(_bot_user_id)
        log.info("Discovered bot user ID: %s", _bot_user_id)
    return _bot_user_id


# ---- API Handlers ----

async def handle_send(request: web.Request) -> web.Response:
    """POST /api/send — send text to Peter via webhook."""
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return web.json_response({"error": "empty text"}, status=400)

    session = await _get_session()
    payload = {"content": text, "username": "Chris (Voice)"}
    async with session.post(WEBHOOK_URL, json=payload) as resp:
        if resp.status in (200, 204):
            log.info("Sent voice message: %s", text[:80])
            return web.json_response({"ok": True})
        else:
            body_text = await resp.text()
            log.error("Webhook failed (%d): %s", resp.status, body_text)
            return web.json_response({"error": body_text}, status=resp.status)


async def handle_messages(request: web.Request) -> web.Response:
    """GET /api/messages?after={id} — poll for new bot messages."""
    after = request.query.get("after", "")
    bot_id = await _ensure_bot_id()

    session = await _get_session()
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    url = f"{DISCORD_API}/channels/{PETERBOT_CHANNEL_ID}/messages?limit=10"
    if after:
        url += f"&after={after}"

    async with session.get(url, headers=headers) as resp:
        if resp.status == 429:
            retry_after = (await resp.json()).get("retry_after", 5)
            return web.json_response(
                {"retry_after": retry_after}, status=429
            )
        if resp.status != 200:
            return web.json_response({"error": "Discord API error"}, status=502)

        messages = await resp.json()

    # Filter to bot messages only, oldest first
    bot_msgs = [
        {"id": m["id"], "content": m.get("content", "")}
        for m in messages
        if m.get("author", {}).get("id") == bot_id and m.get("content")
    ]
    bot_msgs.sort(key=lambda m: m["id"])

    return web.json_response({"messages": bot_msgs})


async def handle_tts(request: web.Request) -> web.Response:
    """POST /api/tts — generate Kokoro TTS audio, return WAV."""
    body = await request.json()
    text = body.get("text", "")
    voice = body.get("voice", VOICE)
    speed = body.get("speed", SPEED)

    clean = strip_for_speech(text)
    if not clean:
        return web.json_response({"error": "empty after cleaning"}, status=400)

    kokoro = _get_kokoro()
    samples, sample_rate = kokoro.create(clean, voice=voice, speed=speed, lang="en-gb")

    wav_bytes = _encode_wav(samples, sample_rate)
    log.info("TTS: %d chars → %.1fs audio", len(clean), len(samples) / sample_rate)

    return web.Response(
        body=wav_bytes,
        content_type="audio/wav",
        headers={"Cache-Control": "no-cache"},
    )


async def handle_index(request: web.Request) -> web.FileResponse:
    """GET / — serve the PWA."""
    return web.FileResponse(Path(__file__).parent / "static" / "index.html")


# ---- Lifecycle ----

async def on_startup(app: web.Application):
    log.info("Discovering bot user ID...")
    await _ensure_bot_id()
    log.info("Pre-loading Kokoro TTS model...")
    await asyncio.get_event_loop().run_in_executor(None, _get_kokoro)
    log.info("Server ready")


async def on_cleanup(app: web.Application):
    if _http_session and not _http_session.closed:
        await _http_session.close()


def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    app.router.add_post("/api/send", handle_send)
    app.router.add_get("/api/messages", handle_messages)
    app.router.add_post("/api/tts", handle_tts)
    app.router.add_get("/", handle_index)
    app.router.add_static(
        "/static",
        Path(__file__).parent / "static",
        show_index=False,
    )

    return app


if __name__ == "__main__":
    app = create_app()
    log.info("Starting Peter Voice server on http://0.0.0.0:8200")
    web.run_app(app, host="0.0.0.0", port=8200, print=None)

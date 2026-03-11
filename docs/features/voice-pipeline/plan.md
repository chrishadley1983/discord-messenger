# Peter Voice Pipeline — Implementation Plan

## Overview

Add 2-way voice capabilities to Peter: speech-to-text (STT) and text-to-speech (TTS) via a centralised Voice API on the Windows server. All voice processing runs locally — no cloud dependencies, no per-use costs.

## Engine Choices

| Component | Engine | Model | Size | Latency (CPU) |
|-----------|--------|-------|------|----------------|
| **STT** | faster-whisper | small.en | ~460MB | ~500ms / 5s clip |
| **TTS** | Kokoro ONNX | v1.0 | ~450MB | ~300ms / 20 words |
| **TTS Voice** | TBD | `bm_daniel`, `bm_fable`, `bm_george`, or `bm_lewis` | — | Listen test needed |

## Architecture

```
┌─────────────────────────────────────────────┐
│  WINDOWS SERVER (Hadley API :8100)          │
│                                             │
│  POST /voice/listen    audio → text         │
│  POST /voice/speak     text → audio         │
│  POST /voice/converse  audio → text + audio │
│                                             │
│  STT: faster-whisper (small.en, singleton)  │
│  TTS: Kokoro ONNX (bm_* voice, singleton)  │
└──────────────┬──────────────────────────────┘
               │
    ┌──────────┼──────────────┐
    │          │              │
 WhatsApp   Discord    Home Display
 (Phase 1)  (Phase 1)   (Phase 2)
```

---

## Phase 1: Voice API + WhatsApp Integration

### F1: Install dependencies and create voice engine module

**File**: `hadley_api/voice_engine.py` (new)

Install:
```
pip install faster-whisper kokoro-onnx
```

Create a singleton module that lazily loads both engines on first use:
- `transcribe(audio_bytes, format="ogg") -> str` — decode audio, run faster-whisper small.en
- `synthesise(text, voice="bm_george") -> bytes` — run Kokoro ONNX, return WAV bytes
- Models loaded once at first call, kept in memory
- Accept common formats: ogg/opus (WhatsApp), webm/opus (browser), wav

**Verify**: Unit test — pass a sample WAV through `transcribe()`, confirm text output. Pass text through `synthesise()`, confirm WAV bytes returned.

---

### F2: Voice API endpoints

**File**: `hadley_api/voice_routes.py` (new)
**Modify**: `hadley_api/main.py` (register router)

Three endpoints:

#### `POST /voice/listen`
- Request: audio file as body (Content-Type: audio/wav, audio/ogg, audio/webm)
- Response: `{ "text": "transcribed text" }`
- Calls `voice_engine.transcribe()`

#### `POST /voice/speak`
- Request: `{ "text": "...", "voice": "bm_george" }` (voice optional, has default)
- Response: audio/wav body
- Calls `voice_engine.synthesise()`

#### `POST /voice/converse`
- Request: audio file as body
- Pipeline: transcribe → route to Peter → synthesise response
- Response: `{ "text": "Peter's reply", "audio_url": "/voice/audio/<id>.wav" }`
- Text returned immediately; audio file served from temp directory
- Audio files cleaned up after 5 minutes (background task)
- Requires internal call to bot.py's Peter routing (reuse WhatsApp handler pattern on port 8101)

**Blocked by**: F1

**Verify**: curl test — POST a WAV file to `/voice/listen`, confirm JSON text response. POST text to `/voice/speak`, confirm WAV audio returned.

---

### F3: WhatsApp voice note handling — receive

**File**: `hadley_api/whatsapp_webhook.py` (modify)

Currently line 157-163 extracts only text, returns early if no text. Add audio message handling:

1. Detect audio message type in the Evolution API payload:
   - `message.audioMessage` field present → voice note
   - Contains `mediaUrl` or needs download via Evolution API media endpoint
2. Download the audio file (ogg/opus format)
3. Call `/voice/listen` internally (or `voice_engine.transcribe()` directly)
4. Inject transcribed text into the existing debounce queue with a `[Voice]` prefix tag
5. The rest of the pipeline (debounce → forward to bot.py) stays unchanged

**Blocked by**: F2

**Verify**: Send a voice note on WhatsApp → Peter receives it as text and responds with text.

---

### F4: WhatsApp voice note handling — respond with audio

**Files**:
- `integrations/whatsapp.py` (add `send_audio()`)
- `bot.py` WhatsApp handler (modify to optionally send audio reply)

1. Add `send_audio_sync()` / `send_audio()` to `integrations/whatsapp.py`:
   - Evolution API endpoint: `POST /message/sendWhatsAppAudio/{instance}`
   - Send audio as base64 or media URL
2. Modify bot.py `_whatsapp_handler` (line 191):
   - Accept new field `is_voice: bool` in the forwarded payload
   - If `is_voice`, after getting Peter's text response:
     - Call `voice_engine.synthesise()` to generate audio
     - Save to temp file
     - Send via `send_audio()` to WhatsApp
     - Also send the text reply (so the chat has both)

**Blocked by**: F3

**Verify**: Send a voice note on WhatsApp → Peter responds with both a text message and a voice note.

---

### F5: Voice selection — listen and choose

Before wiring everything together, test all 4 British male voices:
- Write a quick test script that synthesises the same phrase with `bm_daniel`, `bm_fable`, `bm_george`, `bm_lewis`
- Output 4 WAV files for Chris to listen to
- Set the chosen voice as the default in `voice_engine.py`

**Blocked by**: F1

**Verify**: Chris listens and picks a voice.

---

### F6: Documentation

**Files**:
- `hadley_api/README.md` — add Voice API endpoints
- `domains/peterbot/wsl_config/CLAUDE.md` — mention Peter can handle voice notes on WhatsApp

**Blocked by**: F4

---

## Phase 2: Home Display (Future — Specced Out)

### Architecture

The Pi 5 runs Chromium in kiosk mode, serving a web app from Hadley API. The browser handles mic capture and audio playback. All STT/TTS runs on the Windows server via the Phase 1 Voice API.

```
┌─────────────────────────────────────────────┐
│  PI 5 — Chromium Kiosk                      │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │  Web App (served from Hadley API)   │    │
│  │                                     │    │
│  │  [Push-to-Talk Button]              │    │
│  │  MediaRecorder → POST /voice/converse│   │
│  │  ← text displayed + audio played    │    │
│  │                                     │    │
│  │  [Wake Word: "Peter"]               │    │
│  │  Silero VAD (ONNX Web, ~2MB)        │    │
│  │  Continuous mic → detect speech     │    │
│  │  → STT → check "Peter" prefix      │    │
│  │  → if yes, route as conversation    │    │
│  │                                     │    │
│  │  Chat log (scrolling text)          │    │
│  │  Waveform visualiser (speaking)     │    │
│  │  Status indicator (listening/thinking│)   │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

### Display Tasks (not yet scheduled)

#### D1: Static web app shell
- Single HTML + JS file served by Hadley API as static file
- Chromium kiosk mode config for Pi autostart
- Full-screen layout: Peter avatar/status, chat log, mic button
- Responsive for 13.3" 1920x1080 touch

#### D2: Push-to-talk
- Tap mic button → MediaRecorder captures audio (opus/webm)
- On release → POST to `/voice/converse`
- Display text response immediately
- Play audio response via AudioContext
- Visual states: idle → recording → thinking → speaking

#### D3: Wake word ("Peter")
- Silero VAD running in browser via ONNX Web (~2MB model)
- Continuous mic monitoring (low CPU — VAD only, not full STT)
- When speech detected:
  - Capture segment
  - POST to `/voice/listen` (quick STT check)
  - If result starts with "Peter" → strip prefix, route to `/voice/converse`
  - If not → discard (wasn't talking to Peter)
- Visual indicator when wake word detected (Peter "wakes up")

#### D4: Ambient display features
- When not in conversation, show useful info (time, weather, calendar)
- Screen dims when PIR motion sensor detects no movement (via Pi GPIO → local API)
- BH1750 light sensor adjusts brightness
- These are bonus features, not blocking the voice pipeline

### Pi Setup Notes

- Chromium autostart: `~/.config/autostart/peter-display.desktop`
- Kiosk flags: `--kiosk --autoplay-policy=no-user-gesture-required --use-fake-ui-for-media-stream`
- `--use-fake-ui-for-media-stream` auto-grants mic permission
- Pi connects to Windows box over LAN (needs static IP or mDNS hostname)
- Audio output: 3.5mm jack or USB speaker
- Mic: USB mic or USB conference speaker (combined mic+speaker ideal for kitchen)

### Latency Budget (Home Display)

| Step | Target |
|------|--------|
| Audio capture + LAN transfer | ~100ms |
| STT (faster-whisper small.en) | ~500ms |
| Peter response (Claude Code) | ~1-2s |
| TTS (Kokoro) | ~300ms |
| Audio return + playback start | ~100ms |
| **Total** | **~2-3s** |

---

## Dependency Graph

```
Phase 1:
  F1 (voice engine) ──→ F2 (API endpoints) ──→ F3 (WA receive) ──→ F4 (WA respond) ──→ F6 (docs)
  F1 ──→ F5 (voice selection)

Phase 2 (future):
  F2 ──→ D1 (web shell) ──→ D2 (push-to-talk) ──→ D3 (wake word)
                                                  ──→ D4 (ambient)
```

## Files Changed (Phase 1)

| File | Action |
|------|--------|
| `hadley_api/voice_engine.py` | **New** — STT + TTS singleton module |
| `hadley_api/voice_routes.py` | **New** — `/voice/*` API endpoints |
| `hadley_api/main.py` | **Modify** — register voice router |
| `hadley_api/whatsapp_webhook.py` | **Modify** — handle audio messages |
| `integrations/whatsapp.py` | **Modify** — add `send_audio()` |
| `bot.py` | **Modify** — voice flag in WhatsApp handler |
| `hadley_api/README.md` | **Modify** — document voice endpoints |
| `domains/peterbot/wsl_config/CLAUDE.md` | **Modify** — mention voice capability |

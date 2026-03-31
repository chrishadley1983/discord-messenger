# Peter Voice -- Desktop Voice Client

## Overview

Standalone Windows system tray app adding voice I/O to Peter. Runs in a separate Python 3.13 venv because kokoro-onnx does not support Python 3.14. The source files are local-only (not committed to git) -- only the `.gitignore` is tracked.

## Architecture

```
Microphone -> sounddevice -> Moonshine STT -> Discord Webhook ("Chris (Voice)")
                                                      |
                                                Peter (bot.py)
                                                      |
                                REST API polling <- Discord API -> TTS (Kokoro) -> Speakers
```

## Components

| File | Purpose |
|------|---------|
| `peter_voice.pyw` | Main entry point (`.pyw` = no console window) |
| `config.py` | Config from parent `.env` + local `config.json` |
| `audio.py` | Microphone capture (16kHz mono float32) |
| `stt.py` | Moonshine ONNX speech-to-text |
| `tts.py` | Kokoro ONNX text-to-speech |
| `discord_comms.py` | Webhook send + REST API reply polling |
| `hotkey.py` | Global hotkeys (Ctrl+Space PTT, Ctrl+Shift+Space mode toggle) |
| `wake.py` | silero-vad wake word detection |
| `sounds.py` | Programmatic audio feedback tones |
| `tray.py` | System tray icon + menu (pystray) |

## Modes

| Mode | Trigger | Behaviour |
|------|---------|-----------|
| PTT | Ctrl+Space (hold) | Record while held, transcribe on release |
| Wake Word | Say "Peter, ..." | Continuous VAD listening, transcribe on speech end |
| Muted | Tray menu | No input, no output |

## Key Design Decisions

- **Separate venv (Python 3.13)** -- heavy ML dependencies (torch, onnxruntime) isolated from the bot's Python 3.14 environment.
- **REST polling for replies** -- NOT the Discord gateway (would conflict with bot.py's single-token gateway connection).
- **Webhook sends as "Chris (Voice)"** -- Peter sees these as normal text messages, no special handling required.
- **float32 audio throughout** -- both Moonshine and silero-vad expect float32 at 16kHz.
- **Models dir gitignored** (~450MB): `kokoro-v1.0.onnx` + `voices-v1.0.bin`.
- **Source files not committed** -- only `.gitignore` is tracked. Files live locally at `peter-voice/`.

## Setup

```powershell
cd peter-voice
powershell -ExecutionPolicy Bypass -File setup.ps1
```

This creates the Python 3.13 venv and installs all dependencies.

## Voice Options

Available TTS voices (all British male):

| Voice ID | Name |
|----------|------|
| `bm_daniel` | Daniel (default) |
| `bm_fable` | Fable |
| `bm_george` | George |
| `bm_lewis` | Lewis |

## Logs

Location: `%LOCALAPPDATA%\peter-voice\logs\`

## Gitignored Content

The following are present locally but excluded from version control:

- `.venv/` -- Python 3.13 virtual environment
- `models/` -- Kokoro ONNX models (~450MB)
- `__pycache__/`, `*.pyc` -- Python cache
- `*.log` -- Log files (stored in `%LOCALAPPDATA%`)

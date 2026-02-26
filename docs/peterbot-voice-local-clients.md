# Peterbot Voice — Local Voice Clients

**Date:** February 2026
**Status:** Research / Pre-Spec
**Author:** Claude (for Chris Hadley)
**Supersedes:** peterbot-voice-discord.md (voice channel approach — abandoned in favour of this)

---

## 1. The Core Idea

Peter stays a text bot. Voice is a thin client-side wrapper on each device.

```
┌──────────────────────────────────────────────────────┐
│                    YOUR DEVICES                       │
│                                                       │
│  ┌─────────────────┐       ┌──────────────────────┐  │
│  │  Windows Desktop │       │  Android Phone       │  │
│  │                  │       │                      │  │
│  │  Mic → Moonshine │       │  Mic → Android STT   │  │
│  │  (local STT)     │       │  (built-in)          │  │
│  │       ↓          │       │       ↓              │  │
│  │  Text message     │       │  Text message        │  │
│  │       ↓          │       │       ↓              │  │
│  │  Discord API ─────┼───────┼── Discord API        │  │
│  │       ↓          │       │       ↓              │  │
│  │  Watch for reply  │       │  Watch for reply     │  │
│  │       ↓          │       │       ↓              │  │
│  │  Kokoro → Speaker │       │  Android TTS → Speaker│  │
│  │  (local TTS)     │       │  (built-in)          │  │
│  └─────────────────┘       └──────────────────────┘  │
└──────────────────────────────────────────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  Peter (unchanged)   │
              │                     │
              │  Sees text messages  │
              │  Sends text replies  │
              │  Doesn't know or    │
              │  care about voice   │
              └─────────────────────┘
```

**Why this is better than the Discord voice channel approach:**

- Peter doesn't change at all — no new dependencies, no voice protocol handling
- Works on any device independently — desktop and phone don't need to coordinate
- No Discord voice channel to join/manage
- Ctrl+Space works natively on Windows (it's just a local hotkey)
- Wake word works locally too — no audio leaving your machine until it's text
- Phone uses Android's built-in STT/TTS which are excellent and free
- If Moonshine or Kokoro break, Peter still works perfectly via text as it always has

---

## 2. Desktop Voice Client — Windows System Tray App

### What It Does

A Python app that lives in your system tray. Two activation modes you can toggle between:

1. **Push-to-talk (Ctrl+Space)** — press to start listening, release to stop, transcribe, send
2. **Wake word ("Peter")** — always listening, only activates when it hears "Peter"

When Peter replies in Discord, the app intercepts the response and speaks it through your speakers via Kokoro.

### Architecture

```
┌──────────────────────────────────────────────────────┐
│              peter-voice.pyw (system tray)             │
│                                                        │
│  ┌────────────┐  ┌────────────┐  ┌─────────────────┐ │
│  │ Tray Icon   │  │ Hotkey     │  │ Discord Watcher │ │
│  │ pystray     │  │ Listener   │  │ (bot or webhook)│ │
│  │             │  │ pynput     │  │                 │ │
│  │ • PTT mode  │  │            │  │ Watches for     │ │
│  │ • Wake mode │  │ Ctrl+Space │  │ Peter's replies │ │
│  │ • Mute      │  │ detected → │  │ in #peterbot    │ │
│  │ • Quit      │  │ start mic  │  │                 │ │
│  └──────┬─────┘  └─────┬──────┘  └────────┬────────┘ │
│         │              │                    │          │
│         │    ┌─────────▼──────────┐        │          │
│         │    │ Audio Capture      │        │          │
│         │    │ sounddevice / pyaudio│       │          │
│         │    │ 16kHz mono PCM     │        │          │
│         │    └─────────┬──────────┘        │          │
│         │              │                    │          │
│         │    ┌─────────▼──────────┐        │          │
│         │    │ Moonshine STT      │  ┌─────▼────────┐ │
│         │    │ (local, CPU)       │  │ Kokoro TTS   │ │
│         │    │ Audio → Text       │  │ (local, CPU) │ │
│         │    └─────────┬──────────┘  │ Text → Audio │ │
│         │              │              └─────┬────────┘ │
│         │    ┌─────────▼──────────┐        │          │
│         │    │ Discord API        │  ┌─────▼────────┐ │
│         │    │ Send message to    │  │ Speaker      │ │
│         │    │ #peterbot          │  │ sounddevice  │ │
│         │    └────────────────────┘  └──────────────┘ │
└──────────────────────────────────────────────────────┘
```

### Tech Stack

| Component | Library | Why |
|-----------|---------|-----|
| System tray | `pystray` + `Pillow` | Native Windows tray icon, right-click menu |
| Global hotkey | `pynput` | Captures Ctrl+Space even when app isn't focused |
| Mic capture | `sounddevice` | Clean Python audio I/O, no ffmpeg needed |
| STT | `moonshine-onnx` | 62M params, runs on CPU, 5× faster than Whisper |
| TTS | `kokoro-onnx` | 82M params, runs on CPU, near-commercial quality |
| Speaker output | `sounddevice` | Direct PCM playback, no temp files |
| Discord comms | `discord.py` (bot) or `aiohttp` (webhook) | Send messages, watch for replies |
| VAD (wake mode) | `silero-vad` | Accurate speech boundary detection |
| Config | `json` file | Persist mode choice, voice selection, hotkey |

### Activation Modes

#### Push-to-Talk (Ctrl+Space)

```
Ctrl+Space pressed
    → Start capturing mic audio (16kHz mono)
    → Tray icon changes to 🔴 (recording)
    → Optional: play subtle "boop" sound

Ctrl+Space released (or after 30s timeout)
    → Stop capturing
    → Tray icon changes to ⏳ (processing)
    → Moonshine transcribes audio → text
    → Send text to #peterbot as Discord message
    → Tray icon back to normal

Peter replies in #peterbot
    → Kokoro synthesises reply → audio
    → Play through speakers
    → Tray icon shows 🔊 briefly
```

No wake word needed. Everything you say between press and release is transcribed and sent. Clean, precise, zero false positives.

#### Wake Word ("Peter")

```
Always capturing mic in small chunks (VAD running)
    → Tray icon shows 👂 (listening)

VAD detects speech → buffer audio
VAD detects silence (1.5s) → transcribe buffered audio
    → If starts with "Peter": strip wake word, send to #peterbot
    → If doesn't start with "Peter": discard, continue listening

Peter replies in #peterbot
    → Same as PTT: Kokoro → speakers
```

Hands-free. Good for when you're away from keyboard — cooking, tidying, etc.

#### Toggle Between Modes

Right-click tray icon:
- ◉ Push-to-talk (Ctrl+Space)
- ○ Wake word ("Peter")
- ─────────
- 🔇 Mute (disable voice entirely)
- ⚙️ Settings...
- ✕ Quit

Or a hotkey to toggle: `Ctrl+Shift+Space` flips between modes.

### Discord Communication

Two options for how the desktop client talks to Peter:

**Option A: Lightweight bot token (recommended)**

The voice client logs into Discord as a second bot (or uses Peter's existing token in read-only mode). It sends messages as "you" by using a Discord user token or webhook, and watches Peter's replies.

Actually simpler: **use a webhook to send, and a bot connection to watch for replies.**

```python
# Send your spoken text to #peterbot via webhook
async def send_to_peter(text):
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
        await webhook.send(text, username="Chris (Voice)")

# Watch for Peter's replies
@bot.event
async def on_message(message):
    if message.author.id == PETER_BOT_ID and message.channel.id == PETERBOT_CHANNEL_ID:
        await speak_response(message.content)
```

This way your voice messages show up in Discord as "Chris (Voice)" so you can see the full conversation history in text, and Peter replies normally.

**Option B: Direct API (no second bot)**

Use the Discord HTTP API directly with your user token. Simpler but technically against Discord ToS for user accounts (bot tokens are fine). The webhook approach avoids this entirely.

### Voice Feedback

The app should give audio cues so you know what's happening:

| Event | Sound |
|-------|-------|
| PTT activated | Subtle rising tone (like Teams unmute) |
| PTT deactivated / processing | Subtle falling tone |
| Wake word detected | Short confirmation beep |
| Error (mic not found, Discord down) | Different tone + tray notification |

These should be short WAV files played via `sounddevice`, not TTS. Keep them under 200ms.

### Sample Implementation

```python
"""peter_voice.pyw — Peterbot voice client for Windows"""

import asyncio
import threading
import json
import numpy as np
import sounddevice as sd
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw
from pynput import keyboard
import moonshine_onnx
from kokoro_onnx import Kokoro
import aiohttp
import discord

# ── Config ──────────────────────────────────────────────
CONFIG = {
    "mode": "ptt",            # "ptt" or "wake"
    "hotkey": "ctrl+space",
    "wake_word": "peter",
    "voice": "am_adam",
    "speed": 1.0,
    "webhook_url": "https://discord.com/api/webhooks/...",
    "bot_token": "...",       # for watching Peter's replies
    "peter_bot_id": 123456,
    "channel_id": 789012,
    "sample_rate": 16000,
    "silence_timeout": 1.5,   # seconds of silence before processing
}

# ── Models (loaded once, stay resident) ─────────────────
kokoro = Kokoro("models/kokoro-v1.0.onnx", "models/voices-v1.0.bin")
# Moonshine loads on first transcribe call


# ── Audio Capture ───────────────────────────────────────
class AudioCapture:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.buffer = []
        self.is_recording = False
        self.stream = None

    def start(self):
        self.buffer = []
        self.is_recording = True
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype='int16',
            callback=self._callback
        )
        self.stream.start()

    def stop(self):
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        audio = np.concatenate(self.buffer) if self.buffer else np.array([], dtype=np.int16)
        self.buffer = []
        return audio

    def _callback(self, indata, frames, time, status):
        if self.is_recording:
            self.buffer.append(indata[:, 0].copy())


# ── STT ─────────────────────────────────────────────────
def transcribe(audio_np):
    """Transcribe 16kHz int16 numpy array to text."""
    # Moonshine expects float32 normalised to [-1, 1]
    audio_float = audio_np.astype(np.float32) / 32768.0
    result = moonshine_onnx.transcribe(audio_float, "moonshine/base")
    return result[0] if result else ""


# ── TTS ─────────────────────────────────────────────────
def speak(text):
    """Synthesise text and play through speakers."""
    clean = strip_for_speech(text)
    if not clean:
        return
    samples, sr = kokoro.create(clean, voice=CONFIG["voice"], speed=CONFIG["speed"])
    sd.play(samples, sr)
    sd.wait()  # block until playback finishes


def strip_for_speech(text):
    """Remove markdown, code blocks, URLs for natural speech."""
    import re
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[*_~#]', '', text)
    text = re.sub(r'\n+', '. ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ── Discord ─────────────────────────────────────────────
async def send_to_peter(text):
    """Send transcribed text to #peterbot via webhook."""
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(CONFIG["webhook_url"], session=session)
        await webhook.send(text, username="Chris (Voice)")


class ReplyWatcher(discord.Client):
    """Minimal Discord client that watches for Peter's replies."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

    async def on_message(self, message):
        if (message.author.id == CONFIG["peter_bot_id"]
                and message.channel.id == CONFIG["channel_id"]):
            # Run TTS in thread to avoid blocking
            threading.Thread(target=speak, args=(message.content,)).start()


# ── Hotkey Listener ─────────────────────────────────────
class HotkeyManager:
    def __init__(self, audio_capture, on_utterance):
        self.audio = audio_capture
        self.on_utterance = on_utterance
        self.ctrl_held = False
        self.space_held = False
        self.recording = False

    def on_press(self, key):
        if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
            self.ctrl_held = True
        elif key == keyboard.Key.space and self.ctrl_held and not self.recording:
            self.recording = True
            self.audio.start()

    def on_release(self, key):
        if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
            self.ctrl_held = False
            if self.recording:
                self._finish_recording()
        elif key == keyboard.Key.space and self.recording and not self.ctrl_held:
            self._finish_recording()

    def _finish_recording(self):
        self.recording = False
        audio = self.audio.stop()
        if len(audio) > 0:
            threading.Thread(target=self._process, args=(audio,)).start()

    def _process(self, audio):
        text = transcribe(audio)
        if text.strip():
            self.on_utterance(text)


# ── System Tray ─────────────────────────────────────────
def create_tray_icon():
    """Create a simple coloured circle as tray icon."""
    img = Image.new('RGB', (64, 64), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, 56, 56], fill='#5865F2')  # Discord blue
    return img


def build_tray(toggle_mode_fn, quit_fn):
    menu = Menu(
        MenuItem('Push-to-talk (Ctrl+Space)',
                 lambda: toggle_mode_fn('ptt'),
                 checked=lambda item: CONFIG['mode'] == 'ptt'),
        MenuItem('Wake word ("Peter")',
                 lambda: toggle_mode_fn('wake'),
                 checked=lambda item: CONFIG['mode'] == 'wake'),
        Menu.SEPARATOR,
        MenuItem('Quit', quit_fn),
    )
    return Icon("Peter Voice", create_tray_icon(), "Peter Voice", menu)


# ── Main ────────────────────────────────────────────────
def main():
    audio_capture = AudioCapture(CONFIG["sample_rate"])

    def on_utterance(text):
        """Called when speech is transcribed."""
        # In wake mode, check for wake word
        if CONFIG["mode"] == "wake":
            if not text.lower().startswith(CONFIG["wake_word"]):
                return
            text = text[len(CONFIG["wake_word"]):].strip().lstrip(",").strip()
            if not text:
                return

        print(f"Sending to Peter: {text}")
        asyncio.run_coroutine_threadsafe(
            send_to_peter(text), discord_loop
        )

    def toggle_mode(mode):
        CONFIG["mode"] = mode
        print(f"Switched to {mode} mode")

    def quit_app(icon):
        icon.stop()
        watcher.close()

    # Hotkey listener
    hotkey_mgr = HotkeyManager(audio_capture, on_utterance)
    key_listener = keyboard.Listener(
        on_press=hotkey_mgr.on_press,
        on_release=hotkey_mgr.on_release
    )
    key_listener.start()

    # Discord reply watcher (runs in background thread)
    watcher = ReplyWatcher()
    discord_loop = asyncio.new_event_loop()
    discord_thread = threading.Thread(
        target=lambda: discord_loop.run_until_complete(
            watcher.start(CONFIG["bot_token"])
        ),
        daemon=True
    )
    discord_thread.start()

    # System tray (blocks main thread)
    tray = build_tray(toggle_mode, quit_app)
    tray.run()


if __name__ == "__main__":
    main()
```

### File Structure

```
peter-voice/
├── peter_voice.pyw          # main app (.pyw = no console window)
├── config.json              # user config (webhook URL, bot token, etc.)
├── models/
│   ├── kokoro-v1.0.onnx     # ~400MB, download once
│   └── voices-v1.0.bin      # ~50MB, download once
├── sounds/
│   ├── activate.wav          # PTT on sound
│   └── deactivate.wav        # PTT off sound
├── icon.ico                  # tray icon
└── requirements.txt
```

### Requirements

```
# requirements.txt
kokoro-onnx
moonshine-onnx
sounddevice
pystray
Pillow
pynput
discord.py
aiohttp
numpy
torch          # for silero-vad (wake word mode only)
```

### Windows Setup

```powershell
# One-time setup
python -m venv peter-voice-env
peter-voice-env\Scripts\activate

pip install -r requirements.txt

# Install espeak-ng (Kokoro dependency)
# Download from https://github.com/espeak-ng/espeak-ng/releases
# Or: winget install espeak-ng

# Download models
mkdir models
cd models
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v1.0.onnx
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices-v1.0.bin

# Run
pythonw peter_voice.pyw
```

### Auto-Start with Windows

Add a shortcut to `peter_voice.pyw` in:
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```

Or use Task Scheduler for more control (run at login, run as background process).

---

## 3. Phone Voice Client — Android via Tasker

On the phone, you don't need Moonshine or Kokoro at all. Android has excellent built-in STT (Google Speech Recognition) and TTS (Google TTS) that are free, fast, and handle punctuation properly.

### How It Works

```
You speak into phone
    → Android STT transcribes (Google, on-device)
    → Tasker sends text to Peter via Discord webhook
    → Tasker watches for Peter's reply (via webhook or polling)
    → Android TTS reads reply aloud
```

### Activation Options

| Method | How | Best For |
|--------|-----|----------|
| AutoVoice "Peter" | Wake word via AutoVoice Tasker plugin | Hands-free, around the house |
| Widget button | Tasker widget on home screen | Quick one-tap activation |
| Android Auto | Voice command in car | Driving |
| Notification action | Persistent notification with mic button | Quick access from any screen |

### Tasker Setup (High Level)

This is covered in more detail in the existing Tasker spec (`tasker-voice-spec.md`), but the key tasks are:

**Task: "Ask Peter"**
1. Voice Recognition → `%speech`
2. HTTP Request POST to Discord webhook with `%speech` as content
3. Wait for Peter's reply (poll channel or use a return webhook)
4. Say `%reply` (Android TTS)

**Profile: "Peter Wake Word"**
- Trigger: AutoVoice Recognized → "Peter"
- Action: Run "Ask Peter" task

**Profile: "Peter in Car"**
- Trigger: Android Auto connected
- Action: Enable "Peter Wake Word" profile

The webhook URL is the same one the desktop client uses. Peter sees messages from both "Chris (Voice)" on desktop and "Chris (Phone)" on mobile — same channel, same conversation history.

---

## 4. How Peter's Replies Get Back

This is the one piece that needs thought. Sending TO Peter is easy (webhook). Getting Peter's reply back to the voice client requires the client to know when Peter has responded.

### Option A: Discord Bot Listener (Desktop — Recommended)

The desktop app runs a lightweight Discord bot that watches #peterbot for messages from Peter's bot ID. When one arrives, it speaks it. This is what the sample code above does.

Downside: requires a bot token and a persistent websocket connection.

### Option B: Polling (Phone — Simplest)

After sending a message, poll the Discord channel API every 500ms for up to 30 seconds waiting for Peter's reply. Simple, works in Tasker.

```
Send message → Start polling → Peter replies → Speak reply → Stop polling
```

### Option C: Return Webhook (Both — Cleanest)

Modify Peter to POST responses to a webhook endpoint as well as sending them to Discord. The desktop app and phone app each run a tiny HTTP listener.

This would mean a small change to Peter — after sending a Discord reply, also POST to a configured webhook URL. But it gives instant notification with no polling and no bot token.

### Option D: Tag Voice Messages

Send messages with a special prefix like `🎤 What's on my calendar?` and have Peter tag voice responses with `🔊` so the client can filter. Not necessary but useful for distinguishing voice vs typed messages in the channel history.

---

## 5. Moonshine & Kokoro — Quick Reference

### Moonshine (STT — Desktop Only)

| Spec | Value |
|------|-------|
| Model | Moonshine Base |
| Parameters | 62M |
| Size on disk | ~400MB (ONNX) |
| Input | 16kHz mono audio |
| Output | Lowercase English text, no punctuation |
| Speed | 5-15× faster than Whisper on short audio |
| Accuracy | Matches or beats Whisper base.en |
| License | MIT |
| Runs on | Any CPU, no GPU needed |

**Limitation:** No punctuation or capitalisation. For voice commands to Peter this doesn't matter — the router handles messy input fine. If it becomes annoying, a small punctuation restoration model can be added later.

### Kokoro (TTS — Desktop Only)

| Spec | Value |
|------|-------|
| Model | Kokoro v1.0 |
| Parameters | 82M |
| Size on disk | ~450MB (ONNX model + voices) |
| Output | 24kHz audio |
| Voices | 14+ (American, British, male, female) |
| Speed | Sub-300ms for typical Peterbot responses |
| Quality | Near-commercial, natural sounding |
| License | Apache 2.0 |
| Runs on | Any CPU, no GPU needed |

**Recommended voice for Peter:** `am_adam` (conversational American) or `bm_george` (British male). Test both.

---

## 6. Latency Budget

### Desktop (PTT Mode)

| Step | Time |
|------|------|
| You release Ctrl+Space | 0ms |
| Moonshine transcribes | ~100-200ms |
| Send to Discord webhook | ~50-100ms |
| Peter processes + responds | 200-2000ms (varies by domain) |
| Discord delivers reply to bot listener | ~50-100ms |
| Kokoro synthesises | ~200-500ms |
| Audio starts playing | ~10ms |
| **Total** | **~0.6-3.0s** |

For simple queries (time, status), under 1 second. For Claude API queries, 2-3 seconds. Both feel natural and conversational.

### Phone (Tasker)

| Step | Time |
|------|------|
| Android STT | ~300-500ms |
| Send to Discord webhook | ~100-200ms |
| Peter processes + responds | 200-2000ms |
| Poll detects reply | ~500ms (worst case) |
| Android TTS | ~200-400ms |
| **Total** | **~1.3-3.6s** |

Slightly slower due to polling, but still feels responsive.

---

## 7. Implementation Plan

### Phase 1: Desktop TTS Only (One Evening)

Peter speaks but you still type. Just add voice output to existing text workflow.

1. Install Kokoro on your machine
2. Test voices, pick Peter's voice
3. Build minimal tray app that watches #peterbot for Peter's replies
4. When Peter replies, speak it through speakers
5. Tray icon shows when Peter is speaking

**Success:** Type in Discord, hear Peter respond through speakers.

### Phase 2: Desktop STT — Push-to-Talk (One Evening)

Add Ctrl+Space input.

1. Install Moonshine
2. Add hotkey listener and mic capture
3. Ctrl+Space → record → transcribe → send to #peterbot via webhook
4. Full loop working: speak → text → Peter → text → speak

**Success:** Ctrl+Space, say "What's on my calendar today", hear Peter read your calendar.

### Phase 3: Wake Word Mode (Quick Addition)

Add "Peter" wake word as alternative activation.

1. Add silero-vad for continuous listening
2. Add wake word detection on transcribed text
3. Toggle between PTT and wake word via tray menu

**Success:** Say "Peter, what time is it?" without touching keyboard.

### Phase 4: Phone via Tasker (Separate Track)

1. Set up Discord webhook (same one desktop uses)
2. Create Tasker voice recognition task
3. Add reply polling or return webhook
4. Test full loop on phone

**Success:** Say "Peter, add milk to the shopping list" on phone.

### Phase 5: Polish

- Audio feedback sounds (PTT on/off beeps)
- Response length gating (long responses → "Check Discord for the full answer")
- Error handling (mic not found, Discord down, model failed)
- Config file for voice, speed, hotkey, webhook URL
- Windows startup integration

---

## 8. What Peter Doesn't Need to Change

This is the beauty of the approach. Peter's codebase needs zero modifications for Phase 1-3. It just sees text messages and sends text replies.

The only optional Peter-side change is for the return webhook (Option C in section 4), which would give faster response delivery. But polling or bot-listener work without touching Peter at all.

---

## 9. Reference Links

- Kokoro ONNX: https://github.com/thewh1teagle/kokoro-onnx
- Kokoro model: https://huggingface.co/hexgrad/Kokoro-82M
- Moonshine: https://github.com/moonshine-ai/moonshine
- pystray: https://github.com/moses-palmer/pystray
- pynput: https://github.com/moses-palmer/pynput
- sounddevice: https://python-sounddevice.readthedocs.io
- silero-vad: https://github.com/snakers4/silero-vad
- Existing Tasker spec: tasker-voice-spec.md

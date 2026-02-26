"""Peter Voice Desktop Client — Main Entry Point.

System tray app that adds voice I/O to Peter (Discord bot).
Voice in via Moonshine STT, voice out via Kokoro TTS,
Discord webhook for sending, REST API polling for replies.

Threading model:
  Main thread:  pystray Icon.run() (blocks)
  Thread 1:     asyncio event loop (polling + sends)
  Thread 2:     pynput keyboard listener (global hotkeys)
  Thread 3:     sounddevice wake word listener (when in wake mode)
  Temp threads: TTS playback, STT transcription
"""

import asyncio
import logging
import sys
import threading
from enum import Enum
from pathlib import Path

# Ensure peter-voice is on the path
sys.path.insert(0, str(Path(__file__).parent))

from config import LOG_DIR, MODE, VOICE_REPLIES_ONLY
from audio import AudioCapture
from stt import transcribe
from tts import speak, stop_speaking
from discord_comms import discover_bot_user_id, send_to_peter, ReplyPoller
from hotkey import HotkeyManager
from wake import WakeWordListener
from sounds import play_activate, play_deactivate, play_wake_detected, play_error
from tray import VoiceTray, TrayState

import aiohttp

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "peter_voice.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("peter_voice")


# ---------------------------------------------------------------------------
# State Machine
# ---------------------------------------------------------------------------

class State(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    SENDING = "sending"
    WAITING = "waiting"
    SPEAKING = "speaking"


class PeterVoice:
    """Orchestrates all modules."""

    def __init__(self):
        self._state = State.IDLE
        self._mode = MODE  # "ptt" or "wake" or "muted"
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session: aiohttp.ClientSession | None = None

        # Modules
        self._audio = AudioCapture()
        self._poller = ReplyPoller()
        self._wake = WakeWordListener(on_utterance=self._on_wake_utterance)
        self._hotkeys = HotkeyManager(
            on_ptt_start=self._on_ptt_start,
            on_ptt_stop=self._on_ptt_stop,
            on_mode_toggle=self._on_mode_toggle,
        )
        self._tray = VoiceTray(
            on_mode_change=self._on_tray_mode_change,
            on_quit=self._shutdown,
        )

        self._shutting_down = False

    # ------- State transitions -------

    def _set_state(self, state: State) -> None:
        self._state = state
        log.debug("State → %s", state.value)
        # Map app state to tray state
        tray_map = {
            State.IDLE: TrayState.WAKE if self._mode == "wake" else TrayState.IDLE,
            State.RECORDING: TrayState.RECORDING,
            State.TRANSCRIBING: TrayState.PROCESSING,
            State.SENDING: TrayState.PROCESSING,
            State.WAITING: TrayState.PROCESSING,
            State.SPEAKING: TrayState.SPEAKING,
        }
        self._tray.update_state(tray_map.get(state, TrayState.IDLE))

    # ------- PTT callbacks (from hotkey thread) -------

    def _on_ptt_start(self) -> None:
        if self._mode != "ptt" or self._state != State.IDLE:
            return
        play_activate()
        self._audio.start()
        self._set_state(State.RECORDING)

    def _on_ptt_stop(self) -> None:
        if self._state != State.RECORDING:
            return
        audio = self._audio.stop()
        play_deactivate()
        self._set_state(State.TRANSCRIBING)

        # Transcribe + send in background
        threading.Thread(
            target=self._handle_ptt_audio,
            args=(audio,),
            daemon=True,
        ).start()

    def _handle_ptt_audio(self, audio) -> None:
        """Transcribe PTT audio and send to Peter."""
        try:
            text = transcribe(audio)
            if not text:
                log.info("No speech detected in PTT audio")
                self._set_state(State.IDLE)
                return

            log.info("PTT transcribed: %s", text)
            self._set_state(State.SENDING)
            self._run_async(self._send_and_wait(text))
        except Exception as e:
            log.error("PTT processing error: %s", e)
            play_error()
            self._tray.notify("Peter Voice Error", str(e))
            self._set_state(State.IDLE)

    # ------- Wake word callback (from wake listener thread) -------

    def _on_wake_utterance(self, text: str) -> None:
        """Called by WakeWordListener when wake word + command detected."""
        if self._state != State.IDLE or self._mode != "wake":
            return

        play_wake_detected()
        log.info("Wake utterance: %s", text)
        self._set_state(State.SENDING)
        self._run_async(self._send_and_wait(text))

    # ------- Async operations -------

    def _run_async(self, coro) -> None:
        """Schedule a coroutine on the asyncio loop from any thread."""
        if self._loop:
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def _send_and_wait(self, text: str) -> None:
        """Send message to Peter and activate polling for reply."""
        try:
            await send_to_peter(self._session, text)
            self._poller.activate()
            self._set_state(State.WAITING)
        except Exception as e:
            log.error("Send failed: %s", e)
            play_error()
            self._tray.notify("Send Failed", str(e))
            self._set_state(State.IDLE)

    async def _on_peter_reply(self, text: str, is_active: bool) -> None:
        """Called when poller detects a new message from Peter."""
        if self._shutting_down:
            return

        # When voice_replies_only is on, skip TTS for idle-detected messages
        if VOICE_REPLIES_ONLY and not is_active:
            log.info("Skipping TTS for idle reply (voice_replies_only=true)")
            return

        self._set_state(State.SPEAKING)
        # Run TTS in a thread to avoid blocking the event loop
        await asyncio.get_event_loop().run_in_executor(
            None, speak, text
        )
        self._set_state(State.IDLE)

    async def _on_poll_timeout(self) -> None:
        """Called when active polling expires without a reply."""
        if self._state == State.WAITING:
            log.info("Poll timeout — returning to idle")
            self._set_state(State.IDLE)

    # ------- Mode switching -------

    def _on_mode_toggle(self) -> None:
        """Hotkey: toggle between PTT and wake mode."""
        if self._mode == "ptt":
            self._switch_mode("wake")
        elif self._mode == "wake":
            self._switch_mode("ptt")
        else:
            self._switch_mode("ptt")

    def _on_tray_mode_change(self, mode: str) -> None:
        """Tray menu mode selection."""
        self._switch_mode(mode)

    def _switch_mode(self, mode: str) -> None:
        """Switch between ptt/wake/muted modes."""
        old_mode = self._mode
        self._mode = mode
        log.info("Mode: %s → %s", old_mode, mode)

        # Stop recording if switching away
        if self._state == State.RECORDING:
            self._audio.stop()

        # Manage wake listener
        if old_mode == "wake" and mode != "wake":
            self._wake.stop()
        elif mode == "wake" and old_mode != "wake":
            self._wake.start()

        if mode == "muted":
            stop_speaking()
            self._tray.update_state(TrayState.MUTED)
        elif mode == "wake":
            self._tray.update_state(TrayState.WAKE)
        else:
            self._tray.update_state(TrayState.IDLE)

        self._set_state(State.IDLE)

    # ------- Lifecycle -------

    async def _async_main(self) -> None:
        """Main async loop: connects session, starts poller."""
        async with aiohttp.ClientSession() as session:
            self._session = session

            # Discover bot user ID
            try:
                bot_user_id = await discover_bot_user_id(session)
            except Exception as e:
                log.error("Failed to discover bot user ID: %s", e)
                self._tray.notify("Peter Voice Error", f"Bot discovery failed: {e}")
                return

            # Start polling
            await self._poller.start(
                session, self._on_peter_reply, bot_user_id,
                on_timeout=self._on_poll_timeout,
            )

    def _run_async_loop(self) -> None:
        """Thread target: runs the asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_main())
        except Exception as e:
            if not self._shutting_down:
                log.error("Async loop error: %s", e)
        finally:
            self._loop.close()

    def _shutdown(self) -> None:
        """Clean shutdown of all components."""
        if self._shutting_down:
            return
        self._shutting_down = True
        log.info("Shutting down...")

        stop_speaking()
        self._audio.stop()
        self._hotkeys.stop()
        self._wake.stop()
        self._poller.stop()

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def run(self) -> None:
        """Start Peter Voice (blocks on tray icon)."""
        log.info("Peter Voice starting...")
        log.info("Mode: %s", self._mode)

        # Start async loop in background thread
        async_thread = threading.Thread(
            target=self._run_async_loop,
            daemon=True,
            name="async-loop",
        )
        async_thread.start()

        # Start hotkey listener
        self._hotkeys.start()

        # Start wake listener if in wake mode
        if self._mode == "wake":
            self._wake.start()

        # Log ready
        log.info("Peter Voice ready!")

        # Run tray icon (blocks main thread)
        self._tray.run()

        # If tray exits, clean up
        self._shutdown()


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        app = PeterVoice()
        app.run()
    except Exception as e:
        log.critical("Fatal error: %s", e, exc_info=True)
        sys.exit(1)

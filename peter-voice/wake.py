"""Wake word detection using silero-vad + Moonshine STT.

Continuously listens via sounddevice. When VAD detects speech, buffers it,
then transcribes and checks if it starts with the wake word ("peter").
"""

import logging
import threading

import numpy as np
import sounddevice as sd
import torch

from config import WAKE_WORD

log = logging.getLogger(__name__)

# VAD settings
SAMPLE_RATE = 16000
CHUNK_SIZE = 512  # silero-vad requires 512 samples at 16kHz
MAX_SPEECH_SECONDS = 15  # Max recording length
SILENCE_CHUNKS = 30  # ~1s of silence to end speech (30 * 32ms)


class WakeWordListener:
    """Listens for wake word using VAD + STT."""

    def __init__(self, on_utterance=None):
        """
        Args:
            on_utterance: async callable(text) — called with the speech after
                the wake word (e.g. "what's the weather" from "Peter, what's the weather").
        """
        self._on_utterance = on_utterance
        self._stream: sd.InputStream | None = None
        self._running = False
        self._vad_model = None
        self._vad_iterator = None

        # Speech buffering state
        self._speech_buffer: list[np.ndarray] = []
        self._is_speaking = False
        self._silence_count = 0

    def _load_vad(self):
        """Load silero-vad model (one-time)."""
        if self._vad_model is not None:
            return

        torch.set_num_threads(1)
        log.info("Loading silero-vad model...")
        self._vad_model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
        _, _, _, self._VADIterator, _ = utils
        self._vad_iterator = self._VADIterator(
            self._vad_model, sampling_rate=SAMPLE_RATE
        )
        log.info("silero-vad loaded")

    def start(self) -> None:
        """Start continuous listening."""
        self._load_vad()
        self._running = True
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=CHUNK_SIZE,
            callback=self._audio_callback,
        )
        self._stream.start()
        log.info("Wake word listener started")

    def stop(self) -> None:
        """Stop listening."""
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._reset_state()

    def _reset_state(self) -> None:
        self._speech_buffer.clear()
        self._is_speaking = False
        self._silence_count = 0
        if self._vad_iterator:
            self._vad_iterator.reset_states()

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """Process each audio chunk through VAD."""
        if not self._running:
            return

        chunk = indata[:, 0].copy()

        # Feed chunk to VAD
        tensor = torch.from_numpy(chunk)
        speech_dict = self._vad_iterator(tensor, return_seconds=True)

        if speech_dict:
            if "start" in speech_dict:
                self._is_speaking = True
                self._silence_count = 0
                self._speech_buffer.clear()
                log.debug("VAD: speech start")
            elif "end" in speech_dict:
                self._is_speaking = False
                log.debug("VAD: speech end")
                self._process_speech()
                return

        if self._is_speaking:
            self._speech_buffer.append(chunk)
            # Safety limit
            max_chunks = int(MAX_SPEECH_SECONDS * SAMPLE_RATE / CHUNK_SIZE)
            if len(self._speech_buffer) > max_chunks:
                log.warning("Max speech length reached, processing")
                self._is_speaking = False
                self._process_speech()

    def _process_speech(self) -> None:
        """Transcribe buffered speech and check for wake word."""
        if not self._speech_buffer:
            self._reset_state()
            return

        audio = np.concatenate(self._speech_buffer)
        self._reset_state()

        # Transcribe in a thread to avoid blocking the audio callback
        threading.Thread(
            target=self._transcribe_and_check,
            args=(audio,),
            daemon=True,
        ).start()

    def _transcribe_and_check(self, audio: np.ndarray) -> None:
        """Transcribe audio and check for wake word prefix."""
        from stt import transcribe

        text = transcribe(audio)
        if not text:
            return

        lower = text.lower().strip()
        wake = WAKE_WORD.lower()

        # Check if utterance starts with wake word
        if lower.startswith(wake):
            # Strip wake word and common separators
            remainder = lower[len(wake):].lstrip(" ,.")
            if remainder:
                log.info("Wake word detected, forwarding: %s", remainder)
                if self._on_utterance:
                    self._on_utterance(remainder)
            else:
                log.debug("Wake word detected but no command followed")
        else:
            log.debug("Speech detected but no wake word: %s", text[:50])

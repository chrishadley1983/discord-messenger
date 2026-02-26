"""Audio capture using sounddevice.

Provides a simple start/stop interface for recording 16kHz mono float32 audio.
"""

import numpy as np
import sounddevice as sd
import threading


class AudioCapture:
    """Records audio from the default microphone."""

    SAMPLE_RATE = 16000
    CHANNELS = 1
    BLOCKSIZE = 512  # ~32ms chunks

    def __init__(self):
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        """Called by sounddevice for each audio block."""
        if status:
            pass  # Drop status warnings silently
        with self._lock:
            self._chunks.append(indata[:, 0].copy())

    def start(self) -> None:
        """Start recording."""
        with self._lock:
            self._chunks.clear()
        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            dtype="float32",
            blocksize=self.BLOCKSIZE,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        """Stop recording and return captured audio as float32 array."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._chunks)
            self._chunks.clear()
        return audio

    @property
    def is_recording(self) -> bool:
        return self._stream is not None and self._stream.active

"""Programmatic audio feedback tones.

All tones are generated with numpy sine waves — no external sound files.
Playback is non-blocking (uses sounddevice in a separate stream).
"""

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 24000


def _tone(freq_start: float, freq_end: float, duration: float, volume: float = 0.3) -> np.ndarray:
    """Generate a sine sweep from freq_start to freq_end."""
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    freqs = np.linspace(freq_start, freq_end, len(t))
    phase = 2 * np.pi * np.cumsum(freqs) / SAMPLE_RATE
    samples = (np.sin(phase) * volume).astype(np.float32)
    # Apply fade in/out to avoid clicks
    fade = int(SAMPLE_RATE * 0.01)
    if fade > 0 and len(samples) > 2 * fade:
        samples[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
        samples[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return samples


def _play(samples: np.ndarray) -> None:
    """Non-blocking playback."""
    sd.play(samples, SAMPLE_RATE)


def play_activate() -> None:
    """Rising tone: recording started. 440→660Hz, 150ms."""
    _play(_tone(440, 660, 0.15))


def play_deactivate() -> None:
    """Falling tone: recording stopped. 660→440Hz, 150ms."""
    _play(_tone(660, 440, 0.15))


def play_wake_detected() -> None:
    """Short beep: wake word detected. 880Hz, 100ms."""
    _play(_tone(880, 880, 0.10, volume=0.25))


def play_error() -> None:
    """Low buzz: error occurred. 200Hz, 200ms."""
    _play(_tone(200, 200, 0.20, volume=0.25))

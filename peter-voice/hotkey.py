"""Global hotkey manager using pynput.

Ctrl+Space: Push-to-talk (press=start, release either key=stop)
Ctrl+Shift+Space: Toggle PTT <-> Wake mode
"""

import logging
from pynput import keyboard

log = logging.getLogger(__name__)


class HotkeyManager:
    """Manages global keyboard shortcuts."""

    def __init__(self, on_ptt_start=None, on_ptt_stop=None, on_mode_toggle=None):
        """
        Args:
            on_ptt_start: Called when PTT recording should begin.
            on_ptt_stop: Called when PTT recording should end.
            on_mode_toggle: Called when mode should switch (PTT <-> Wake).
        """
        self._on_ptt_start = on_ptt_start
        self._on_ptt_stop = on_ptt_stop
        self._on_mode_toggle = on_mode_toggle
        self._listener: keyboard.Listener | None = None
        self._ctrl_held = False
        self._shift_held = False
        self._ptt_active = False

    def start(self) -> None:
        """Start the keyboard listener (daemon thread)."""
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            daemon=True,
        )
        self._listener.start()
        log.info("Hotkey listener started")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key):
        try:
            if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                self._ctrl_held = True
            elif key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                self._shift_held = True
            elif key == keyboard.Key.space:
                if self._ctrl_held and self._shift_held:
                    # Ctrl+Shift+Space → mode toggle
                    if self._on_mode_toggle:
                        log.info("Mode toggle hotkey")
                        self._on_mode_toggle()
                elif self._ctrl_held and not self._ptt_active:
                    # Ctrl+Space → PTT start
                    self._ptt_active = True
                    if self._on_ptt_start:
                        log.info("PTT start")
                        self._on_ptt_start()
        except Exception as e:
            log.error("Hotkey press error: %s", e)

    def _on_release(self, key):
        try:
            if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                self._ctrl_held = False
                if self._ptt_active:
                    self._ptt_active = False
                    if self._on_ptt_stop:
                        log.info("PTT stop (ctrl released)")
                        self._on_ptt_stop()
            elif key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                self._shift_held = False
            elif key == keyboard.Key.space:
                if self._ptt_active:
                    self._ptt_active = False
                    if self._on_ptt_stop:
                        log.info("PTT stop (space released)")
                        self._on_ptt_stop()
        except Exception as e:
            log.error("Hotkey release error: %s", e)

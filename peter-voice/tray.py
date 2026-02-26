"""System tray icon using pystray.

Dynamic icon colors reflect current state. Right-click menu for mode
switching and quit.
"""

import logging
import threading
from enum import Enum

from PIL import Image, ImageDraw
import pystray

log = logging.getLogger(__name__)


class TrayState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    WAKE = "wake"
    MUTED = "muted"


# State → color mapping
STATE_COLORS = {
    TrayState.IDLE: "#5865F2",       # Discord blurple
    TrayState.RECORDING: "#ED4245",  # Red
    TrayState.PROCESSING: "#FEE75C", # Yellow
    TrayState.SPEAKING: "#57F287",   # Green
    TrayState.WAKE: "#EB459E",       # Pink
    TrayState.MUTED: "#99AAB5",      # Grey
}

STATE_TOOLTIPS = {
    TrayState.IDLE: "Peter Voice — Idle (Ctrl+Space to talk)",
    TrayState.RECORDING: "Peter Voice — Recording...",
    TrayState.PROCESSING: "Peter Voice — Processing...",
    TrayState.SPEAKING: "Peter Voice — Speaking...",
    TrayState.WAKE: "Peter Voice — Listening for wake word",
    TrayState.MUTED: "Peter Voice — Muted",
}


def _create_icon_image(color: str, size: int = 64) -> Image.Image:
    """Create a simple circular icon with the given color."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
    )
    # Draw a "P" in the center
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial.ttf", size=size // 2)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "P", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2, (size - th) / 2 - 2),
        "P",
        fill="white",
        font=font,
    )
    return img


class VoiceTray:
    """System tray icon with dynamic state and right-click menu."""

    def __init__(self, on_mode_change=None, on_quit=None):
        """
        Args:
            on_mode_change: callable(mode_str) — "ptt", "wake", or "muted"
            on_quit: callable() — clean shutdown
        """
        self._on_mode_change = on_mode_change
        self._on_quit = on_quit
        self._state = TrayState.IDLE
        self._current_mode = "ptt"
        self._icon: pystray.Icon | None = None

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                "Push-to-Talk",
                self._set_ptt,
                checked=lambda item: self._current_mode == "ptt",
                radio=True,
            ),
            pystray.MenuItem(
                "Wake Word",
                self._set_wake,
                checked=lambda item: self._current_mode == "wake",
                radio=True,
            ),
            pystray.MenuItem(
                "Muted",
                self._set_muted,
                checked=lambda item: self._current_mode == "muted",
                radio=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def _set_ptt(self):
        self._current_mode = "ptt"
        self.update_state(TrayState.IDLE)
        if self._on_mode_change:
            self._on_mode_change("ptt")

    def _set_wake(self):
        self._current_mode = "wake"
        self.update_state(TrayState.WAKE)
        if self._on_mode_change:
            self._on_mode_change("wake")

    def _set_muted(self):
        self._current_mode = "muted"
        self.update_state(TrayState.MUTED)
        if self._on_mode_change:
            self._on_mode_change("muted")

    def _quit(self):
        if self._on_quit:
            self._on_quit()
        if self._icon:
            self._icon.stop()

    def update_state(self, state: TrayState) -> None:
        """Update the tray icon color and tooltip."""
        self._state = state
        if self._icon:
            color = STATE_COLORS.get(state, "#5865F2")
            self._icon.icon = _create_icon_image(color)
            self._icon.title = STATE_TOOLTIPS.get(state, "Peter Voice")

    def notify(self, title: str, message: str) -> None:
        """Show a Windows notification balloon."""
        if self._icon:
            try:
                self._icon.notify(message, title)
            except Exception as e:
                log.warning("Tray notification failed: %s", e)

    def run(self) -> None:
        """Start the tray icon (blocks the calling thread)."""
        initial_color = STATE_COLORS[TrayState.IDLE]
        self._icon = pystray.Icon(
            name="peter-voice",
            icon=_create_icon_image(initial_color),
            title=STATE_TOOLTIPS[TrayState.IDLE],
            menu=self._build_menu(),
        )
        log.info("System tray started")
        self._icon.run()  # Blocks until stop()

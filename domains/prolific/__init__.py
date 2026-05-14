"""Prolific studies monitor.

Polls app.prolific.com/studies on a jittered interval during waking hours,
posts a Discord webhook for every newly-seen study.

Uses CDP-to-real-Chrome (Chrome-Prolific profile) to avoid bot detection.
One-time manual login required: python -m domains.prolific.login
"""

from .monitor import register_prolific_monitor

__all__ = ["register_prolific_monitor"]

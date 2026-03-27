"""Sanitiser stub — the full sanitiser was removed as dead code (Mar 2026).

Router_v2 outputs clean JSON (pre_sanitised=True), and channel-based
responses bypass the pipeline entirely. This stub exists only to satisfy
the import in pipeline.py for the fallback path.
"""

from dataclasses import dataclass, field


@dataclass
class SanitiserResult:
    content: str
    rules_applied: list[str] = field(default_factory=list)


def sanitise(text: str, track_rules: bool = False):
    """No-op sanitiser — returns input unchanged."""
    if track_rules:
        return SanitiserResult(content=text, rules_applied=["stub:no-op"])
    return text


def check_bypass_flag(text: str) -> bool:
    """Check for --raw or --debug bypass flags."""
    return "--raw" in text or "--debug" in text

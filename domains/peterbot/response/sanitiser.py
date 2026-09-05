"""Sanitiser stub — the full sanitiser was removed as dead code (Mar 2026).

Router_v2 outputs clean JSON (pre_sanitised=True), and channel-based
responses bypass the pipeline entirely. This stub exists only to satisfy
the import in pipeline.py for the fallback path.

strip_tool_xml() is live code: channel replies occasionally leak tool-call
XML fragments (e.g. the 2026-07-01 Morning News post ended with a literal
"</text>\n</invoke>" that was posted to Discord and saved to
news_history.jsonl). The scheduler runs every job response through it.
"""

import re
from dataclasses import dataclass, field


# Tool-call XML artifacts that must never reach Discord. These tags have no
# legitimate use in any skill output, so stripping them anywhere is safe.
_TOOL_XML_PATTERN = re.compile(
    r"</?(?:"
    r"text|invoke|parameter[^>]*|function_calls|function_results|"
    r"fnr|output|tool_result|tool_use"
    r")>"
    r"|<invoke\s+name=[^>]*>"
    r"|<parameter\s+name=[^>]*>",
    re.IGNORECASE,
)


def strip_tool_xml(text: str) -> str:
    """Remove leaked tool-call XML fragments from a response."""
    if not text or "<" not in text:
        return text
    cleaned = _TOOL_XML_PATTERN.sub("", text)
    if cleaned != text:
        # Collapse whitespace left behind at the tail
        cleaned = cleaned.rstrip()
    return cleaned


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

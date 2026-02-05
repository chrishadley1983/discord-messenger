"""Conversational Formatter - For natural language chat responses.

The most common response type (~80% of responses).
Based on RESPONSE.md Section 5.2.
"""

import re
import json
from typing import Optional


def format_conversational(text: str, context: Optional[dict] = None) -> str:
    """Format conversational response for Discord.

    Rules (Section 5.2):
    1. Strip markdown headers (#, ##, ###)
    2. Preserve Discord-compatible markdown (bold, italic, code)
    3. Remove JSON blocks, extract prose
    4. Strip trailing meta-commentary
    5. Clean up spacing

    Args:
        text: Sanitised text to format
        context: Optional context (user_prompt, etc.)

    Returns:
        Discord-ready conversational text
    """
    if not text:
        return ''

    # 1. Strip markdown headers (conversational shouldn't have them)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # 2. Strip horizontal rules
    text = re.sub(r'^---+\s*$', '', text, flags=re.MULTILINE)

    # 3. Strip JSON blocks and extract prose
    text = strip_json_from_conversational(text)

    # 4. Remove trailing meta-commentary
    text = strip_trailing_meta(text)

    # 5. Clean up spacing
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text


def strip_json_from_conversational(text: str) -> str:
    """Strip or summarise JSON from conversational responses.

    If response is ONLY JSON with no prose, return a note.
    If JSON embedded in prose, remove JSON blocks and keep prose.
    """
    # Check if entire response is JSON
    trimmed = text.strip()
    if trimmed.startswith(('{', '[')):
        try:
            json.loads(trimmed)
            # It's valid JSON - this shouldn't happen in conversational
            # Return as-is, the classifier should have caught this
            return trimmed
        except (json.JSONDecodeError, ValueError):
            pass

    # Remove fenced JSON blocks
    text = re.sub(r'```json\n[\s\S]*?\n```', '', text)
    text = re.sub(r'```\n\{[\s\S]*?\}\n```', '', text)
    text = re.sub(r'```\n\[[\s\S]*?\]\n```', '', text)

    # Remove inline JSON objects that leaked (standalone lines starting with {)
    text = re.sub(r'^\s*\{[^}]+\}\s*$', '', text, flags=re.MULTILINE)

    # Clean up resulting gaps
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


# Common trailing phrases to strip
TRAILING_PHRASES = [
    r"let me know if you need [\w\s]+[!.]?",  # Most general - matches "let me know if you need X!"
    r"let me know if you (?:need|want|have) (?:anything|any questions?|more|else)",
    r"(?:hope|glad) (?:this|that) helps?[!.]?",
    r"feel free to (?:ask|reach out|let me know)",
    r"is there anything else (?:i can help with|you need)?",
    r"if you have (?:any )?(?:other )?questions?,? (?:just )?(?:ask|let me know)",
    r"happy to help(?: further)?[!.]?",
    r"(?:please )?let me know if (?:you )?(?:need|want) (?:any)?(?:thing)? else",
    r"don't hesitate to ask",
    r"i'm here if you need (?:anything|me)",
]


def strip_trailing_meta(text: str) -> str:
    """Remove common assistant sign-off phrases.

    These phrases add no value and feel robotic in Discord.
    """
    # Also check for trailing sentences that match patterns
    for pattern in TRAILING_PHRASES:
        # Match at end of text or on its own line
        text = re.sub(
            rf'(?:\n\n|\n)?\s*{pattern}\s*$',
            '',
            text,
            flags=re.IGNORECASE
        )
        # Also match at end with punctuation
        text = re.sub(
            rf'\s*{pattern}\s*$',
            '',
            text,
            flags=re.IGNORECASE
        )

    return text.strip()


def ensure_conversational_length(text: str, max_chars: int = 500) -> str:
    """For simple Q&A, keep responses concise.

    Note: This is optional - only use for truly casual responses.
    Substantive requests should NOT be truncated (chunker handles splitting).
    """
    if len(text) <= max_chars:
        return text

    # Find a good break point near max_chars
    break_patterns = ['\n\n', '. ', '.\n', '! ', '? ']

    for pattern in break_patterns:
        pos = text.rfind(pattern, 0, max_chars)
        if pos > max_chars * 0.7:  # At least 70% of max
            return text[:pos + len(pattern)].strip()

    # Fall back to word boundary
    space_pos = text.rfind(' ', 0, max_chars)
    if space_pos > max_chars * 0.7:
        return text[:space_pos].strip() + '...'

    return text[:max_chars].strip() + '...'


# =============================================================================
# TESTING
# =============================================================================

def test_conversational_formatter():
    """Run basic conversational formatter tests."""
    test_cases = [
        # Strip headers
        (
            "# Welcome\n\nHere's some info.",
            "Welcome\n\nHere's some info."
        ),

        # Strip JSON blocks
        (
            "Here's the data:\n```json\n{\"key\": \"value\"}\n```\nThat's it.",
            "Here's the data:\n\nThat's it."
        ),

        # Strip trailing meta
        (
            "The answer is 42. Let me know if you need anything else!",
            "The answer is 42."
        ),

        # Strip horizontal rules
        (
            "First section.\n\n---\n\nSecond section.",
            "First section.\n\nSecond section."
        ),

        # Multiple cleanups
        (
            "## Header\n\nContent here.\n\nHope this helps!",
            "Header\n\nContent here."
        ),
    ]

    passed = 0
    failed = 0

    for input_text, expected in test_cases:
        result = format_conversational(input_text)

        if result == expected:
            passed += 1
            print(f"✓ PASS")
        else:
            failed += 1
            print(f"✗ FAIL")
            print(f"  Input: {repr(input_text[:50])}")
            print(f"  Expected: {repr(expected[:50])}")
            print(f"  Got: {repr(result[:50])}")

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == '__main__':
    test_conversational_formatter()

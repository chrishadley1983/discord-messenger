"""Tests for garbage detection in response parser.

Tests the is_garbage_response() and detect_garbage_patterns() functions
that identify when response extraction captures shell/tool artifacts
instead of actual Claude responses.
"""

import pytest
from domains.peterbot.parser import (
    is_garbage_response,
    detect_garbage_patterns,
    GARBAGE_PATTERNS,
    GARBAGE_MIN_LENGTH,
)


class TestDetectGarbagePatterns:
    """Tests for detect_garbage_patterns() function."""

    def test_detects_shell_paths(self):
        """Should detect Unix shell paths."""
        content = "/home/chris_hadley/.claude/projects/foo/bar"
        patterns = detect_garbage_patterns(content)
        assert "shell_path" in patterns

    def test_detects_claude_paths(self):
        """Should detect Claude-specific internal paths."""
        content = "Reading .claude/projects/-home-chris-hadley-peterbot/context.md"
        patterns = detect_garbage_patterns(content)
        assert "claude_path" in patterns

    def test_detects_shell_operators(self):
        """Should detect shell operators like || and &&."""
        content = "|| echo 'No response'\n&& grep -r pattern"
        patterns = detect_garbage_patterns(content)
        assert "shell_operator" in patterns

    def test_detects_command_fragments(self):
        """Should detect command fragments like curl, grep."""
        content = 'curl -s "http://localhost:8100/api/health"'
        patterns = detect_garbage_patterns(content)
        assert "command_fragment" in patterns

    def test_detects_file_paths(self):
        """Should detect bare file paths."""
        content = "context_abc123.md"
        patterns = detect_garbage_patterns(content)
        assert "file_path" in patterns

    def test_no_patterns_for_normal_content(self):
        """Should return empty list for normal content."""
        content = """Here's the weather forecast for today:
        - Morning: Sunny, 15C
        - Afternoon: Cloudy, 18C
        - Evening: Clear, 12C
        """
        patterns = detect_garbage_patterns(content)
        assert patterns == []


class TestIsGarbageResponse:
    """Tests for is_garbage_response() function."""

    def test_normal_response_not_garbage(self):
        """Normal responses should not be detected as garbage."""
        content = """Here's what I found about your question:

The weather today will be mostly sunny with temperatures around 18 degrees.
You might want to bring a light jacket for the evening as it could cool down.

Let me know if you need anything else!
"""
        is_garbage, patterns = is_garbage_response(content)
        assert is_garbage is False
        assert patterns == []

    def test_shell_path_response_is_garbage(self):
        """Shell path responses should be detected as garbage."""
        content = """/home/chris_hadley/.claude/projects/-home-chris-hadley-peterbot/context.md
|| echo "No g...)
/usr/bin/bash -c test
/var/log/messages
"""
        is_garbage, patterns = is_garbage_response(content)
        assert is_garbage is True
        assert len(patterns) >= 2

    def test_mixed_garbage_detected(self):
        """Mixed shell/tool output should be detected as garbage."""
        content = """curl -s "http://localhost:8100/api/test"
grep -r "pattern" .
|| echo "fallback"
/tmp/context_12345.md
2>/dev/null
"""
        is_garbage, patterns = is_garbage_response(content)
        assert is_garbage is True

    def test_short_response_not_garbage(self):
        """Short responses below threshold should not be flagged."""
        content = "OK"
        is_garbage, patterns = is_garbage_response(content)
        assert is_garbage is False

    def test_no_reply_not_garbage(self):
        """NO_REPLY marker should not be flagged as garbage."""
        content = "NO_REPLY"
        is_garbage, patterns = is_garbage_response(content)
        assert is_garbage is False

    def test_heartbeat_marker_not_garbage(self):
        """HEARTBEAT marker should not be flagged as garbage."""
        content = "---HEARTBEAT---\nAll systems operational"
        is_garbage, patterns = is_garbage_response(content)
        assert is_garbage is False

    def test_empty_response_not_garbage(self):
        """Empty responses should not be flagged (handled differently)."""
        is_garbage, patterns = is_garbage_response("")
        assert is_garbage is False
        assert patterns == []

    def test_high_garbage_ratio_detected(self):
        """High ratio of garbage-like lines should flag response."""
        # More than 40% of lines look like garbage
        content = """/home/user/path
/usr/local/bin
/var/log/test
Normal line here
/tmp/file.txt
Another normal line
/etc/config
"""
        is_garbage, patterns = is_garbage_response(content)
        assert is_garbage is True
        assert "high_garbage_ratio" in patterns or len(patterns) >= 2

    def test_single_pattern_not_enough(self):
        """Single pattern match should not flag as garbage."""
        # Only one shell path, but mostly normal content
        content = """Here's the information you requested:

The file is located at /home/user/documents/report.pdf

Please let me know if you need help accessing it.
This is a helpful response with real content.
"""
        is_garbage, patterns = is_garbage_response(content)
        # Should not be flagged because it's mostly normal content
        assert is_garbage is False


class TestGarbagePatternsConfig:
    """Tests for garbage pattern configuration."""

    def test_all_patterns_are_compiled_regex(self):
        """All patterns should be compiled regex objects."""
        import re
        for name, pattern in GARBAGE_PATTERNS.items():
            assert isinstance(pattern, re.Pattern), f"{name} should be compiled regex"

    def test_minimum_length_configured(self):
        """Minimum content length should be configured."""
        assert GARBAGE_MIN_LENGTH > 0
        assert GARBAGE_MIN_LENGTH <= 100  # Reasonable upper bound


class TestRealWorldGarbageExamples:
    """Tests using real-world garbage examples from incident logs."""

    def test_incident_example_1(self):
        """Example from 2026-02-05 incident: shell paths."""
        content = """|| echo "No g...)
/home/chris_hadley/.claude/projects/-home-chris-hadley-peterbot/context_12345.md
bash-5.1$
"""
        is_garbage, patterns = is_garbage_response(content)
        assert is_garbage is True

    def test_incident_example_2(self):
        """Tool output fragments."""
        content = """query="traffic london to brighton"
limit=5
offset=0
2>/dev/null
|| true
"""
        is_garbage, patterns = is_garbage_response(content)
        assert is_garbage is True

    def test_valid_technical_response_not_garbage(self):
        """Technical responses with code should not be flagged."""
        content = """Here's how to fix the issue:

```python
def calculate_total(items):
    return sum(item.price for item in items)
```

The function iterates over items and sums their prices.
You can use it like this: `total = calculate_total(cart_items)`
"""
        is_garbage, patterns = is_garbage_response(content)
        assert is_garbage is False

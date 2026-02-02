"""Tests for passive capture detection."""

import pytest
from domains.second_brain.passive import (
    detect_passive_captures,
    should_capture_message,
    detect_urls,
    detect_idea,
)


class TestUrlExtraction:
    """Test URL extraction."""

    def test_basic_url(self):
        """Should extract basic HTTP URLs."""
        text = "Check out https://example.com for more info"
        urls = detect_urls(text)
        assert "https://example.com" in urls

    def test_url_with_path(self):
        """Should extract URLs with paths."""
        text = "See https://example.com/path/to/page.html"
        urls = detect_urls(text)
        assert "https://example.com/path/to/page.html" in urls

    def test_url_with_query(self):
        """Should extract URLs with query strings."""
        text = "Link: https://example.com/search?q=test&page=1"
        urls = detect_urls(text)
        assert any("example.com/search" in url for url in urls)

    def test_multiple_urls(self):
        """Should extract multiple URLs."""
        text = "See https://a.com and https://b.com for more"
        urls = detect_urls(text)
        assert len(urls) >= 2

    def test_no_urls(self):
        """Should handle text without URLs."""
        text = "This is plain text without any links"
        urls = detect_urls(text)
        assert urls == []

    def test_cleans_trailing_punctuation(self):
        """Should remove trailing punctuation from URLs."""
        text = "Check https://example.com."
        urls = detect_urls(text)
        assert "https://example.com" in urls


class TestShouldCapture:
    """Test quick pre-filter for capture."""

    def test_short_message_ignored(self):
        """Very short messages without signals should be skipped."""
        assert should_capture_message("ok") is False
        assert should_capture_message("yes") is False
        assert should_capture_message("lol") is False

    def test_url_message_captured(self):
        """Messages with URLs should be captured."""
        assert should_capture_message("Check this: https://example.com") is True

    def test_idea_signal_captured(self):
        """Messages with idea signals should be captured."""
        # Check which phrases are in IDEA_SIGNAL_PHRASES
        assert should_capture_message("what if we built a new feature") is True
        assert should_capture_message("i think we should update the docs") is True


class TestDetectIdea:
    """Test idea detection."""

    def test_no_signal_no_idea(self):
        """Without signal phrases, no idea detected."""
        idea = detect_idea("This is a regular statement.")
        assert idea is None

    def test_signal_detected(self):
        """Signal phrase should trigger idea detection."""
        idea = detect_idea("What if we built a new dashboard for tracking?")
        assert idea is not None

    def test_too_short_rejected(self):
        """Very short messages with signals still rejected."""
        idea = detect_idea("What if?")
        assert idea is None


class TestDetectPassiveCaptures:
    """Test full passive capture detection."""

    def test_url_detection(self):
        """Should detect URLs for capture."""
        message = "Great article: https://example.com/article"
        captures = detect_passive_captures(message)

        url_captures = [c for c in captures if c.url]
        assert len(url_captures) >= 1
        assert "example.com" in url_captures[0].url

    def test_idea_detection(self):
        """Should detect ideas for capture."""
        message = "I think we should build a new dashboard for metrics tracking"
        captures = detect_passive_captures(message)

        idea_captures = [c for c in captures if c.idea_text]
        assert len(idea_captures) >= 1

    def test_empty_message(self):
        """Should handle empty messages."""
        captures = detect_passive_captures("")
        assert captures == []

    def test_command_ignored(self):
        """Should ignore bot commands."""
        captures = detect_passive_captures("!help")
        assert captures == []

    def test_question_ignored(self):
        """Should ignore questions to bot."""
        captures = detect_passive_captures("What is the weather today?")
        assert captures == []

    def test_discord_urls_ignored(self):
        """Should ignore Discord CDN URLs."""
        captures = detect_passive_captures(
            "Here's an image https://cdn.discordapp.com/attachments/123/456/image.png"
        )
        assert captures == []

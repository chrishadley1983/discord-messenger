"""Tests for morning briefing data fetching and formatting."""

import pytest
from unittest.mock import patch, AsyncMock

# Import the trim functions
from domains.peterbot.data_fetchers import (
    _trim_x_items,
    _trim_reddit_items,
    _trim_web_items,
)


class TestTrimXItems:
    """Tests for X/Twitter post trimming."""

    def test_basic_trim(self):
        """Test basic trimming with valid data."""
        items = [
            {
                "url": "https://x.com/username/status/123",
                "text": "Test post about Claude",
                "context": "Some context here"
            }
        ]
        result = _trim_x_items(items, limit=5)

        assert len(result) == 1
        assert result[0]["url"] == "https://x.com/username/status/123"
        assert result[0]["title"] == "Test post about Claude"
        assert result[0]["handle"] == "@username"
        assert result[0]["markdown_link"] == "[Test post about Claude](https://x.com/username/status/123)"

    def test_handle_extraction(self):
        """Test @handle extraction from X URLs."""
        items = [
            {"url": "https://x.com/anthropic/status/123", "text": "Post"},
            {"url": "https://x.com/ClawdBot/status/456", "text": "Post"},
        ]
        result = _trim_x_items(items)

        assert result[0]["handle"] == "@anthropic"
        assert result[1]["handle"] == "@ClawdBot"

    def test_empty_input(self):
        """Test with empty input list."""
        result = _trim_x_items([])
        assert result == []

    def test_missing_fields(self):
        """Test with missing optional fields."""
        items = [{"url": "https://x.com/user/status/1"}]
        result = _trim_x_items(items)

        assert result[0]["title"] == ""
        assert result[0]["context"] == ""

    def test_limit_enforcement(self):
        """Test that item limit is enforced."""
        items = [{"url": f"https://x.com/u/status/{i}", "text": f"Post {i}"} for i in range(20)]
        result = _trim_x_items(items, limit=15)

        assert len(result) == 15

    def test_title_truncation(self):
        """Test that title is truncated to 100 chars."""
        items = [{"url": "https://x.com/u/status/1", "text": "A" * 150}]
        result = _trim_x_items(items)

        assert len(result[0]["title"]) == 100

    def test_context_truncation(self):
        """Test that context is truncated to 200 chars."""
        items = [{"url": "https://x.com/u/status/1", "text": "Post", "context": "B" * 300}]
        result = _trim_x_items(items)

        assert len(result[0]["context"]) == 200

    def test_handle_extraction_edge_cases(self):
        """Test handle extraction with various URL formats."""
        items = [
            {"url": "https://x.com/user_name/status/123", "text": "Post"},  # underscore
            {"url": "https://x.com/User123/status/456", "text": "Post"},    # alphanumeric
            {"url": "https://twitter.com/oldstyle/status/789", "text": "Post"},  # twitter.com (no match)
        ]
        result = _trim_x_items(items)

        assert result[0]["handle"] == "@user_name"
        assert result[1]["handle"] == "@User123"
        assert result[2]["handle"] == ""  # twitter.com doesn't match x.com regex

    def test_uses_title_field_fallback(self):
        """Test that 'title' field is used when 'text' is missing."""
        items = [{"url": "https://x.com/user/status/1", "title": "Fallback title"}]
        result = _trim_x_items(items)

        assert result[0]["title"] == "Fallback title"


class TestTrimRedditItems:
    """Tests for Reddit post trimming."""

    def test_basic_trim(self):
        """Test basic trimming with valid data."""
        items = [
            {
                "url": "https://reddit.com/r/ClaudeAI/comments/abc/test",
                "text": "Discussion title",
                "context": "Discussion context",
                "subreddit": "r/ClaudeAI"
            }
        ]
        result = _trim_reddit_items(items, limit=5)

        assert len(result) == 1
        assert result[0]["subreddit"] == "r/ClaudeAI"
        assert "[Discussion title]" in result[0]["markdown_link"]

    def test_subreddit_extraction(self):
        """Test subreddit extraction from URL when not provided."""
        items = [
            {"url": "https://reddit.com/r/LocalLLaMA/comments/xyz/post", "text": "Post"}
        ]
        result = _trim_reddit_items(items)

        assert result[0]["subreddit"] == "r/LocalLLaMA"

    def test_preserves_existing_subreddit(self):
        """Test that existing subreddit field is preserved."""
        items = [
            {"url": "https://reddit.com/r/ClaudeAI/comments/xyz/post",
             "text": "Post",
             "subreddit": "r/ClaudeAI"}
        ]
        result = _trim_reddit_items(items)

        assert result[0]["subreddit"] == "r/ClaudeAI"

    def test_limit_enforcement(self):
        """Test that item limit is enforced."""
        items = [{"url": f"https://reddit.com/r/test/comments/{i}/post", "text": f"Post {i}"} for i in range(20)]
        result = _trim_reddit_items(items, limit=12)

        assert len(result) == 12

    def test_empty_input(self):
        """Test with empty input list."""
        result = _trim_reddit_items([])
        assert result == []

    def test_missing_fields(self):
        """Test with missing optional fields."""
        items = [{"url": "https://reddit.com/r/test/comments/1/post"}]
        result = _trim_reddit_items(items)

        assert result[0]["title"] == ""
        assert result[0]["context"] == ""

    def test_subreddit_extraction_various_formats(self):
        """Test subreddit extraction from various URL formats."""
        items = [
            {"url": "https://www.reddit.com/r/MachineLearning/comments/abc/title", "text": "Post"},
            {"url": "https://old.reddit.com/r/ClaudeAI/comments/def/title", "text": "Post"},
        ]
        result = _trim_reddit_items(items)

        assert result[0]["subreddit"] == "r/MachineLearning"
        assert result[1]["subreddit"] == "r/ClaudeAI"


class TestTrimWebItems:
    """Tests for web article trimming."""

    def test_basic_trim(self):
        """Test basic trimming with valid data."""
        items = [
            {
                "url": "https://anthropic.com/news/article",
                "text": "Anthropic announces new feature",
                "context": "Article context"
            }
        ]
        result = _trim_web_items(items, limit=5)

        assert len(result) == 1
        assert result[0]["url"] == "https://anthropic.com/news/article"
        assert "[Anthropic announces new feature](https://anthropic.com/news/article)" == result[0]["markdown_link"]

    def test_empty_input(self):
        """Test with empty input list."""
        result = _trim_web_items([])
        assert result == []

    def test_limit_enforcement(self):
        """Test that item limit is enforced."""
        items = [{"url": f"https://example.com/{i}", "text": f"Article {i}"} for i in range(20)]
        result = _trim_web_items(items, limit=12)

        assert len(result) == 12

    def test_missing_fields(self):
        """Test with missing optional fields."""
        items = [{"url": "https://example.com/article"}]
        result = _trim_web_items(items)

        assert result[0]["title"] == ""
        assert result[0]["context"] == ""

    def test_title_truncation(self):
        """Test that title is truncated to 100 chars."""
        items = [{"url": "https://example.com", "text": "X" * 150}]
        result = _trim_web_items(items)

        assert len(result[0]["title"]) == 100

    def test_uses_title_field_fallback(self):
        """Test that 'title' field is used when 'text' is missing."""
        items = [{"url": "https://example.com", "title": "Fallback title"}]
        result = _trim_web_items(items)

        assert result[0]["title"] == "Fallback title"


class TestMarkdownLinkFormat:
    """Tests for markdown link formatting."""

    def test_no_angle_brackets(self):
        """Ensure no angle brackets in output."""
        items = [{"url": "https://x.com/user/status/1", "text": "Post"}]
        result = _trim_x_items(items)

        assert "<" not in result[0]["markdown_link"]
        assert ">" not in result[0]["markdown_link"]

    def test_proper_markdown_format(self):
        """Verify proper markdown link format."""
        items = [{"url": "https://example.com", "text": "Title"}]
        result = _trim_web_items(items)

        link = result[0]["markdown_link"]
        assert link.startswith("[")
        assert "](https://example.com)" in link

    def test_empty_url_no_link(self):
        """Test that empty URL produces empty markdown_link."""
        items = [{"url": "", "text": "Title"}]
        result = _trim_web_items(items)

        assert result[0]["markdown_link"] == ""

    def test_empty_title_no_link(self):
        """Test that empty title produces empty markdown_link."""
        items = [{"url": "https://example.com", "text": ""}]
        result = _trim_web_items(items)

        assert result[0]["markdown_link"] == ""

    def test_none_url_no_link(self):
        """Test that None URL produces empty markdown_link."""
        items = [{"text": "Title"}]  # url key missing entirely
        result = _trim_web_items(items)

        assert result[0]["markdown_link"] == ""

    def test_x_markdown_format(self):
        """Verify X posts have proper markdown format."""
        items = [{"url": "https://x.com/user/status/123", "text": "My Tweet"}]
        result = _trim_x_items(items)

        assert result[0]["markdown_link"] == "[My Tweet](https://x.com/user/status/123)"

    def test_reddit_markdown_format(self):
        """Verify Reddit posts have proper markdown format."""
        items = [{"url": "https://reddit.com/r/test/comments/abc/post", "text": "Discussion"}]
        result = _trim_reddit_items(items)

        assert result[0]["markdown_link"] == "[Discussion](https://reddit.com/r/test/comments/abc/post)"


class TestNoneAndEmptyHandling:
    """Tests for handling None values and empty data."""

    def test_x_items_with_none_text(self):
        """Test X items where text field is None."""
        items = [{"url": "https://x.com/user/status/1", "text": None}]
        result = _trim_x_items(items)

        assert result[0]["title"] == ""

    def test_reddit_items_with_none_context(self):
        """Test Reddit items where context is None."""
        items = [{"url": "https://reddit.com/r/test/comments/1/post", "text": "Title", "context": None}]
        result = _trim_reddit_items(items)

        assert result[0]["context"] == ""

    def test_web_items_with_all_none(self):
        """Test web items with all fields None or missing."""
        items = [{}]
        result = _trim_web_items(items)

        assert result[0]["url"] == ""
        assert result[0]["title"] == ""
        assert result[0]["context"] == ""
        assert result[0]["markdown_link"] == ""


# Integration tests would require mocking the Grok API
class TestMorningBriefingIntegration:
    """Integration tests for the full data fetching flow."""

    @pytest.mark.asyncio
    async def test_get_morning_briefing_data_structure(self):
        """Test that get_morning_briefing_data returns expected structure."""
        from domains.peterbot.data_fetchers import get_morning_briefing_data

        # Mock the search functions in jobs.morning_briefing (where they're defined)
        with patch('jobs.morning_briefing._search_x', new_callable=AsyncMock) as mock_x, \
             patch('jobs.morning_briefing._search_reddit', new_callable=AsyncMock) as mock_reddit, \
             patch('jobs.morning_briefing._search_web', new_callable=AsyncMock) as mock_web:

            mock_x.return_value = [
                {"url": "https://x.com/test/status/1", "text": "X Post", "context": "ctx"}
            ]
            mock_reddit.return_value = [
                {"url": "https://reddit.com/r/ClaudeAI/comments/1/post", "text": "Reddit Post", "context": "ctx"}
            ]
            mock_web.return_value = [
                {"url": "https://example.com/article", "text": "Web Article", "context": "ctx"}
            ]

            result = await get_morning_briefing_data()

            # Check structure
            assert "x_posts" in result
            assert "reddit_posts" in result
            assert "web_articles" in result
            assert "has_x_data" in result
            assert "has_reddit_data" in result
            assert "has_web_data" in result
            assert "fetch_time" in result

            # Check flags
            assert result["has_x_data"] is True
            assert result["has_reddit_data"] is True
            assert result["has_web_data"] is True

            # Check items have markdown_link
            assert "markdown_link" in result["x_posts"][0]
            assert "markdown_link" in result["reddit_posts"][0]
            assert "markdown_link" in result["web_articles"][0]

    @pytest.mark.asyncio
    async def test_get_morning_briefing_data_empty_results(self):
        """Test that get_morning_briefing_data handles empty results."""
        from domains.peterbot.data_fetchers import get_morning_briefing_data

        with patch('jobs.morning_briefing._search_x', new_callable=AsyncMock) as mock_x, \
             patch('jobs.morning_briefing._search_reddit', new_callable=AsyncMock) as mock_reddit, \
             patch('jobs.morning_briefing._search_web', new_callable=AsyncMock) as mock_web:

            mock_x.return_value = []
            mock_reddit.return_value = []
            mock_web.return_value = []

            result = await get_morning_briefing_data()

            # Check structure still present
            assert "x_posts" in result
            assert "reddit_posts" in result
            assert "web_articles" in result

            # Check flags are False for empty data
            assert result["has_x_data"] is False
            assert result["has_reddit_data"] is False
            assert result["has_web_data"] is False

            # Check lists are empty
            assert result["x_posts"] == []
            assert result["reddit_posts"] == []
            assert result["web_articles"] == []

    @pytest.mark.asyncio
    async def test_get_morning_briefing_data_exception_handling(self):
        """Test that get_morning_briefing_data handles search exceptions gracefully."""
        from domains.peterbot.data_fetchers import get_morning_briefing_data

        with patch('jobs.morning_briefing._search_x', new_callable=AsyncMock) as mock_x, \
             patch('jobs.morning_briefing._search_reddit', new_callable=AsyncMock) as mock_reddit, \
             patch('jobs.morning_briefing._search_web', new_callable=AsyncMock) as mock_web:

            # Simulate X search failing
            mock_x.side_effect = Exception("API error")
            mock_reddit.return_value = [{"url": "https://reddit.com/r/test/comments/1/post", "text": "Post"}]
            mock_web.return_value = [{"url": "https://example.com", "text": "Article"}]

            result = await get_morning_briefing_data()

            # X should be empty due to exception
            assert result["has_x_data"] is False
            assert result["x_posts"] == []

            # Reddit and web should still work
            assert result["has_reddit_data"] is True
            assert result["has_web_data"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

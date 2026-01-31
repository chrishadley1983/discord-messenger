"""Integration tests for multi-turn tool calls."""

import pytest
from unittest.mock import Mock, AsyncMock, patch


class TestMultiTurnToolCalls:
    """Test multi-turn tool call handling."""

    @pytest.mark.asyncio
    async def test_two_sequential_tool_calls(self):
        """Test handling two tool calls in sequence."""
        from claude_client import ClaudeClient

        with patch('anthropic.Anthropic') as mock_anthropic:
            # First response: first tool call
            tool_use_1 = Mock()
            tool_use_1.type = "tool_use"
            tool_use_1.name = "get_today_totals"
            tool_use_1.id = "call_1"
            tool_use_1.input = {}

            response_1 = Mock()
            response_1.content = [tool_use_1]

            # Second response: second tool call
            tool_use_2 = Mock()
            tool_use_2.type = "tool_use"
            tool_use_2.name = "get_steps"
            tool_use_2.id = "call_2"
            tool_use_2.input = {}

            response_2 = Mock()
            response_2.content = [tool_use_2]

            # Final response: text
            text_block = Mock()
            text_block.type = "text"
            text_block.text = "You've had 1500 calories and 8000 steps today."

            response_3 = Mock()
            response_3.content = [text_block]

            mock_client = Mock()
            mock_client.messages.create.side_effect = [response_1, response_2, response_3]
            mock_anthropic.return_value = mock_client

            # Mock handlers
            totals_handler = AsyncMock(return_value={"calories": 1500, "protein_g": 80})
            steps_handler = AsyncMock(return_value={"steps": 8000})

            client = ClaudeClient(api_key="test-key")
            response = await client.chat(
                message="how am I doing today?",
                system="You are a test assistant",
                tools=[
                    {"name": "get_today_totals", "description": "Get totals", "input_schema": {}},
                    {"name": "get_steps", "description": "Get steps", "input_schema": {}}
                ],
                tool_handlers={
                    "get_today_totals": totals_handler,
                    "get_steps": steps_handler
                }
            )

            # Both handlers should have been called
            totals_handler.assert_called_once()
            steps_handler.assert_called_once()
            assert "1500" in response or "8000" in response

    @pytest.mark.asyncio
    async def test_parallel_tool_calls(self):
        """Test handling multiple tool calls in a single response."""
        from claude_client import ClaudeClient

        with patch('anthropic.Anthropic') as mock_anthropic:
            # Response with two tool calls
            tool_use_1 = Mock()
            tool_use_1.type = "tool_use"
            tool_use_1.name = "get_today_totals"
            tool_use_1.id = "call_1"
            tool_use_1.input = {}

            tool_use_2 = Mock()
            tool_use_2.type = "tool_use"
            tool_use_2.name = "get_steps"
            tool_use_2.id = "call_2"
            tool_use_2.input = {}

            response_1 = Mock()
            response_1.content = [tool_use_1, tool_use_2]

            # Final response
            text_block = Mock()
            text_block.type = "text"
            text_block.text = "Summary: 1500 cal, 8000 steps"

            response_2 = Mock()
            response_2.content = [text_block]

            mock_client = Mock()
            mock_client.messages.create.side_effect = [response_1, response_2]
            mock_anthropic.return_value = mock_client

            # Mock handlers
            totals_handler = AsyncMock(return_value={"calories": 1500})
            steps_handler = AsyncMock(return_value={"steps": 8000})

            client = ClaudeClient(api_key="test-key")
            response = await client.chat(
                message="summary",
                system="Test",
                tools=[
                    {"name": "get_today_totals", "description": "Get totals", "input_schema": {}},
                    {"name": "get_steps", "description": "Get steps", "input_schema": {}}
                ],
                tool_handlers={
                    "get_today_totals": totals_handler,
                    "get_steps": steps_handler
                }
            )

            # Both handlers called in same iteration
            totals_handler.assert_called_once()
            steps_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self):
        """Test that max iterations limit is respected."""
        from claude_client import ClaudeClient

        with patch('anthropic.Anthropic') as mock_anthropic:
            # Always return tool use (would loop forever without limit)
            tool_use = Mock()
            tool_use.type = "tool_use"
            tool_use.name = "endless_tool"
            tool_use.id = "call_1"
            tool_use.input = {}

            response = Mock()
            response.content = [tool_use]

            mock_client = Mock()
            mock_client.messages.create.return_value = response
            mock_anthropic.return_value = mock_client

            mock_handler = AsyncMock(return_value={"status": "ok"})

            client = ClaudeClient(api_key="test-key")
            result = await client.chat(
                message="loop",
                system="Test",
                tools=[{"name": "endless_tool", "description": "Test", "input_schema": {}}],
                tool_handlers={"endless_tool": mock_handler},
                max_iterations=3
            )

            # Should hit the limit message
            assert "limit" in result.lower()
            # Should have been called 3 times (max_iterations)
            assert mock_handler.call_count == 3

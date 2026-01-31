"""Integration tests for error scenarios."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import anthropic


class TestSupabaseFailure:
    """Test Supabase failure handling."""

    @pytest.mark.asyncio
    async def test_supabase_connection_failure(self):
        """Test graceful handling of Supabase connection failure."""
        from domains.nutrition.services.supabase_service import get_today_totals

        with patch('domains.nutrition.services.supabase_service._get_client') as mock_get_client:
            mock_get_client.side_effect = Exception("Connection refused")

            with pytest.raises(Exception) as exc_info:
                await get_today_totals()

            assert "Connection refused" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_supabase_query_failure(self):
        """Test handling of Supabase query failure."""
        from domains.nutrition.services.supabase_service import insert_meal

        with patch('domains.nutrition.services.supabase_service._get_client') as mock_get_client:
            mock_client = Mock()
            mock_table = Mock()
            mock_table.insert.return_value.execute.side_effect = Exception("Query failed")
            mock_client.table.return_value = mock_table
            mock_get_client.return_value = mock_client

            with pytest.raises(Exception) as exc_info:
                await insert_meal("breakfast", "eggs", 200, 15, 2, 14)

            assert "Query failed" in str(exc_info.value)


class TestGarminFailure:
    """Test Garmin API failure handling."""

    @pytest.mark.asyncio
    async def test_garmin_auth_failure(self):
        """Test handling of Garmin authentication failure."""
        from domains.nutrition.services.garmin import get_steps

        with patch('domains.nutrition.services.garmin._get_client') as mock_get_client:
            mock_get_client.side_effect = Exception("Authentication failed")

            result = await get_steps()

            # Should return error dict, not raise
            assert "error" in result
            assert result["steps"] is None

    @pytest.mark.asyncio
    async def test_garmin_api_timeout(self):
        """Test handling of Garmin API timeout."""
        from domains.nutrition.services.garmin import get_steps

        with patch('domains.nutrition.services.garmin._get_client') as mock_get_client:
            mock_client = Mock()
            mock_client.connectapi.side_effect = TimeoutError("Request timed out")
            mock_get_client.return_value = mock_client

            result = await get_steps()

            assert "error" in result
            assert result["steps"] is None


class TestWithingsTokenRefresh:
    """Test Withings token refresh flow."""

    @pytest.mark.asyncio
    async def test_withings_token_refresh_on_expiry(self):
        """Test token refresh when Withings returns expired status."""
        from domains.nutrition.services import withings

        # Reset tokens
        withings._tokens = {"access": "old_token", "refresh": "refresh_token"}

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()

            # First call: expired token (status != 0)
            expired_response = Mock()
            expired_response.json.return_value = {"status": 401}

            # Refresh call: success
            refresh_response = Mock()
            refresh_response.json.return_value = {
                "status": 0,
                "body": {
                    "access_token": "new_access_token",
                    "refresh_token": "new_refresh_token"
                }
            }

            # Retry call: success
            success_response = Mock()
            success_response.json.return_value = {
                "status": 0,
                "body": {
                    "measuregrps": [{
                        "date": 1704067200,
                        "measures": [{"value": 82500, "unit": -3}]
                    }]
                }
            }

            mock_client.post.side_effect = [expired_response, refresh_response, success_response]
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await withings.get_weight()

            # Should have refreshed and retried
            assert mock_client.post.call_count == 3
            assert result.get("weight_kg") == 82.5


class TestClaudeAPIFailure:
    """Test Claude API failure handling."""

    @pytest.mark.asyncio
    async def test_claude_api_error(self):
        """Test handling of Claude API error."""
        from claude_client import ClaudeClient

        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_client = Mock()
            mock_client.messages.create.side_effect = anthropic.APIError(
                message="Rate limit exceeded",
                request=Mock(),
                body={}
            )
            mock_anthropic.return_value = mock_client

            client = ClaudeClient(api_key="test-key")

            with pytest.raises(anthropic.APIError):
                await client.chat(
                    message="test",
                    system="test",
                    tools=[],
                    tool_handlers={}
                )

    @pytest.mark.asyncio
    async def test_claude_network_error(self):
        """Test handling of network error to Claude."""
        from claude_client import ClaudeClient

        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_client = Mock()
            mock_client.messages.create.side_effect = anthropic.APIConnectionError(
                request=Mock()
            )
            mock_anthropic.return_value = mock_client

            client = ClaudeClient(api_key="test-key")

            with pytest.raises(anthropic.APIConnectionError):
                await client.chat(
                    message="test",
                    system="test",
                    tools=[],
                    tool_handlers={}
                )


class TestToolExecutionFailure:
    """Test tool execution failure handling."""

    @pytest.mark.asyncio
    async def test_tool_raises_exception(self):
        """Test that tool exceptions are caught and returned as errors."""
        from claude_client import ClaudeClient

        with patch('anthropic.Anthropic') as mock_anthropic:
            # Response requesting tool
            tool_use = Mock()
            tool_use.type = "tool_use"
            tool_use.name = "failing_tool"
            tool_use.id = "call_1"
            tool_use.input = {}

            response_1 = Mock()
            response_1.content = [tool_use]

            # Final response after error
            text_block = Mock()
            text_block.type = "text"
            text_block.text = "The operation failed."

            response_2 = Mock()
            response_2.content = [text_block]

            mock_client = Mock()
            mock_client.messages.create.side_effect = [response_1, response_2]
            mock_anthropic.return_value = mock_client

            # Handler that raises
            async def failing_handler(**kwargs):
                raise ValueError("Database connection lost")

            client = ClaudeClient(api_key="test-key")
            response = await client.chat(
                message="test",
                system="test",
                tools=[{"name": "failing_tool", "description": "Test", "input_schema": {}}],
                tool_handlers={"failing_tool": failing_handler}
            )

            # Should still get a response (error was caught)
            assert response is not None

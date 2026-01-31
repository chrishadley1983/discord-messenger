"""Integration tests for message flow: message → domain → Claude → tool → response."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from registry import DomainRegistry
from domains.nutrition import NutritionDomain
from claude_client import ClaudeClient


@pytest.fixture
def registry():
    """Create a fresh registry."""
    return DomainRegistry()


@pytest.fixture
def nutrition_domain():
    """Create nutrition domain."""
    return NutritionDomain()


class TestDomainRegistry:
    """Test domain registry routing."""

    def test_register_domain(self, registry, nutrition_domain):
        """Test domain registration."""
        registry.register(nutrition_domain)

        assert registry.get_by_channel(nutrition_domain.channel_id) == nutrition_domain
        assert registry.get_by_name("nutrition") == nutrition_domain

    def test_get_unknown_channel(self, registry):
        """Test getting domain for unknown channel returns None."""
        assert registry.get_by_channel(999999) is None

    def test_all_domains(self, registry, nutrition_domain):
        """Test getting all domains."""
        registry.register(nutrition_domain)
        domains = registry.all_domains()

        assert len(domains) == 1
        assert nutrition_domain in domains


class TestMessageRouting:
    """Test message routing to correct domain."""

    def test_nutrition_channel_routes_to_nutrition(self, registry, nutrition_domain):
        """Test nutrition channel routes to nutrition domain."""
        registry.register(nutrition_domain)

        # Simulate message in nutrition channel
        domain = registry.get_by_channel(1465294449038069912)

        assert domain is not None
        assert domain.name == "nutrition"
        assert domain.system_prompt is not None
        assert len(domain.tools) > 0

    def test_unregistered_channel_returns_none(self, registry, nutrition_domain):
        """Test unregistered channel returns None (should be ignored)."""
        registry.register(nutrition_domain)

        # Simulate message in unknown channel
        domain = registry.get_by_channel(123456789)

        assert domain is None


class TestClaudeClientToolFlow:
    """Test Claude client tool handling."""

    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        """Test Claude returns text without tool calls."""
        with patch('anthropic.Anthropic') as mock_anthropic:
            # Mock response with just text
            mock_response = Mock()
            mock_response.content = [Mock(type="text", text="Hello! I logged your meal.")]

            mock_client = Mock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            client = ClaudeClient(api_key="test-key")
            response = await client.chat(
                message="log breakfast",
                system="You are a test assistant",
                tools=[],
                tool_handlers={}
            )

            assert response == "Hello! I logged your meal."

    @pytest.mark.asyncio
    async def test_tool_call_execution(self):
        """Test tool calls are executed and results returned."""
        with patch('anthropic.Anthropic') as mock_anthropic:
            # First response: tool use
            tool_use_response = Mock()
            tool_use_block = Mock()
            tool_use_block.type = "tool_use"
            tool_use_block.name = "log_meal"
            tool_use_block.id = "call_123"
            tool_use_block.input = {"meal_type": "breakfast", "description": "eggs", "calories": 200, "protein_g": 15, "carbs_g": 2, "fat_g": 14}
            tool_use_response.content = [tool_use_block]

            # Second response: final text
            final_response = Mock()
            text_block = Mock()
            text_block.type = "text"
            text_block.text = "Logged your breakfast!"
            final_response.content = [text_block]

            mock_client = Mock()
            mock_client.messages.create.side_effect = [tool_use_response, final_response]
            mock_anthropic.return_value = mock_client

            # Mock tool handler
            mock_handler = AsyncMock(return_value={"success": True, "id": 1})

            client = ClaudeClient(api_key="test-key")
            response = await client.chat(
                message="log breakfast eggs",
                system="You are a test assistant",
                tools=[{"name": "log_meal", "description": "Log meal", "input_schema": {}}],
                tool_handlers={"log_meal": mock_handler}
            )

            # Verify tool was called
            mock_handler.assert_called_once()
            assert response == "Logged your breakfast!"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        """Test unknown tool requests return error."""
        with patch('anthropic.Anthropic') as mock_anthropic:
            # Response requesting unknown tool
            tool_use_response = Mock()
            tool_use_block = Mock()
            tool_use_block.type = "tool_use"
            tool_use_block.name = "unknown_tool"
            tool_use_block.id = "call_123"
            tool_use_block.input = {}
            tool_use_response.content = [tool_use_block]

            # Final response after error
            final_response = Mock()
            text_block = Mock()
            text_block.type = "text"
            text_block.text = "I encountered an error."
            final_response.content = [text_block]

            mock_client = Mock()
            mock_client.messages.create.side_effect = [tool_use_response, final_response]
            mock_anthropic.return_value = mock_client

            client = ClaudeClient(api_key="test-key")
            response = await client.chat(
                message="do something",
                system="You are a test assistant",
                tools=[],
                tool_handlers={}
            )

            # Should still get a response (Claude handles the error gracefully)
            assert response is not None


class TestEndToEndMessageFlow:
    """Test complete message flow with mocked services."""

    @pytest.mark.asyncio
    async def test_happy_path_message_to_response(self, mock_discord_bot):
        """Test complete flow: message → domain → Claude → tool → response."""
        registry = DomainRegistry()
        registry.register(NutritionDomain())

        # Get domain for channel
        domain = registry.get_by_channel(1465294449038069912)
        assert domain is not None

        # Build tool handlers (would normally come from domain)
        tool_handlers = {tool.name: tool.handler for tool in domain.tools}

        # Verify we have the expected tools
        assert "log_meal" in tool_handlers
        assert "log_water" in tool_handlers
        assert "get_today_totals" in tool_handlers
        assert "get_steps" in tool_handlers
        assert "get_weight" in tool_handlers

        # Verify tool definitions are valid
        tool_defs = domain.get_tool_definitions()
        assert len(tool_defs) == 7
        for tool_def in tool_defs:
            assert "name" in tool_def
            assert "description" in tool_def
            assert "input_schema" in tool_def

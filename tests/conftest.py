"""Pytest configuration and fixtures."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_discord_bot():
    """Create a mock Discord bot."""
    bot = Mock()
    bot.get_channel = Mock(return_value=Mock(
        send=AsyncMock(),
        typing=Mock(return_value=AsyncMock())
    ))
    bot.user = Mock(name="TestBot#1234")
    return bot


@pytest.fixture
def mock_anthropic_client():
    """Create a mock Anthropic client."""
    with patch('anthropic.Anthropic') as mock:
        client = Mock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_supabase_client():
    """Create a mock Supabase client."""
    with patch('supabase.create_client') as mock:
        client = Mock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx client."""
    with patch('httpx.AsyncClient') as mock:
        client = AsyncMock()
        mock.return_value.__aenter__.return_value = client
        yield client

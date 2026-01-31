"""Tests for the Peterbot domain and messages endpoint integration."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import aiohttp


class TestPeterbotDomain:
    """Tests for PeterbotDomain class."""

    @pytest.fixture
    def domain(self):
        """Create a PeterbotDomain instance."""
        with patch.dict('os.environ', {'PETERBOT_CHANNEL_ID': '123456'}):
            from domains.peterbot import PeterbotDomain
            return PeterbotDomain()

    def test_domain_name(self, domain):
        """Domain should have correct name."""
        assert domain.name == "peterbot"

    def test_domain_channel_id(self, domain):
        """Domain should read channel ID from environment."""
        assert domain.channel_id == 123456

    def test_domain_has_system_prompt(self, domain):
        """Domain should have a system prompt."""
        assert domain.system_prompt
        assert "Peter" in domain.system_prompt
        assert len(domain.system_prompt) > 100

    def test_domain_no_tools(self, domain):
        """Domain should have no special tools."""
        assert domain.tools == []


class TestSendToMemory:
    """Tests for send_to_memory method."""

    @pytest.fixture
    def domain(self):
        """Create a PeterbotDomain instance."""
        with patch.dict('os.environ', {'PETERBOT_CHANNEL_ID': '123456'}):
            from domains.peterbot import PeterbotDomain
            return PeterbotDomain()

    @pytest.mark.asyncio
    async def test_send_to_memory_success(self, domain):
        """Should return True when API returns 202."""
        mock_response = MagicMock()
        mock_response.status = 202

        with patch('domains.peterbot.domain.aiohttp.ClientSession') as mock_session:
            mock_post_ctx = MagicMock()
            mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_ctx.__aexit__ = AsyncMock(return_value=None)

            mock_session_ctx = MagicMock()
            mock_session_ctx.post = MagicMock(return_value=mock_post_ctx)

            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_session_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await domain.send_to_memory(
                content_session_id="test-123",
                user_message="Hello world",
                assistant_response="Hi there!"
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_send_to_memory_api_error(self, domain):
        """Should return False when API returns error."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal error")

        with patch('aiohttp.ClientSession') as mock_session:
            mock_ctx = AsyncMock()
            mock_ctx.post.return_value.__aenter__.return_value = mock_response
            mock_session.return_value.__aenter__.return_value = mock_ctx

            result = await domain.send_to_memory(
                content_session_id="test-123",
                user_message="Hello world",
                assistant_response="Hi there!"
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_send_to_memory_connection_error(self, domain):
        """Should return False when connection fails."""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_ctx = AsyncMock()
            mock_ctx.post.side_effect = aiohttp.ClientError("Connection failed")
            mock_session.return_value.__aenter__.return_value = mock_ctx

            result = await domain.send_to_memory(
                content_session_id="test-123",
                user_message="Hello world",
                assistant_response="Hi there!"
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_send_to_memory_empty_message_skipped(self, domain):
        """Should return False for empty messages."""
        result = await domain.send_to_memory(
            content_session_id="test-123",
            user_message="",
            assistant_response="Hi there!"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_to_memory_whitespace_message_skipped(self, domain):
        """Should return False for whitespace-only messages."""
        result = await domain.send_to_memory(
            content_session_id="test-123",
            user_message="   \n\t  ",
            assistant_response="Hi there!"
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_to_memory_no_channel_id(self):
        """Should return False when PETERBOT_CHANNEL_ID not set."""
        with patch.dict('os.environ', {'PETERBOT_CHANNEL_ID': '123456'}):
            from domains.peterbot import PeterbotDomain
            domain = PeterbotDomain()

            # Patch the module-level CHANNEL_ID to 0
            with patch('domains.peterbot.domain.CHANNEL_ID', 0):
                result = await domain.send_to_memory(
                    content_session_id="test-123",
                    user_message="Hello",
                    assistant_response="Hi"
                )
                assert result is False

    @pytest.mark.asyncio
    async def test_send_to_memory_truncates_long_message(self, domain):
        """Should truncate messages exceeding max length."""
        long_message = "x" * 15000  # Exceeds MAX_USER_MESSAGE of 10000

        mock_response = MagicMock()
        mock_response.status = 202

        captured_payload = {}

        def capture_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            mock_post_ctx = MagicMock()
            mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post_ctx.__aexit__ = AsyncMock(return_value=None)
            return mock_post_ctx

        with patch('domains.peterbot.domain.aiohttp.ClientSession') as mock_session:
            mock_session_ctx = MagicMock()
            mock_session_ctx.post = capture_post

            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_session_ctx)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await domain.send_to_memory(
                content_session_id="test-123",
                user_message=long_message,
                assistant_response="Hi"
            )

            assert result is True
            # Check message was truncated
            assert len(captured_payload['userMessage']) < len(long_message)
            assert "[truncated]" in captured_payload['userMessage']


class TestMessagesEndpointIntegration:
    """Integration tests for the /api/sessions/messages endpoint."""

    @pytest.mark.asyncio
    async def test_messages_endpoint_accepts_valid_request(self):
        """Test that a valid request returns 202."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    "http://localhost:37777/api/sessions/messages",
                    json={
                        "contentSessionId": "pytest-test-123",
                        "source": "pytest",
                        "channel": "test",
                        "userMessage": "Test message from pytest",
                        "assistantResponse": "Test response"
                    },
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    assert resp.status == 202
                    data = await resp.json()
                    assert data["status"] == "queued"
            except aiohttp.ClientError:
                pytest.skip("Worker not running - skipping integration test")

    @pytest.mark.asyncio
    async def test_messages_endpoint_rejects_missing_session_id(self):
        """Test that missing contentSessionId returns 400."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    "http://localhost:37777/api/sessions/messages",
                    json={
                        "source": "pytest",
                        "userMessage": "Test message"
                    },
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    assert resp.status == 400
            except aiohttp.ClientError:
                pytest.skip("Worker not running - skipping integration test")

    @pytest.mark.asyncio
    async def test_messages_endpoint_rejects_missing_user_message(self):
        """Test that missing userMessage returns 400."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    "http://localhost:37777/api/sessions/messages",
                    json={
                        "contentSessionId": "pytest-test-123",
                        "source": "pytest"
                    },
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    assert resp.status == 400
            except aiohttp.ClientError:
                pytest.skip("Worker not running - skipping integration test")

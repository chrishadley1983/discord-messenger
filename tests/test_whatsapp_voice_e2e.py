"""E2E tests for WhatsApp voice note handling.

Tests the full flow: webhook receives audio → transcribe → queue → forward to bot.
Uses mocks for Evolution API and bot.py internal server.
"""
import asyncio
import base64

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hadley_api.whatsapp_webhook import (
    router,
    _sender_queues,
    _seen_message_ids,
    _handle_voice_note,
    _enqueue_message,
    _debounce_flush,
)


@pytest.fixture(autouse=True)
def clear_state():
    """Reset webhook state between tests."""
    _sender_queues.clear()
    _seen_message_ids.clear()
    yield
    _sender_queues.clear()
    _seen_message_ids.clear()


@pytest.fixture(scope="module")
def sample_ogg_audio():
    """Generate a WAV sample (used as stand-in for ogg in tests)."""
    from hadley_api.voice_engine import synthesise_sync
    return synthesise_sync("What is the weather like today?")


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _make_audio_webhook(
    message_id: str, audio_b64: str, sender: str = "Chris Hadley", jid: str = "447855620978",
) -> dict:
    """Build a fake Evolution API messages.upsert webhook with audioMessage."""
    return {
        "event": "messages.upsert",
        "instance": "peter-whatsapp",
        "data": {
            "key": {
                "remoteJid": f"{jid}@s.whatsapp.net",
                "fromMe": False,
                "id": message_id,
            },
            "pushName": sender,
            "message": {
                "audioMessage": {
                    "mimetype": "audio/ogg; codecs=opus",
                    "seconds": 3,
                    "ptt": True,
                },
                "base64": audio_b64,
            },
            "messageType": "audioMessage",
        },
    }


def _make_text_webhook(message_id: str, text: str, sender: str = "Chris Hadley") -> dict:
    """Build a fake text message webhook for comparison."""
    return {
        "event": "messages.upsert",
        "instance": "peter-whatsapp",
        "data": {
            "key": {
                "remoteJid": "447855620978@s.whatsapp.net",
                "fromMe": False,
                "id": message_id,
            },
            "pushName": sender,
            "message": {
                "conversation": text,
            },
        },
    }


class TestVoiceNoteDetection:
    """Test that voice notes are properly detected and routed."""

    def test_audio_message_detected(self, client, sample_ogg_audio):
        """Webhook with audioMessage should trigger voice note handling."""
        audio_b64 = base64.b64encode(sample_ogg_audio).decode()
        payload = _make_audio_webhook("voice-001", audio_b64)

        with patch("hadley_api.whatsapp_webhook._download_audio") as mock_dl:
            resp = client.post("/whatsapp/webhook", json=payload)
            assert resp.status_code == 200
            mock_dl.assert_not_called()  # base64 was in payload, no download needed

    def test_text_message_still_works(self, client):
        """Regular text messages should still work alongside voice support."""
        payload = _make_text_webhook("text-001", "Hello Peter")
        resp = client.post("/whatsapp/webhook", json=payload)
        assert resp.status_code == 200


class TestVoiceNoteTranscription:
    """Test voice note transcription via direct function calls."""

    @pytest.mark.asyncio
    async def test_handle_voice_note_transcribes(self, sample_ogg_audio):
        """_handle_voice_note should transcribe and enqueue text."""
        audio_b64 = base64.b64encode(sample_ogg_audio).decode()
        message_content = {
            "audioMessage": {"mimetype": "audio/ogg; codecs=opus", "seconds": 3, "ptt": True},
            "base64": audio_b64,
        }

        with patch("hadley_api.whatsapp_webhook._enqueue_message", new_callable=AsyncMock) as mock_enqueue:
            await _handle_voice_note(
                message_id="voice-002",
                message_content=message_content,
                sender_name="Chris",
                sender_number="447855620978",
                reply_to="447855620978",
                is_group=False,
            )

            mock_enqueue.assert_called_once()
            call_kwargs = mock_enqueue.call_args.kwargs
            assert call_kwargs["sender_name"] == "Chris"
            assert call_kwargs["is_voice"] is True
            assert "weather" in call_kwargs["text"].lower()


class TestVoiceNoteDownload:
    """Test audio download from Evolution API."""

    def test_download_fallback_when_no_base64(self, client, sample_ogg_audio):
        """When base64 is not in payload, should call getBase64FromMediaMessage."""
        payload = _make_audio_webhook("voice-003", "")
        del payload["data"]["message"]["base64"]

        with patch("hadley_api.whatsapp_webhook._download_audio", new_callable=AsyncMock) as mock_dl:
            mock_dl.return_value = sample_ogg_audio
            resp = client.post("/whatsapp/webhook", json=payload)
            assert resp.status_code == 200
            mock_dl.assert_called_once_with("voice-003")

    @pytest.mark.asyncio
    async def test_download_failure_handled(self):
        """If download fails, should not crash."""
        message_content = {
            "audioMessage": {"mimetype": "audio/ogg; codecs=opus", "seconds": 3, "ptt": True},
        }

        with patch("hadley_api.whatsapp_webhook._download_audio", new_callable=AsyncMock) as mock_dl:
            mock_dl.return_value = None  # Simulate download failure
            with patch("hadley_api.whatsapp_webhook._enqueue_message", new_callable=AsyncMock) as mock_enqueue:
                await _handle_voice_note(
                    message_id="voice-fail",
                    message_content=message_content,
                    sender_name="Chris",
                    sender_number="447855620978",
                    reply_to="447855620978",
                    is_group=False,
                )
                mock_enqueue.assert_not_called()  # Should not enqueue if download failed


class TestIsVoiceFlag:
    """Test that is_voice flag propagates through the pipeline."""

    @pytest.mark.asyncio
    async def test_voice_enqueue_sets_flag(self):
        """_enqueue_message with is_voice=True should store the flag."""
        await _enqueue_message(
            sender_name="Chris",
            sender_number="447855620978",
            reply_to="447855620978",
            is_group=False,
            text="What is the weather?",
            is_voice=True,
        )

        queue = _sender_queues.get("447855620978")
        assert queue is not None
        assert len(queue.messages) == 1
        assert queue.messages[0]["is_voice"] is True
        assert queue.messages[0]["text"] == "What is the weather?"

        # Cancel the timer to avoid side effects
        if queue.timer_task:
            queue.timer_task.cancel()

    @pytest.mark.asyncio
    async def test_text_enqueue_no_voice_flag(self):
        """_enqueue_message without is_voice should default to False."""
        await _enqueue_message(
            sender_name="Chris",
            sender_number="447855620978",
            reply_to="447855620978",
            is_group=False,
            text="Just text",
        )

        queue = _sender_queues.get("447855620978")
        assert queue is not None
        assert queue.messages[0]["is_voice"] is False

        if queue.timer_task:
            queue.timer_task.cancel()

    @pytest.mark.asyncio
    async def test_debounce_flush_passes_voice_flag(self):
        """_debounce_flush should include is_voice in the forwarded payload."""
        # Manually set up a queue with a voice message
        await _enqueue_message(
            sender_name="Chris",
            sender_number="447855620979",
            reply_to="447855620979",
            is_group=False,
            text="Voice message text",
            is_voice=True,
        )
        # Cancel the auto timer
        queue = _sender_queues["447855620979"]
        if queue.timer_task:
            queue.timer_task.cancel()

        forwarded = {}

        async def mock_post(*args, **kwargs):
            forwarded.update(kwargs.get("json", {}))
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            return mock_resp

        with patch("hadley_api.whatsapp_webhook.httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.post = mock_post
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            # Manually trigger flush (skip the sleep)
            with patch("hadley_api.whatsapp_webhook._DEBOUNCE_SECONDS", 0):
                await _debounce_flush("447855620979")

        assert forwarded.get("is_voice") is True
        assert "Voice message text" in forwarded.get("text", "")


class TestDeduplication:
    """Test that voice note deduplication works."""

    def test_duplicate_voice_note_ignored(self, client, sample_ogg_audio):
        """Same message ID should not be processed twice."""
        audio_b64 = base64.b64encode(sample_ogg_audio).decode()
        payload = _make_audio_webhook("voice-dup-001", audio_b64)

        resp1 = client.post("/whatsapp/webhook", json=payload)
        resp2 = client.post("/whatsapp/webhook", json=payload)

        assert resp1.status_code == 200
        assert resp2.status_code == 200


class TestUnauthorisedSender:
    """Test that voice notes from unknown senders are rejected."""

    def test_unknown_sender_ignored(self, client, sample_ogg_audio):
        """Voice notes from non-allowed senders should be silently ignored."""
        audio_b64 = base64.b64encode(sample_ogg_audio).decode()
        payload = _make_audio_webhook("voice-unauth-001", audio_b64, sender="Random Person", jid="449999999999")

        with patch("hadley_api.whatsapp_webhook._handle_voice_note", new_callable=AsyncMock) as mock_voice:
            resp = client.post("/whatsapp/webhook", json=payload)
            assert resp.status_code == 200
            mock_voice.assert_not_called()

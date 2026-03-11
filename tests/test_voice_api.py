"""E2E tests for voice API endpoints."""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hadley_api.voice_routes import router, AUDIO_DIR


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(scope="module")
def sample_audio(client):
    """Generate a TTS sample to use in listen tests."""
    resp = client.post("/voice/speak", json={"text": "Hello, this is a test message for Peter."})
    assert resp.status_code == 200
    return resp.content


class TestVoiceListen:
    """POST /voice/listen tests."""

    def test_transcribe_wav(self, client, sample_audio):
        resp = client.post(
            "/voice/listen",
            content=sample_audio,
            headers={"Content-Type": "audio/wav"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "text" in data
        assert len(data["text"]) > 0
        assert "hello" in data["text"].lower()

    def test_empty_body_returns_400(self, client):
        resp = client.post("/voice/listen", content=b"", headers={"Content-Type": "audio/wav"})
        assert resp.status_code == 400

    def test_corrupt_audio_returns_500(self, client):
        resp = client.post(
            "/voice/listen",
            content=b"not real audio data",
            headers={"Content-Type": "audio/wav"},
        )
        assert resp.status_code == 500

    def test_format_detection(self, client, sample_audio):
        resp = client.post(
            "/voice/listen",
            content=sample_audio,
            headers={"Content-Type": "audio/wav"},
        )
        assert resp.json()["format_detected"] == "wav"


class TestVoiceSpeak:
    """POST /voice/speak tests."""

    def test_synthesise_default_voice(self, client):
        resp = client.post("/voice/speak", json={"text": "Good morning."})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert resp.content[:4] == b"RIFF"
        assert len(resp.content) > 1000

    def test_custom_voice(self, client):
        resp = client.post("/voice/speak", json={"text": "Test.", "voice": "bm_daniel"})
        assert resp.status_code == 200
        assert resp.content[:4] == b"RIFF"

    def test_custom_speed(self, client):
        resp = client.post("/voice/speak", json={"text": "Speed test.", "speed": 1.5})
        assert resp.status_code == 200

    def test_empty_text_returns_400(self, client):
        resp = client.post("/voice/speak", json={"text": ""})
        assert resp.status_code == 400

    def test_missing_text_returns_422(self, client):
        resp = client.post("/voice/speak", json={})
        assert resp.status_code == 422


class TestVoiceAudio:
    """GET /voice/audio/<filename> tests."""

    def test_serve_existing_file(self, client):
        # Create a test file
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        test_file = AUDIO_DIR / "test123.wav"
        test_file.write_bytes(b"RIFF" + b"\x00" * 100)

        resp = client.get("/voice/audio/test123.wav")
        assert resp.status_code == 200
        assert resp.content[:4] == b"RIFF"

        # Cleanup
        test_file.unlink(missing_ok=True)

    def test_missing_file_returns_404(self, client):
        resp = client.get("/voice/audio/nonexistent.wav")
        assert resp.status_code == 404

    def test_path_traversal_blocked(self, client):
        # FastAPI normalises path traversal, so this hits 400 or 404 (never serves /etc/passwd)
        resp = client.get("/voice/audio/../../../etc/passwd")
        assert resp.status_code in (400, 404)
        # Also test with special chars
        resp2 = client.get("/voice/audio/;rm -rf /")
        assert resp2.status_code in (400, 404)


class TestVoiceVoices:
    """GET /voice/voices tests."""

    def test_list_voices(self, client):
        resp = client.get("/voice/voices")
        assert resp.status_code == 200
        data = resp.json()
        assert "default" in data
        assert "british_male" in data
        assert "all" in data
        assert data["default"] == "bm_daniel"
        assert len(data["british_male"]) >= 4


class TestRoundTrip:
    """Full STT → TTS round-trip test."""

    def test_speak_then_listen(self, client):
        # Synthesise
        speak_resp = client.post("/voice/speak", json={"text": "What is the weather like today?"})
        assert speak_resp.status_code == 200

        # Transcribe
        listen_resp = client.post(
            "/voice/listen",
            content=speak_resp.content,
            headers={"Content-Type": "audio/wav"},
        )
        assert listen_resp.status_code == 200
        text = listen_resp.json()["text"].lower()
        assert "weather" in text

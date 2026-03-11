"""Unit tests for the voice engine (STT + TTS)."""
import io
import struct

import pytest


@pytest.fixture(scope="module")
def sample_wav():
    """Generate a TTS sample to use as STT input."""
    from hadley_api.voice_engine import synthesise_sync
    return synthesise_sync("Testing one two three.")


class TestSynthesise:
    """TTS synthesis tests."""

    def test_returns_valid_wav(self):
        from hadley_api.voice_engine import synthesise_sync
        wav = synthesise_sync("Hello world.")
        # WAV files start with RIFF header
        assert wav[:4] == b"RIFF", "Output should be a WAV file"
        assert wav[8:12] == b"WAVE"
        assert len(wav) > 1000, "WAV should have meaningful content"

    def test_all_british_male_voices(self):
        from hadley_api.voice_engine import synthesise_sync
        for voice in ["bm_daniel", "bm_fable", "bm_george", "bm_lewis"]:
            wav = synthesise_sync("Quick test.", voice=voice)
            assert wav[:4] == b"RIFF", f"Voice {voice} should produce valid WAV"
            assert len(wav) > 500

    def test_empty_text_raises(self):
        from hadley_api.voice_engine import synthesise_sync
        with pytest.raises(Exception):
            synthesise_sync("")

    def test_long_text(self):
        from hadley_api.voice_engine import synthesise_sync
        long_text = "This is a longer sentence that Peter might say. " * 5
        wav = synthesise_sync(long_text)
        assert len(wav) > 10000, "Long text should produce substantial audio"

    def test_speed_parameter(self):
        from hadley_api.voice_engine import synthesise_sync
        normal = synthesise_sync("Speed test.", speed=1.0)
        fast = synthesise_sync("Speed test.", speed=1.5)
        # Faster speech should produce shorter audio
        assert len(fast) < len(normal)


class TestTranscribe:
    """STT transcription tests."""

    def test_round_trip(self, sample_wav):
        from hadley_api.voice_engine import transcribe_sync
        text = transcribe_sync(sample_wav, source_format="wav")
        # Should contain the key words (exact match varies)
        lower = text.lower()
        assert "testing" in lower or "test" in lower
        assert "one" in lower or "1" in lower
        assert "two" in lower or "2" in lower
        assert "three" in lower or "3" in lower

    def test_returns_string(self, sample_wav):
        from hadley_api.voice_engine import transcribe_sync
        text = transcribe_sync(sample_wav, source_format="wav")
        assert isinstance(text, str)
        assert len(text) > 0

    def test_corrupt_audio_raises(self):
        from hadley_api.voice_engine import transcribe_sync
        with pytest.raises(Exception):
            transcribe_sync(b"not audio data", source_format="wav")


class TestVoicesList:
    """Voice listing tests."""

    def test_get_voices(self):
        from hadley_api.voice_engine import get_available_voices
        voices = get_available_voices()
        assert isinstance(voices, list)
        assert "bm_george" in voices
        assert "bm_daniel" in voices
        british_male = [v for v in voices if v.startswith("bm_")]
        assert len(british_male) >= 4


class TestModelLoading:
    """Test lazy loading behaviour."""

    def test_whisper_singleton(self):
        from hadley_api.voice_engine import _get_whisper
        model1 = _get_whisper()
        model2 = _get_whisper()
        assert model1 is model2, "Should return same instance"

    def test_kokoro_singleton(self):
        from hadley_api.voice_engine import _get_kokoro
        k1 = _get_kokoro()
        k2 = _get_kokoro()
        assert k1 is k2, "Should return same instance"

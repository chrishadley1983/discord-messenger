"""Tests for chunking module."""

import pytest
from domains.second_brain.chunk import chunk_text, chunk_for_embedding, estimate_chunks
from domains.second_brain.config import CHUNK_SIZE, CHUNK_OVERLAP


class TestChunking:
    """Test text chunking functionality."""

    def test_short_text_not_chunked(self):
        """Short text should return as single chunk."""
        text = "This is a short text."
        chunks = chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_empty_text(self):
        """Empty text should return empty list."""
        chunks = chunk_text("")
        assert chunks == []

    def test_whitespace_only(self):
        """Whitespace-only text should return empty list."""
        chunks = chunk_text("   \n\t  ")
        assert chunks == []

    def test_long_text_chunked(self):
        """Long text should be split into multiple chunks."""
        # Create text with more than CHUNK_SIZE words
        text = "word " * (CHUNK_SIZE + 100)
        chunks = chunk_text(text)
        assert len(chunks) >= 2

    def test_chunk_word_count(self):
        """Each chunk should have reasonable word count."""
        text = "This is a word. " * 200
        chunks = chunk_text(text)

        for chunk in chunks:
            # Should not vastly exceed CHUNK_SIZE
            assert chunk.word_count <= CHUNK_SIZE * 1.5

    def test_chunks_have_indices(self):
        """Chunks should have sequential indices."""
        text = "word " * 500
        chunks = chunk_text(text)

        for i, chunk in enumerate(chunks):
            assert chunk.index == i

    def test_no_empty_chunks(self):
        """Should not produce empty chunks."""
        text = "\n\n\n".join(["Some text here."] * 10)
        chunks = chunk_text(text)

        for chunk in chunks:
            assert chunk.text.strip()
            assert chunk.word_count > 0

    def test_unicode_handling(self):
        """Should handle unicode properly."""
        text = "Hello 世界! " * 100 + "This is émoji: 🎉 " * 50
        chunks = chunk_text(text)

        assert len(chunks) >= 1
        # All unicode should be preserved
        full_text = " ".join(c.text for c in chunks)
        assert "世界" in full_text
        assert "🎉" in full_text


class TestChunkForEmbedding:
    """Test chunk_for_embedding function."""

    def test_returns_strings(self):
        """Should return list of strings."""
        text = "This is test content."
        chunks = chunk_for_embedding(text)

        assert isinstance(chunks, list)
        assert all(isinstance(c, str) for c in chunks)

    def test_title_prepended(self):
        """Title should be prepended when provided."""
        text = "This is test content."
        title = "Test Title"
        chunks = chunk_for_embedding(text, title=title)

        assert chunks[0].startswith(f"Title: {title}")

    def test_no_title(self):
        """Should work without title."""
        text = "This is test content."
        chunks = chunk_for_embedding(text)

        assert chunks[0] == text


class TestEstimateChunks:
    """Test chunk estimation."""

    def test_small_text_one_chunk(self):
        """Small text should estimate 1 chunk."""
        assert estimate_chunks(100) == 1
        assert estimate_chunks(CHUNK_SIZE) == 1

    def test_large_text_multiple_chunks(self):
        """Large text should estimate multiple chunks."""
        word_count = CHUNK_SIZE * 3
        estimate = estimate_chunks(word_count)
        assert estimate >= 2

    def test_zero_words(self):
        """Zero words should estimate 1 chunk."""
        assert estimate_chunks(0) == 1

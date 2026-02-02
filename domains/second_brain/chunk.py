"""Text chunking for Second Brain.

Splits content into ~300 word segments with 50 word overlap.
Split priority: paragraph > sentence > whitespace.
"""

import re
from dataclasses import dataclass

from .config import CHUNK_SIZE, CHUNK_OVERLAP


@dataclass
class TextChunk:
    """A chunk of text with position info."""
    text: str
    index: int
    start_word: int
    end_word: int
    word_count: int


def chunk_text(text: str) -> list[TextChunk]:
    """Split text into overlapping chunks.

    Args:
        text: Full text to chunk

    Returns:
        List of TextChunk objects with ~300 words each, 50 word overlap
    """
    if not text or not text.strip():
        return []

    # Split into words while preserving structure
    words = text.split()
    total_words = len(words)

    if total_words <= CHUNK_SIZE:
        # Single chunk - no splitting needed
        return [TextChunk(
            text=text.strip(),
            index=0,
            start_word=0,
            end_word=total_words,
            word_count=total_words,
        )]

    chunks = []
    chunk_index = 0
    position = 0

    while position < total_words:
        # Calculate end position
        end_pos = min(position + CHUNK_SIZE, total_words)

        # Get the chunk words
        chunk_words = words[position:end_pos]
        chunk_text = ' '.join(chunk_words)

        # Try to find a better break point if not at end
        if end_pos < total_words:
            chunk_text = _find_best_break(chunk_text, chunk_words)
            # Recalculate actual word count after break adjustment
            actual_words = chunk_text.split()
            end_pos = position + len(actual_words)

        chunks.append(TextChunk(
            text=chunk_text.strip(),
            index=chunk_index,
            start_word=position,
            end_word=end_pos,
            word_count=len(chunk_text.split()),
        ))

        chunk_index += 1

        # Move position forward, accounting for overlap
        # If we're at the end, break
        if end_pos >= total_words:
            break

        # Next chunk starts CHUNK_OVERLAP words before the end of this chunk
        position = max(position + 1, end_pos - CHUNK_OVERLAP)

    return chunks


def _find_best_break(chunk_text: str, chunk_words: list[str]) -> str:
    """Find the best break point in a chunk.

    Priority:
    1. End of paragraph (double newline)
    2. End of sentence (. ! ?)
    3. End of clause (, ; :)
    4. Whitespace (keep as-is)
    """
    # Look for paragraph break in last 20% of chunk
    cutoff = int(len(chunk_text) * 0.8)
    last_portion = chunk_text[cutoff:]

    # Try paragraph break
    para_match = re.search(r'\n\n', last_portion)
    if para_match:
        break_pos = cutoff + para_match.end()
        return chunk_text[:break_pos].strip()

    # Try sentence break (look for . ! ? followed by space or end)
    sentence_matches = list(re.finditer(r'[.!?]\s+', last_portion))
    if sentence_matches:
        # Use the last sentence break
        last_match = sentence_matches[-1]
        break_pos = cutoff + last_match.end()
        return chunk_text[:break_pos].strip()

    # Try clause break
    clause_matches = list(re.finditer(r'[,;:]\s+', last_portion))
    if clause_matches:
        last_match = clause_matches[-1]
        break_pos = cutoff + last_match.end()
        return chunk_text[:break_pos].strip()

    # No good break point found, return as-is
    return chunk_text


def chunk_for_embedding(text: str, title: str | None = None) -> list[str]:
    """Chunk text for embedding generation.

    Prepends title context to each chunk for better semantic matching.

    Args:
        text: Full text to chunk
        title: Optional title to prepend for context

    Returns:
        List of text strings ready for embedding
    """
    chunks = chunk_text(text)

    if not title:
        return [c.text for c in chunks]

    # Prepend title context to each chunk
    prefix = f"Title: {title}\n\n"
    return [prefix + c.text for c in chunks]


def estimate_chunks(word_count: int) -> int:
    """Estimate number of chunks for a given word count.

    Useful for cost estimation before processing.
    """
    if word_count <= CHUNK_SIZE:
        return 1

    # Account for overlap
    effective_chunk_size = CHUNK_SIZE - CHUNK_OVERLAP
    return 1 + ((word_count - CHUNK_SIZE) // effective_chunk_size) + 1

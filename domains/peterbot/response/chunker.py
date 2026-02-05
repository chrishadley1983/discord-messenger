"""Chunker - Stage 4 of the Response Processing Pipeline.

Splits formatted content into Discord-safe message segments.
Based on RESPONSE.md Section 6.
"""

import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


# Discord limits (Section 6.1)
DISCORD_MESSAGE_LIMIT = 2000
DISCORD_EMBED_TITLE_LIMIT = 256
DISCORD_EMBED_DESC_LIMIT = 4096
DISCORD_EMBED_FIELD_LIMIT = 1024
DISCORD_EMBED_FIELDS_MAX = 25
DISCORD_EMBEDS_PER_MESSAGE = 10
DISCORD_TOTAL_EMBED_CHARS = 6000


class SplitPriority(IntEnum):
    """Priority order for split points (Section 6.2)."""
    PARAGRAPH = 1    # Split on \n\n (preferred)
    NEWLINE = 2      # Split on \n
    SENTENCE = 3     # Split on '. ' or '.\n'
    WHITESPACE = 4   # Split on ' '
    HARD_BREAK = 5   # Split at max_chars (last resort)


@dataclass
class ChunkerConfig:
    """Configuration for chunking behaviour."""
    max_chars: int = 1900          # Leave buffer below 2000
    max_lines_per_message: int = 20  # Prevent visual overwhelm
    min_chars: int = 200           # Don't send tiny fragments
    add_chunk_numbers: bool = True  # Add (1/3) markers for 3+ chunks


def chunk(
    text: str,
    config: Optional[ChunkerConfig] = None
) -> list[str]:
    """Split text into Discord-safe chunks.

    Args:
        text: Formatted text to chunk
        config: Optional chunker configuration

    Returns:
        List of text chunks, each under Discord's limit
    """
    if not text:
        return []

    config = config or ChunkerConfig()

    # If text fits in one message, return as-is
    if len(text) <= config.max_chars:
        return [text]

    # Split preserving code fences
    chunks = split_preserving_code_fences(text, config.max_chars)

    # Merge tiny chunks if possible
    chunks = merge_small_chunks(chunks, config.min_chars, config.max_chars)

    # Add chunk numbers if 3+ chunks
    if config.add_chunk_numbers and len(chunks) >= 3:
        chunks = add_chunk_numbers(chunks)

    return chunks


def split_preserving_code_fences(text: str, max_chars: int) -> list[str]:
    """Split text while preserving code block integrity.

    Critical rule: Never split inside a code block.
    If split needed inside code block, close it and re-open in next chunk.

    Based on Section 6.3.
    """
    # Handle edge case: very long single line or no natural breaks
    if '\n' not in text and len(text) > max_chars:
        return split_at_boundaries(text, max_chars)

    chunks = []
    current = ''
    in_code_block = False
    code_lang = ''

    lines = text.split('\n')

    # If only one very long line, use boundary-based splitting
    if len(lines) == 1 and len(text) > max_chars:
        return split_at_boundaries(text, max_chars)

    for line in lines:
        # Track code block state
        if line.strip().startswith('```'):
            if in_code_block:
                # Closing fence
                in_code_block = False
                code_lang = ''
            else:
                # Opening fence - extract language
                in_code_block = True
                code_lang = line.strip()[3:].strip()

        # Check if adding this line would exceed limit
        potential = current + ('\n' if current else '') + line
        if len(potential) > max_chars and current:
            # Need to split
            if in_code_block and not line.strip().startswith('```'):
                # We're inside a code block - close it properly
                current += '\n```'
                chunks.append(current.strip())
                # Re-open code block in new chunk
                current = f'```{code_lang}\n{line}'
            else:
                # Normal split at line boundary
                chunks.append(current.strip())
                current = line
        else:
            current = potential

    # Don't forget the last chunk
    if current.strip():
        chunks.append(current.strip())

    # Final check: ensure all chunks are under limit
    final_chunks = []
    for c in chunks:
        if len(c) > max_chars:
            final_chunks.extend(split_at_boundaries(c, max_chars))
        else:
            final_chunks.append(c)

    return final_chunks


def split_at_boundaries(text: str, max_chars: int) -> list[str]:
    """Split text at word/sentence boundaries when no natural line breaks."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        # Find best split point
        split_point = find_best_split_point(remaining, max_chars)
        chunks.append(remaining[:split_point].strip())
        remaining = remaining[split_point:].strip()

    return chunks


def merge_small_chunks(chunks: list[str], min_chars: int, max_chars: int) -> list[str]:
    """Merge chunks that are too small.

    Prevents sending tiny fragments like "(continued)" alone.
    """
    if len(chunks) <= 1:
        return chunks

    merged = []
    current = chunks[0]

    for i in range(1, len(chunks)):
        next_chunk = chunks[i]

        # If current is small and can be merged, do it
        if len(current) < min_chars:
            combined = current + '\n\n' + next_chunk
            if len(combined) <= max_chars:
                current = combined
                continue

        merged.append(current)
        current = next_chunk

    merged.append(current)
    return merged


def add_chunk_numbers(chunks: list[str]) -> list[str]:
    """Add chunk indicators for multi-part responses.

    Uses Discord subtext format: -# (1/3)
    Only added for 3+ chunks per Section 6.2.
    """
    total = len(chunks)
    return [
        f"{chunk}\n\n-# ({i + 1}/{total})"
        for i, chunk in enumerate(chunks)
    ]


def find_best_split_point(text: str, max_chars: int) -> int:
    """Find the best place to split text under max_chars.

    Tries split points in priority order:
    1. Paragraph boundary (\\n\\n)
    2. Newline (\\n)
    3. Sentence end (. )
    4. Whitespace
    5. Hard break at max_chars
    """
    if len(text) <= max_chars:
        return len(text)

    # Search area: last 200 chars before max_chars
    search_start = max(0, max_chars - 200)
    search_area = text[search_start:max_chars]

    # Priority 1: Paragraph boundary
    para_match = search_area.rfind('\n\n')
    if para_match != -1:
        return search_start + para_match + 2

    # Priority 2: Newline
    newline_match = search_area.rfind('\n')
    if newline_match != -1:
        return search_start + newline_match + 1

    # Priority 3: Sentence end
    sentence_patterns = ['. ', '.\n', '! ', '!\n', '? ', '?\n']
    best_sentence = -1
    for pattern in sentence_patterns:
        pos = search_area.rfind(pattern)
        if pos > best_sentence:
            best_sentence = pos
    if best_sentence != -1:
        return search_start + best_sentence + 2

    # Priority 4: Whitespace
    space_match = search_area.rfind(' ')
    if space_match != -1:
        return search_start + space_match + 1

    # Priority 5: Hard break (last resort)
    return max_chars


def chunk_smart(text: str, max_chars: int = 1900) -> list[str]:
    """Alternative chunking using smart split points.

    Uses find_best_split_point for optimal breaks.
    """
    if not text or len(text) <= max_chars:
        return [text] if text else []

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        split_point = find_best_split_point(remaining, max_chars)
        chunks.append(remaining[:split_point].strip())
        remaining = remaining[split_point:].strip()

    return chunks


def estimate_chunk_count(text: str, max_chars: int = 1900) -> int:
    """Estimate how many chunks text will produce."""
    if not text:
        return 0
    return max(1, (len(text) + max_chars - 1) // max_chars)


# =============================================================================
# EMBED-SPECIFIC CHUNKING
# =============================================================================

def chunk_for_embed_description(text: str) -> list[str]:
    """Chunk text for embed descriptions (4096 char limit)."""
    return chunk(text, ChunkerConfig(max_chars=4000, min_chars=500))


def chunk_for_embed_field(text: str) -> list[str]:
    """Chunk text for embed field values (1024 char limit)."""
    return chunk(text, ChunkerConfig(max_chars=1000, min_chars=100, add_chunk_numbers=False))


# =============================================================================
# TESTING
# =============================================================================

def test_chunker():
    """Run basic chunker tests."""
    test_cases = [
        # Short text - no chunking
        ('Short message', 1),

        # Long text - should chunk
        ('A' * 2500, 2),

        # Text with code block
        ('Before\n```python\n' + 'x = 1\n' * 100 + '```\nAfter', None),  # Variable

        # Paragraph boundaries preferred
        ('Para 1.\n\n' + 'A' * 1800 + '\n\nPara 3.', 2),
    ]

    passed = 0
    failed = 0

    for text, expected_chunks in test_cases:
        chunks = chunk(text)

        # Verify all chunks are under limit
        all_under_limit = all(len(c) <= 2000 for c in chunks)

        if expected_chunks is not None:
            correct_count = len(chunks) == expected_chunks
        else:
            correct_count = True  # Variable expected

        if all_under_limit and correct_count:
            passed += 1
            print(f"✓ PASS - {len(chunks)} chunks, all under limit")
        else:
            failed += 1
            print(f"✗ FAIL - {len(chunks)} chunks (expected {expected_chunks})")
            for i, c in enumerate(chunks):
                print(f"  Chunk {i + 1}: {len(c)} chars")

    # Test code fence preservation
    code_text = '```python\n' + 'x = 1\n' * 200 + '```'
    code_chunks = chunk(code_text)

    # Each chunk should have balanced fences
    fences_balanced = True
    for c in code_chunks:
        opens = c.count('```python') + c.count('```\n')
        closes = c.count('\n```') + c.endswith('```')
        # Simplified check - should have opening if has code
        if '```' in c:
            if c.count('```') % 2 != 0 and not (c.startswith('```') or c.endswith('```')):
                fences_balanced = False

    if fences_balanced:
        passed += 1
        print("✓ PASS - Code fence preservation")
    else:
        failed += 1
        print("✗ FAIL - Code fence preservation")

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == '__main__':
    test_chunker()

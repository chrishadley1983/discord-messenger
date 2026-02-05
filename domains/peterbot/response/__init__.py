"""Response Processing Pipeline for PeterBot.

Transforms raw Claude Code output into clean Discord messages through 5 stages:
1. Sanitiser - Strip CC artifacts
2. Classifier - Detect response type
3. Formatter - Apply Discord-native formatting
4. Chunker - Split into Discord-safe segments
5. Renderer - Produce final Discord message objects
"""

from .pipeline import process, ProcessedResponse
from .sanitiser import sanitise
from .chunker import chunk
from .classifier import classify, ResponseType

__all__ = [
    'process',
    'ProcessedResponse',
    'sanitise',
    'chunk',
    'classify',
    'ResponseType',
]

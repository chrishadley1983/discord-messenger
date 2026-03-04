"""Split conversations into topic-coherent chunks.

Each chunk represents a self-contained topic segment from a conversation,
suitable for classification and import into memory systems.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .parser import Conversation, ChatMessage


@dataclass
class ConversationChunk:
    """A topic-coherent segment of a conversation."""
    conversation_id: str
    conversation_name: str
    chunk_index: int
    messages: list[ChatMessage]
    created_at: Optional[datetime] = None

    @property
    def text(self) -> str:
        """Combine all messages into a single text block."""
        parts = []
        for msg in self.messages:
            role = "Chris" if msg.sender == "human" else "Claude"
            parts.append(f"**{role}**: {msg.text}")
        return "\n\n".join(parts)

    @property
    def human_text(self) -> str:
        """Just the human messages."""
        return "\n\n".join(m.text for m in self.messages if m.sender == "human")

    @property
    def assistant_text(self) -> str:
        """Just the assistant messages."""
        return "\n\n".join(m.text for m in self.messages if m.sender == "assistant")

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def code_block_ratio(self) -> float:
        """Ratio of text inside code blocks vs total text."""
        text = self.assistant_text
        if not text:
            return 0.0
        import re
        code_blocks = re.findall(r"```[\s\S]*?```", text)
        code_len = sum(len(b) for b in code_blocks)
        return code_len / len(text) if text else 0.0


# Topic shift detection signals
TOPIC_SHIFT_PHRASES = [
    "new topic", "different question", "something else",
    "by the way", "unrelated", "changing subject",
    "can you help me with", "i need help with",
    "let's talk about", "moving on",
]


def _is_topic_shift(message: ChatMessage) -> bool:
    """Detect if a human message signals a topic shift."""
    if message.sender != "human":
        return False
    text_lower = message.text.lower()
    return any(phrase in text_lower for phrase in TOPIC_SHIFT_PHRASES)


def _messages_are_related(prev_msgs: list[ChatMessage], next_msg: ChatMessage) -> bool:
    """Heuristic: are these messages about the same topic?

    Uses simple overlap of significant words between the recent context
    and the new message.
    """
    if not prev_msgs:
        return True

    # Get words from last 2 messages of context
    context_text = " ".join(m.text.lower() for m in prev_msgs[-2:])
    next_text = next_msg.text.lower()

    # Simple word overlap (ignore common words)
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                 "have", "has", "had", "do", "does", "did", "will", "would",
                 "can", "could", "should", "may", "might", "i", "you", "we",
                 "they", "it", "this", "that", "my", "your", "to", "of", "in",
                 "for", "on", "with", "at", "by", "from", "and", "or", "not",
                 "but", "so", "if", "as", "just", "about", "like", "what",
                 "how", "when", "where", "why", "which", "who", "some", "any",
                 "all", "each", "every", "no", "yes", "ok", "okay", "thanks",
                 "thank", "please", "sure", "right", "well", "also", "too"}

    context_words = set(context_text.split()) - stopwords
    next_words = set(next_text.split()) - stopwords

    if not context_words or not next_words:
        return True

    overlap = len(context_words & next_words) / min(len(context_words), len(next_words))
    return overlap > 0.1  # 10% word overlap threshold


def chunk_conversation(
    conversation: Conversation,
    min_chunk_messages: int = 2,
    max_chunk_messages: int = 20,
) -> list[ConversationChunk]:
    """Split a conversation into topic-coherent chunks.

    Splits on:
    1. Explicit topic shift phrases from the human
    2. Low word overlap between consecutive exchanges
    3. Max chunk size

    Args:
        conversation: Parsed conversation
        min_chunk_messages: Minimum messages per chunk (default 2)
        max_chunk_messages: Maximum messages per chunk (default 20)

    Returns:
        List of ConversationChunks
    """
    if not conversation.messages:
        return []

    chunks = []
    current_messages: list[ChatMessage] = []
    chunk_index = 0

    for msg in conversation.messages:
        # Check for topic shift
        should_split = False
        if len(current_messages) >= min_chunk_messages:
            if _is_topic_shift(msg):
                should_split = True
            elif msg.sender == "human" and not _messages_are_related(current_messages, msg):
                should_split = True
            elif len(current_messages) >= max_chunk_messages:
                should_split = True

        if should_split and current_messages:
            chunks.append(ConversationChunk(
                conversation_id=conversation.uuid,
                conversation_name=conversation.name,
                chunk_index=chunk_index,
                messages=current_messages,
                created_at=current_messages[0].created_at,
            ))
            chunk_index += 1
            current_messages = []

        current_messages.append(msg)

    # Final chunk
    if current_messages:
        chunks.append(ConversationChunk(
            conversation_id=conversation.uuid,
            conversation_name=conversation.name,
            chunk_index=chunk_index,
            messages=current_messages,
            created_at=current_messages[0].created_at,
        ))

    return chunks

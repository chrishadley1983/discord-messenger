"""Parse Anthropic Claude chat history JSON export.

Anthropic exports conversations as JSON with this structure:
[
  {
    "uuid": "...",
    "name": "conversation title",
    "created_at": "2024-...",
    "updated_at": "2024-...",
    "chat_messages": [
      {
        "uuid": "...",
        "text": "message content",
        "sender": "human" | "assistant",
        "created_at": "...",
        "attachments": [...],
        "files": [...]
      }
    ]
  }
]
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class ChatMessage:
    """A single message in a conversation."""
    uuid: str
    text: str
    sender: str  # "human" or "assistant"
    created_at: Optional[datetime] = None
    attachments: list[dict] = field(default_factory=list)


@dataclass
class Conversation:
    """A parsed conversation."""
    uuid: str
    name: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    messages: list[ChatMessage] = field(default_factory=list)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def human_messages(self) -> list[ChatMessage]:
        return [m for m in self.messages if m.sender == "human"]

    @property
    def assistant_messages(self) -> list[ChatMessage]:
        return [m for m in self.messages if m.sender == "assistant"]


def _parse_datetime(s: str) -> Optional[datetime]:
    """Parse ISO datetime string, handling various formats."""
    if not s:
        return None
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
    ]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_export_file(path: Path) -> list[Conversation]:
    """Parse a Claude chat history export JSON file.

    Args:
        path: Path to the JSON export file

    Returns:
        List of parsed Conversation objects
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both array-of-conversations and single-conversation format
    if isinstance(data, dict):
        data = [data]

    conversations = []
    for conv_data in data:
        messages = []
        for msg_data in conv_data.get("chat_messages", []):
            text = msg_data.get("text", "")
            # Some exports nest content in a "content" field
            if not text and "content" in msg_data:
                content = msg_data["content"]
                if isinstance(content, list):
                    text = " ".join(
                        block.get("text", "")
                        for block in content
                        if isinstance(block, dict) and block.get("type") == "text"
                    )
                elif isinstance(content, str):
                    text = content

            if not text:
                continue

            messages.append(ChatMessage(
                uuid=msg_data.get("uuid", ""),
                text=text,
                sender=msg_data.get("sender", msg_data.get("role", "unknown")),
                created_at=_parse_datetime(msg_data.get("created_at", "")),
                attachments=msg_data.get("attachments", []) + msg_data.get("files", []),
            ))

        if messages:
            conversations.append(Conversation(
                uuid=conv_data.get("uuid", ""),
                name=conv_data.get("name", "Untitled"),
                created_at=_parse_datetime(conv_data.get("created_at", "")),
                updated_at=_parse_datetime(conv_data.get("updated_at", "")),
                messages=messages,
            ))

    return conversations

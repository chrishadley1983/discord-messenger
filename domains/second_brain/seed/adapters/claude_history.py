"""Claude chat history seed adapter.

Imports knowledge-classified chunks from Anthropic JSON exports
into the Second Brain. Works alongside the main ingest script
which handles peterbot-mem routing separately.

Usage:
    adapter = ClaudeHistoryAdapter({"export_file": "/path/to/export.json"})
    result = await run_seed_import(adapter, limit=100)
"""

from pathlib import Path
from typing import Any

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


@register_adapter
class ClaudeHistoryAdapter(SeedAdapter):
    """Import knowledge content from Claude chat history exports."""

    name = "claude-history"
    description = "Import knowledge from Anthropic Claude chat history JSON exports"
    source_system = "seed:claude-chat"

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config)
        self.export_file = Path(config.get("export_file", "")) if config else None
        self.min_confidence = config.get("min_confidence", 0.5) if config else 0.5

    async def validate(self) -> tuple[bool, str]:
        if not self.export_file or not self.export_file.exists():
            return False, f"Export file not found: {self.export_file}"
        return True, ""

    async def fetch(self, limit: int = 100) -> list[SeedItem]:
        """Parse, chunk, classify, and return knowledge-routed items."""
        from scripts.chat_history.parser import parse_export_file
        from scripts.chat_history.chunker import chunk_conversation
        from scripts.chat_history.classifier import classify_chunk, Route

        conversations = parse_export_file(self.export_file)
        logger.info(f"Parsed {len(conversations)} conversations from {self.export_file.name}")

        items = []
        for conv in conversations:
            chunks = chunk_conversation(conv)
            for chunk in chunks:
                result = classify_chunk(chunk)

                # Only take knowledge-routed chunks with sufficient confidence
                if result.route != Route.SECOND_BRAIN:
                    continue
                if result.confidence < self.min_confidence:
                    continue

                # Build a title from the conversation name + chunk index
                title = f"Chat: {conv.name}"
                if chunk.chunk_index > 0:
                    title += f" (part {chunk.chunk_index + 1})"

                items.append(SeedItem(
                    title=title,
                    content=chunk.text,
                    source_url=f"claude-chat://{conv.uuid}/{chunk.chunk_index}",
                    source_id=f"claude-chat:{conv.uuid}:{chunk.chunk_index}",
                    topics=["claude-history"],
                    created_at=chunk.created_at or conv.created_at,
                    metadata={
                        "conversation_id": conv.uuid,
                        "chunk_index": chunk.chunk_index,
                        "confidence": result.confidence,
                        "reason": result.reason,
                    },
                ))

                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break

        logger.info(f"Found {len(items)} knowledge chunks for Second Brain import")
        return items[:limit]

    def get_default_topics(self) -> list[str]:
        return ["claude-history"]

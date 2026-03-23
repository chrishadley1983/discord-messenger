"""Claude Code local history adapter.

Reads Claude Code CLI conversation history from ~/.claude/projects/
and extracts knowledge-bearing exchanges.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


# Claude Code stores conversations in ~/.claude/projects/
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


@register_adapter
class ClaudeCodeHistoryAdapter(SeedAdapter):
    """Import knowledge from Claude Code local conversation history."""

    name = "claude-code-history"
    description = "Claude Code CLI conversation history from local files"
    source_system = "seed:claude-code"

    def get_default_topics(self) -> list[str]:
        return ["claude-code", "development"]

    async def validate(self) -> tuple[bool, str]:
        if not CLAUDE_PROJECTS_DIR.exists():
            return False, f"Claude Code projects directory not found: {CLAUDE_PROJECTS_DIR}"
        return True, ""

    async def fetch(self, limit: int = 50) -> list[SeedItem]:
        items = []
        days_back = self.config.get("days_back", 7)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        if not CLAUDE_PROJECTS_DIR.exists():
            return items

        # Scan all project directories for conversation files
        for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
            if not project_dir.is_dir():
                continue

            # Look for conversation JSONL files
            for conv_file in project_dir.glob("*.jsonl"):
                try:
                    # Skip old files
                    mtime = datetime.fromtimestamp(
                        conv_file.stat().st_mtime, tz=timezone.utc
                    )
                    if mtime < cutoff:
                        continue

                    conv_items = self._parse_conversation(
                        conv_file, project_dir.name
                    )
                    items.extend(conv_items)

                    if len(items) >= limit:
                        break

                except Exception as e:
                    logger.warning(f"Failed to parse {conv_file.name}: {e}")

            if len(items) >= limit:
                break

        logger.info(f"Fetched {len(items)} Claude Code history items")
        return items[:limit]

    def _parse_conversation(
        self,
        conv_file: Path,
        project_name: str,
    ) -> list[SeedItem]:
        """Parse a Claude Code conversation JSONL file."""
        items = []
        conversation_id = conv_file.stem

        # Read JSONL lines
        messages = []
        try:
            with open(conv_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        messages.append(msg)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Failed to read {conv_file}: {e}")
            return items

        if not messages:
            return items

        # Extract knowledge-bearing exchanges
        # Skip pure tool calls, file reads, and short exchanges
        knowledge_chunks = self._extract_knowledge_chunks(messages)

        for i, chunk in enumerate(knowledge_chunks):
            content = chunk["content"]
            if len(content) < 100:
                continue

            # Derive project-specific topics
            topics = ["claude-code", "development"]
            clean_project = self._clean_project_name(project_name)
            if clean_project:
                topics.append(clean_project)

            items.append(SeedItem(
                title=f"Claude Code: {chunk['title'][:60]}",
                content=content,
                source_url=f"claude-code://{project_name}/{conversation_id}/{i}",
                source_id=f"cc-{conversation_id}-{i}",
                topics=topics,
                created_at=chunk.get("timestamp"),
                content_type="conversation_extract",
            ))

        return items

    def _extract_knowledge_chunks(self, messages: list[dict]) -> list[dict]:
        """Extract knowledge-bearing content from conversation messages."""
        chunks = []
        current_exchange = []
        current_title = ""

        current_timestamp = None

        for msg in messages:
            role = msg.get("role", "")
            content = self._extract_text_content(msg)

            if not content or len(content) < 20:
                continue

            # Skip tool-only messages
            if role == "assistant" and self._is_tool_only(msg):
                continue

            if role == "human" or role == "user":
                # If we have a previous exchange, save it
                if current_exchange and len("\n\n".join(current_exchange)) > 100:
                    chunks.append({
                        "title": current_title,
                        "content": "\n\n".join(current_exchange),
                        "timestamp": current_timestamp,
                    })

                current_exchange = [f"**User:** {content}"]
                current_title = content[:80]
                current_timestamp = self._get_timestamp(msg)

            elif role == "assistant":
                if current_exchange:
                    current_exchange.append(f"**Claude:** {content}")

        # Save final exchange
        if current_exchange and len("\n\n".join(current_exchange)) > 100:
            chunks.append({
                "title": current_title,
                "content": "\n\n".join(current_exchange),
                "timestamp": None,
            })

        return chunks

    def _extract_text_content(self, msg: dict) -> str:
        """Extract text content from a message, ignoring tool calls."""
        content = msg.get("content", "")

        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            return "\n".join(text_parts).strip()

        return ""

    def _is_tool_only(self, msg: dict) -> bool:
        """Check if a message contains only tool calls/results."""
        content = msg.get("content", "")
        if isinstance(content, list):
            has_text = any(
                isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip()
                for b in content
            )
            return not has_text
        return False

    def _get_timestamp(self, msg: dict) -> datetime | None:
        """Extract timestamp from a message."""
        ts = msg.get("timestamp") or msg.get("created_at")
        if ts:
            try:
                if isinstance(ts, (int, float)):
                    return datetime.fromtimestamp(ts, tz=timezone.utc)
                return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
        return None

    def _clean_project_name(self, project_name: str) -> str:
        """Extract a clean topic from the project directory name."""
        # Project dirs are like "C--Users-Chris-Hadley-claude-projects-discord-messenger"
        parts = project_name.lower().split("-")
        # Find meaningful parts (skip path components)
        meaningful = []
        skip_words = {"c", "users", "chris", "hadley", "claude", "projects"}
        for part in parts:
            if part and part not in skip_words and len(part) > 1:
                meaningful.append(part)

        if meaningful:
            return "-".join(meaningful[-3:])  # Last 3 meaningful parts
        return ""

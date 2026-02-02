"""Browser bookmarks adapter.

Imports bookmarks from exported bookmark files (HTML or JSON).
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


@register_adapter
class BookmarksAdapter(SeedAdapter):
    """Import browser bookmarks from exported file."""

    name = "bookmarks"
    description = "Import browser bookmarks from HTML/JSON export"
    source_system = "seed:bookmarks"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.file_path = config.get("file_path") if config else None

    async def validate(self) -> tuple[bool, str]:
        if not self.file_path:
            return False, "Bookmark file path not configured"
        if not Path(self.file_path).exists():
            return False, f"File not found: {self.file_path}"
        return True, ""

    async def fetch(self, limit: int = 100) -> list[SeedItem]:
        file_path = Path(self.file_path)

        # Check if JSON by extension or by content (Chrome's Bookmarks has no extension)
        if file_path.suffix.lower() == ".json":
            return await self._parse_json(file_path, limit)

        # Try to detect JSON by reading first char
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                first_char = f.read(1)
            if first_char == "{":
                return await self._parse_json(file_path, limit)
        except Exception:
            pass

        return await self._parse_html(file_path, limit)

    async def _parse_json(self, path: Path, limit: int) -> list[SeedItem]:
        """Parse Chrome/Edge bookmark JSON export."""
        items = []

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Chrome format has 'roots' with 'bookmark_bar', 'other', etc.
            roots = data.get("roots", {})

            for root_name, root in roots.items():
                if isinstance(root, dict):
                    self._extract_from_node(root, items, limit)
                    if len(items) >= limit:
                        break

        except Exception as e:
            logger.error(f"Failed to parse bookmark JSON: {e}")

        return items[:limit]

    def _extract_from_node(
        self,
        node: dict,
        items: list[SeedItem],
        limit: int,
        folder_path: str = "",
    ) -> None:
        """Recursively extract bookmarks from JSON node."""
        if len(items) >= limit:
            return

        node_type = node.get("type")
        name = node.get("name", "")

        if node_type == "url":
            url = node.get("url", "")
            if url and url.startswith("http"):
                items.append(SeedItem(
                    title=name,
                    content=f"Bookmark: {name}\nFolder: {folder_path}\nURL: {url}",
                    source_url=url,
                    source_id=node.get("id"),
                    topics=self._topics_from_folder(folder_path),
                    created_at=self._parse_chrome_timestamp(node.get("date_added")),
                ))

        # Handle folders (explicit type or root nodes with children)
        if node_type == "folder" or (node_type is None and "children" in node):
            current_path = f"{folder_path}/{name}" if folder_path and name else (name or folder_path)
            for child in node.get("children", []):
                self._extract_from_node(child, items, limit, current_path)

    async def _parse_html(self, path: Path, limit: int) -> list[SeedItem]:
        """Parse Netscape bookmark HTML export."""
        items = []

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            # Extract links with regex
            pattern = r'<A[^>]*HREF="([^"]+)"[^>]*>([^<]+)</A>'
            matches = re.findall(pattern, content, re.IGNORECASE)

            for url, title in matches[:limit]:
                if url.startswith("http"):
                    items.append(SeedItem(
                        title=title.strip(),
                        content=f"Bookmark: {title}\nURL: {url}",
                        source_url=url,
                        topics=["bookmark"],
                    ))

        except Exception as e:
            logger.error(f"Failed to parse bookmark HTML: {e}")

        return items

    def _parse_chrome_timestamp(self, timestamp: Optional[str]) -> Optional[datetime]:
        """Parse Chrome's WebKit timestamp (microseconds since 1601)."""
        if not timestamp:
            return None
        try:
            # Chrome uses microseconds since Jan 1, 1601
            webkit_epoch = 11644473600000000  # Difference between 1601 and 1970
            ts = int(timestamp)
            unix_ts = (ts - webkit_epoch) / 1000000
            return datetime.fromtimestamp(unix_ts)
        except (ValueError, OSError):
            return None

    def _topics_from_folder(self, folder_path: str) -> list[str]:
        """Extract topics from folder path."""
        topics = ["bookmark"]

        if not folder_path:
            return topics

        # Common folder name mappings
        folder_lower = folder_path.lower()
        if "lego" in folder_lower or "brick" in folder_lower:
            topics.append("lego")
        if "running" in folder_lower or "fitness" in folder_lower:
            topics.append("fitness")
        if "tech" in folder_lower or "dev" in folder_lower or "code" in folder_lower:
            topics.append("tech")
        if "business" in folder_lower or "work" in folder_lower:
            topics.append("business")
        if "recipe" in folder_lower or "cooking" in folder_lower:
            topics.append("recipe")

        return topics

    def get_default_topics(self) -> list[str]:
        return ["bookmark"]

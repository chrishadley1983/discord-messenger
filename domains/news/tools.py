"""News domain tools for Claude API."""

from domains.base import ToolDefinition
from .services import fetch_feed, fetch_article

TOOLS = [
    ToolDefinition(
        name="get_headlines",
        description="Get latest headlines from a category (tech, uk, f1, or all)",
        input_schema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["tech", "uk", "f1", "all"],
                    "description": "News category"
                },
                "limit": {
                    "type": "number",
                    "description": "Max headlines to return (default 10)"
                }
            },
            "required": ["category"]
        },
        handler=fetch_feed
    ),

    ToolDefinition(
        name="read_article",
        description="Fetch and summarise a specific article by URL",
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Article URL"}
            },
            "required": ["url"]
        },
        handler=fetch_article
    ),
]

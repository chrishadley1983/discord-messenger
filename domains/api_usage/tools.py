"""API Usage domain tools for Claude API."""

from domains.base import ToolDefinition
from .services import get_anthropic_usage, get_openai_usage

TOOLS = [
    ToolDefinition(
        name="get_anthropic_usage",
        description="Get Claude API usage for a period",
        input_schema={
            "type": "object",
            "properties": {
                "days": {"type": "number", "description": "Number of days to look back (default 7)"}
            }
        },
        handler=get_anthropic_usage
    ),

    ToolDefinition(
        name="get_openai_usage",
        description="Get OpenAI API usage for a period",
        input_schema={
            "type": "object",
            "properties": {
                "days": {"type": "number", "description": "Number of days to look back (default 7)"}
            }
        },
        handler=get_openai_usage
    ),
]

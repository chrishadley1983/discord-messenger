"""API Usage domain tools for Claude API."""

from domains.base import ToolDefinition
from .services import get_anthropic_usage, get_openai_usage, get_google_usage, get_google_daily_breakdown, get_vision_effectiveness

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

    ToolDefinition(
        name="get_google_usage",
        description="Get Google AI (Gemini) API usage and estimated cost for a period",
        input_schema={
            "type": "object",
            "properties": {
                "days": {"type": "number", "description": "Number of days to look back (default 7)"}
            }
        },
        handler=get_google_usage
    ),

    ToolDefinition(
        name="get_google_daily_breakdown",
        description="Get day-by-day Google AI (Gemini) spend breakdown — shows requests and estimated cost per model per day",
        input_schema={
            "type": "object",
            "properties": {
                "days": {"type": "number", "description": "Number of days to look back (default 7)"}
            }
        },
        handler=get_google_daily_breakdown
    ),

    ToolDefinition(
        name="get_vision_effectiveness",
        description="Get Vinted Sniper Gemini Vision effectiveness — hit rate, miss rate, sets identified, response times",
        input_schema={
            "type": "object",
            "properties": {
                "days": {"type": "number", "description": "Number of days to look back (default 1)"}
            }
        },
        handler=get_vision_effectiveness
    ),
]

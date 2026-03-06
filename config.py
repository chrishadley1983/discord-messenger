"""Global configuration for Discord Assistant."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Claude API - using renamed var to prevent Claude Code from picking it up
ANTHROPIC_API_KEY = os.getenv("DISCORD_BOT_CLAUDE_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Garmin
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")

# Withings
WITHINGS_CLIENT_ID = os.getenv("WITHINGS_CLIENT_ID")
WITHINGS_CLIENT_SECRET = os.getenv("WITHINGS_CLIENT_SECRET")
WITHINGS_ACCESS_TOKEN = os.getenv("WITHINGS_ACCESS_TOKEN")
WITHINGS_REFRESH_TOKEN = os.getenv("WITHINGS_REFRESH_TOKEN")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# xAI Grok
GROK_API_KEY = os.getenv("GROK_API_KEY")
GROK_MANAGEMENT_KEY = os.getenv("GROK_MANAGEMENT_KEY")
GROK_TEAM_ID = os.getenv("GROK_TEAM_ID")

# Moonshot Kimi
MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY")

# Google Maps
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# Evolution API (WhatsApp via self-hosted instance)
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8085")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "peter-whatsapp-2026-hadley")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "peter-whatsapp")

# Sport APIs
FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
CRICKET_API_KEY = os.getenv("CRICKET_API_KEY")

# Hadley API (local FastAPI for Claude CLI, Gmail, Calendar, etc.)
HADLEY_API_BASE = os.getenv("HADLEY_API_BASE", "http://172.19.64.1:8100")


async def call_claude_via_cli(
    prompt: str, max_tokens: int = 1500, timeout: int = 60, model: str = ""
) -> str | None:
    """Call Claude via the local Hadley API /claude/extract endpoint.

    Uses claude -p CLI under the hood (OAuth credentials, no API key needed).
    Replaces all direct Anthropic API calls that used the dead DISCORD_BOT_CLAUDE_KEY.
    """
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{HADLEY_API_BASE}/claude/extract",
                json={"prompt": prompt, "max_tokens": max_tokens, "model": model},
                timeout=timeout + 30,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("error"):
                return None
            return data.get("result")
    except Exception:
        return None


# Logging
LOG_DIR = Path(os.getenv("LOCALAPPDATA", ".")) / "discord-assistant" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Balance log directories
CLAUDE_BALANCE_LOG = Path(os.getenv("LOCALAPPDATA", ".")) / "discord-assistant" / "claude-balance.log"
MOONSHOT_BALANCE_LOG = Path(os.getenv("LOCALAPPDATA", ".")) / "discord-assistant" / "moonshot-balance.log"

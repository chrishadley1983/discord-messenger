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

# Twilio WhatsApp
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")

# Logging
LOG_DIR = Path(os.getenv("LOCALAPPDATA", ".")) / "discord-assistant" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Balance log directories
CLAUDE_BALANCE_LOG = Path(os.getenv("LOCALAPPDATA", ".")) / "discord-assistant" / "claude-balance.log"
MOONSHOT_BALANCE_LOG = Path(os.getenv("LOCALAPPDATA", ".")) / "discord-assistant" / "moonshot-balance.log"

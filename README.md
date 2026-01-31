# Discord Personal Assistant

A modular Discord bot with AI coaching/assistance via Claude API.

## Features

### Domains (Channel-Based)

- **Nutrition** (`#food-log`) - Meal/water logging, Garmin steps, Withings weight, PT-style coaching
- **News** (`#news`) - Morning briefings, topic deep-dives, source summaries
- **API Usage** (`#api-usage`) - Track Claude/OpenAI spend, usage patterns, budget alerts

### Scheduled Jobs

- **AI Morning Briefing** (6:30 AM UTC) - Daily AI news digest to `#ai-briefings`
- **API Balance Monitor** (Hourly) - Claude + Moonshot Kimi balance checks to `#peter-chat`
- **School Run Report** (8:15 AM UK, Weekdays) - Traffic, weather, uniform via WhatsApp

## Setup

### 1. Clone and Install

```powershell
cd C:\Users\Chris Hadley\Discord-Messenger
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```powershell
copy .env.example .env
notepad .env
```

Required credentials:
- `DISCORD_TOKEN` - Discord bot token
- `ANTHROPIC_API_KEY` - Claude API key
- `SUPABASE_URL` / `SUPABASE_KEY` - For nutrition data
- `GARMIN_EMAIL` / `GARMIN_PASSWORD` - For steps
- `WITHINGS_*` - For weight tracking
- `GROK_API_KEY` - For morning briefing community buzz
- `MOONSHOT_API_KEY` - For balance monitoring
- `GOOGLE_MAPS_API_KEY` - For school run traffic
- `TWILIO_*` - For WhatsApp messages

### 3. Run

```powershell
# Development (with console output)
python bot.py

# Background (no console)
pythonw bot.py
```

### 4. Install as Startup Task (Optional)

```powershell
# Run as Administrator
.\scripts\install_startup.ps1
```

## Architecture

```
Discord
  │
  ├── #food-log ─────┐
  ├── #news ─────────┼──▶ bot.py (router)
  └── #api-usage ────┘         │
                               ▼
                    ┌─────────────────────┐
                    │  Domain Registry    │
                    └─────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ Nutrition│    │   News   │    │ API Usage│
        │  Domain  │    │  Domain  │    │  Domain  │
        └──────────┘    └──────────┘    └──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  claude_client.py   │
                    │  (tool-use loop)    │
                    └─────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Claude API       │
                    │    (Haiku 4.5)      │
                    └─────────────────────┘
```

## Testing

```powershell
# Run all tests
pytest

# Run specific test file
pytest tests/integration/test_message_flow.py

# Run with coverage
pytest --cov=. --cov-report=html
```

## Logs

Logs are written to:
- `%LOCALAPPDATA%\discord-assistant\logs\YYYY-MM-DD.log`

Balance logs:
- `%LOCALAPPDATA%\discord-assistant\claude-balance.log`
- `%LOCALAPPDATA%\discord-assistant\moonshot-balance.log`

## Adding a New Domain

1. Create folder: `domains/your_domain/`
2. Create files:
   - `__init__.py` - Export your domain class
   - `config.py` - Channel ID, system prompt, constants
   - `tools.py` - Tool definitions list
   - `schedules.py` - Scheduled tasks (optional)
   - `domain.py` - Domain class inheriting from `Domain`
   - `services/` - External API integrations

3. Register in `bot.py`:
   ```python
   from domains.your_domain import YourDomain
   registry.register(YourDomain())
   ```

## Cost Estimate

~$0.50-2/month depending on usage (Claude Haiku 4.5)

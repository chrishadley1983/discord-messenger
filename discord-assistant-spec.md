# Discord Personal Assistant - Technical Spec

**Project:** discord-assistant  
**Purpose:** Multi-domain Discord bot with AI coaching/assistance via Claude API  
**Target:** Windows desktop, personal use  
**AI Backend:** Claude API (Haiku 4.5, upgradeable to Sonnet)  
**Estimated cost:** ~$0.50-2/month depending on usage

---

## Overview

A modular Discord bot that:
1. Routes messages to domain handlers based on channel
2. Each domain has its own system prompt, tools, and scheduled tasks
3. Shares a common Claude API client with tool-use support
4. Easily extensible - add a domain folder, register it, done

**Initial domains:**
- **Nutrition** - Meal/water logging, Garmin steps, Withings weight, PT-style coaching
- **News** - Morning briefings, topic deep-dives, source summaries
- **API Usage** - Track Claude/OpenAI spend, usage patterns, budget alerts

---

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
                    │  channel → domain   │
                    └─────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ Nutrition│    │   News   │    │ API Usage│
        │  Domain  │    │  Domain  │    │  Domain  │
        └──────────┘    └──────────┘    └──────────┘
              │                │                │
              └────────────────┼────────────────┘
                               ▼
                    ┌─────────────────────┐
                    │  claude_client.py   │
                    │  (generic, receives │
                    │  tools per call)    │
                    └─────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Claude API       │
                    │    (Haiku 4.5)      │
                    └─────────────────────┘
```

---

## File Structure

```
discord-assistant/
├── bot.py                      # Main bot, router, scheduler loader
├── claude_client.py            # Generic Claude API wrapper
├── registry.py                 # Domain registration + lookup
├── domains/
│   ├── __init__.py
│   ├── base.py                 # Abstract Domain class
│   │
│   ├── nutrition/
│   │   ├── __init__.py         # Exports NutritionDomain
│   │   ├── domain.py           # Domain class implementation
│   │   ├── config.py           # Targets, channel ID, system prompt
│   │   ├── tools.py            # Tool definitions + handlers
│   │   ├── schedules.py        # 9pm daily summary
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── supabase.py     # Nutrition DB operations
│   │       ├── garmin.py       # Steps API
│   │       └── withings.py     # Weight API
│   │
│   ├── news/
│   │   ├── __init__.py
│   │   ├── domain.py
│   │   ├── config.py
│   │   ├── tools.py
│   │   ├── schedules.py        # 7am briefing
│   │   └── services/
│   │       └── feeds.py        # RSS/API fetchers
│   │
│   └── api_usage/
│       ├── __init__.py
│       ├── domain.py
│       ├── config.py
│       ├── tools.py
│       ├── schedules.py        # Weekly summary
│       └── services/
│           ├── anthropic.py    # Claude usage API
│           └── openai.py       # OpenAI usage API
│
├── config.py                   # Global config (bot token, default model)
├── .env                        # Secrets (gitignored)
├── requirements.txt
└── README.md
```

---

## Dependencies (requirements.txt)

```
discord.py>=2.3.0
anthropic>=0.40.0
supabase>=2.0.0
garth>=0.4.0
httpx>=0.27.0
python-dotenv>=1.0.0
apscheduler>=3.10.0
feedparser>=6.0.0
```

---

## Environment Variables (.env)

```
# Discord
DISCORD_TOKEN=xxx

# Claude API
ANTHROPIC_API_KEY=sk-ant-api03-xxx

# Supabase (nutrition domain)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=xxx

# Garmin (nutrition domain)
GARMIN_EMAIL=xxx
GARMIN_PASSWORD=xxx

# Withings (nutrition domain)
WITHINGS_CLIENT_ID=xxx
WITHINGS_CLIENT_SECRET=xxx
WITHINGS_ACCESS_TOKEN=xxx
WITHINGS_REFRESH_TOKEN=xxx

# OpenAI (api_usage domain)
OPENAI_API_KEY=sk-xxx
```

---

## Core Components

### domains/base.py - Abstract Domain

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler

@dataclass
class ToolDefinition:
    """Claude API tool definition + handler"""
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Any]
    
    def to_api_format(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema
        }

@dataclass
class ScheduledTask:
    """Cron-style scheduled task"""
    name: str
    handler: Callable
    hour: int
    minute: int = 0
    day_of_week: str = "*"  # "*" = daily, "mon" = weekly on Monday, etc.

class Domain(ABC):
    """Base class for all domains"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Domain identifier"""
        pass
    
    @property
    @abstractmethod
    def channel_id(self) -> int:
        """Discord channel this domain handles"""
        pass
    
    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Claude system prompt for this domain"""
        pass
    
    @property
    @abstractmethod
    def tools(self) -> list[ToolDefinition]:
        """Available tools for this domain"""
        pass
    
    @property
    def schedules(self) -> list[ScheduledTask]:
        """Scheduled tasks (optional, default empty)"""
        return []
    
    def get_tool_definitions(self) -> list[dict]:
        """Format tools for Claude API"""
        return [t.to_api_format() for t in self.tools]
    
    def get_tool_handler(self, name: str) -> Callable | None:
        """Get handler function by tool name"""
        for tool in self.tools:
            if tool.name == name:
                return tool.handler
        return None
    
    def register_schedules(self, scheduler: AsyncIOScheduler, bot) -> None:
        """Register all scheduled tasks with the scheduler"""
        for task in self.schedules:
            scheduler.add_job(
                task.handler,
                'cron',
                args=[bot, self],
                hour=task.hour,
                minute=task.minute,
                day_of_week=task.day_of_week,
                id=f"{self.name}_{task.name}"
            )
```

### registry.py - Domain Registry

```python
from domains.base import Domain

class DomainRegistry:
    """Central registry for all domains"""
    
    def __init__(self):
        self._domains: dict[int, Domain] = {}  # channel_id → domain
        self._by_name: dict[str, Domain] = {}  # name → domain
    
    def register(self, domain: Domain) -> None:
        """Register a domain"""
        self._domains[domain.channel_id] = domain
        self._by_name[domain.name] = domain
    
    def get_by_channel(self, channel_id: int) -> Domain | None:
        """Get domain for a channel"""
        return self._domains.get(channel_id)
    
    def get_by_name(self, name: str) -> Domain | None:
        """Get domain by name"""
        return self._by_name.get(name)
    
    def all_domains(self) -> list[Domain]:
        """Get all registered domains"""
        return list(self._by_name.values())

# Global registry instance
registry = DomainRegistry()
```

### claude_client.py - Generic Claude Client

```python
import anthropic
from typing import Any

class ClaudeClient:
    """Generic Claude API client with tool support"""
    
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20241022"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
    
    async def chat(
        self,
        message: str,
        system: str,
        tools: list[dict],
        tool_handlers: dict[str, callable],
        max_iterations: int = 5
    ) -> str:
        """
        Send message, handle tool calls, return final response.
        
        Args:
            message: User message
            system: System prompt
            tools: Tool definitions for Claude API
            tool_handlers: Map of tool_name → handler function
            max_iterations: Max tool call rounds (safety limit)
        
        Returns:
            Final text response from Claude
        """
        messages = [{"role": "user", "content": message}]
        
        for _ in range(max_iterations):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                tools=tools if tools else None,
                messages=messages
            )
            
            # Check if we have tool use
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            
            if not tool_use_blocks:
                # No tool calls - extract text and return
                text_blocks = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_blocks)
            
            # Process tool calls
            messages.append({"role": "assistant", "content": response.content})
            
            tool_results = []
            for tool_use in tool_use_blocks:
                handler = tool_handlers.get(tool_use.name)
                if handler:
                    try:
                        result = await handler(**tool_use.input)
                    except Exception as e:
                        result = {"error": str(e)}
                else:
                    result = {"error": f"Unknown tool: {tool_use.name}"}
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": str(result)
                })
            
            messages.append({"role": "user", "content": tool_results})
        
        return "I've hit my processing limit. Please try a simpler request."
```

### bot.py - Main Bot

```python
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from claude_client import ClaudeClient
from registry import registry

# Import and register domains
from domains.nutrition import NutritionDomain
from domains.news import NewsDomain
from domains.api_usage import ApiUsageDomain

load_dotenv()

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize Claude client
claude = ClaudeClient(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    model=os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20241022")
)

# Initialize scheduler
scheduler = AsyncIOScheduler()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    
    # Register domains
    registry.register(NutritionDomain())
    registry.register(NewsDomain())
    registry.register(ApiUsageDomain())
    
    # Register all scheduled tasks
    for domain in registry.all_domains():
        domain.register_schedules(scheduler, bot)
    
    scheduler.start()
    print(f"Registered {len(registry.all_domains())} domains")

@bot.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        return
    
    # Find domain for this channel
    domain = registry.get_by_channel(message.channel.id)
    if not domain:
        return
    
    # Build tool handlers dict
    tool_handlers = {tool.name: tool.handler for tool in domain.tools}
    
    # Get response from Claude
    async with message.channel.typing():
        try:
            response = await claude.chat(
                message=message.content,
                system=domain.system_prompt,
                tools=domain.get_tool_definitions(),
                tool_handlers=tool_handlers
            )
            await message.channel.send(response)
        except Exception as e:
            await message.channel.send(f"Error: {str(e)[:100]}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
```

---

## Domain: Nutrition

### domains/nutrition/config.py

```python
CHANNEL_ID = 1465294449038069912

DAILY_TARGETS = {
    "calories": 2100,
    "protein_g": 160,
    "carbs_g": 263,
    "fat_g": 70,
    "water_ml": 3500,
    "steps": 15000
}

GOAL = {
    "target_weight_kg": 80,
    "deadline": "April 2026",
    "reason": "Family trip to Japan"
}

SYSTEM_PROMPT = """You are Chris's nutrition and fitness coach. Direct, no fluff - PT style.

## The Goal
Chris is targeting 80kg by April 2026 for a family trip to Japan. Current weight tracked via Withings.
This isn't just about numbers - it's about being fit and confident for an important family experience.

## Daily Targets
- Calories: 2,100 (slight deficit)
- Protein: 160g (PRIORITY - muscle retention while cutting)
- Carbs: 263g
- Fat: 70g  
- Water: 3,500ml
- Steps: 15,000

## Your Job
1. Log meals/water when asked - use tools, don't ask for confirmation
2. Track progress vs targets
3. Give brief, actionable advice
4. Prioritise protein - call it out if lagging
5. Connect daily choices to the Japan goal when motivation helps
6. Celebrate wins, push on gaps

## Tone
- Brief: 2-3 lines unless detail requested
- Direct: No "Great question!" fluff
- Supportive but honest: "You're short on protein" not "Maybe consider..."
- Occasional humour is fine

## Context Awareness
If it's evening and protein is low, suggest fixes.
If steps are lagging, nudge movement.
If weight is trending well, acknowledge it.
Keep the Japan goal as the north star.

## Logging Format
Users may log in various formats. Parse flexibly:
- "log breakfast porridge 408 18 53 15" → meal_type=breakfast, then calories/protein/carbs/fat
- "had a protein shake 150 cal 30g protein" → extract what's given, estimate rest
- "500ml water" → log_water
"""
```

### domains/nutrition/tools.py

```python
from domains.base import ToolDefinition
from .services.supabase import (
    insert_meal, insert_water, get_today_totals, 
    get_today_meals, get_week_summary
)
from .services.garmin import get_steps
from .services.withings import get_weight

TOOLS = [
    ToolDefinition(
        name="log_meal",
        description="Log a meal to the nutrition database",
        input_schema={
            "type": "object",
            "properties": {
                "meal_type": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                    "description": "Type of meal"
                },
                "description": {
                    "type": "string",
                    "description": "What was eaten"
                },
                "calories": {"type": "number"},
                "protein_g": {"type": "number"},
                "carbs_g": {"type": "number"},
                "fat_g": {"type": "number"}
            },
            "required": ["meal_type", "description", "calories", "protein_g", "carbs_g", "fat_g"]
        },
        handler=insert_meal
    ),
    
    ToolDefinition(
        name="log_water",
        description="Log water intake in ml",
        input_schema={
            "type": "object",
            "properties": {
                "ml": {"type": "number", "description": "Water amount in millilitres"}
            },
            "required": ["ml"]
        },
        handler=insert_water
    ),
    
    ToolDefinition(
        name="get_today_totals",
        description="Get today's nutrition totals (calories, protein, carbs, fat, water) and progress vs targets",
        input_schema={"type": "object", "properties": {}},
        handler=get_today_totals
    ),
    
    ToolDefinition(
        name="get_today_meals",
        description="Get list of all meals logged today with times",
        input_schema={"type": "object", "properties": {}},
        handler=get_today_meals
    ),
    
    ToolDefinition(
        name="get_steps",
        description="Get today's step count from Garmin",
        input_schema={"type": "object", "properties": {}},
        handler=get_steps
    ),
    
    ToolDefinition(
        name="get_weight",
        description="Get latest weight reading from Withings",
        input_schema={"type": "object", "properties": {}},
        handler=get_weight
    ),
    
    ToolDefinition(
        name="get_week_summary",
        description="Get daily totals for the past 7 days",
        input_schema={"type": "object", "properties": {}},
        handler=get_week_summary
    ),
]
```

### domains/nutrition/schedules.py

```python
from domains.base import ScheduledTask
from .services.supabase import get_today_totals
from .services.garmin import get_steps
from .services.withings import get_weight
from .config import CHANNEL_ID, DAILY_TARGETS

async def daily_summary(bot, domain):
    """Post 9pm daily summary"""
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return
    
    totals = await get_today_totals()
    steps = await get_steps()
    weight = await get_weight()
    
    # Build summary data for Claude to format
    summary_data = {
        "totals": totals,
        "steps": steps,
        "weight": weight,
        "targets": DAILY_TARGETS
    }
    
    # Use Claude to generate the summary message
    from claude_client import ClaudeClient
    import os
    
    claude = ClaudeClient(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    prompt = f"""Generate a daily summary based on this data:
{summary_data}

Format as:
📊 Daily Summary - [weekday] [date]

[emoji] Calories: actual / 2,100
[emoji] Protein: actual / 160g
[emoji] Carbs: actual / 263g
[emoji] Fat: actual / 70g
[emoji] Water: actual / 3,500ml
[emoji] Steps: actual / 15,000

💪 [one line on what went well]
🎯 [one line on tomorrow's focus]

⚖️ [current]kg → 80kg. [remaining]kg to go. [progress note]

Use ✅ for >=90% (or <=110% for calories), 🟡 for 70-89%, ❌ for <70%"""
    
    response = await claude.chat(
        message=prompt,
        system="You format nutrition summaries. Be concise and motivating.",
        tools=[],
        tool_handlers={}
    )
    
    await channel.send(response)

SCHEDULES = [
    ScheduledTask(
        name="daily_summary",
        handler=daily_summary,
        hour=21,
        minute=0
    )
]
```

### domains/nutrition/services/supabase.py

```python
import os
from datetime import datetime, timedelta
from supabase import create_client

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

async def insert_meal(meal_type: str, description: str, calories: float, 
                      protein_g: float, carbs_g: float, fat_g: float) -> dict:
    """Insert a meal record"""
    result = supabase.table("nutrition_logs").insert({
        "meal_type": meal_type,
        "description": description,
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g
    }).execute()
    
    return {"success": True, "id": result.data[0]["id"]}

async def insert_water(ml: float) -> dict:
    """Insert a water record"""
    result = supabase.table("nutrition_logs").insert({
        "meal_type": "water",
        "description": f"{ml}ml water",
        "water_ml": ml,
        "calories": 0,
        "protein_g": 0,
        "carbs_g": 0,
        "fat_g": 0
    }).execute()
    
    return {"success": True, "id": result.data[0]["id"]}

async def get_today_totals() -> dict:
    """Get today's nutrition totals"""
    today = datetime.now().date().isoformat()
    
    result = supabase.table("nutrition_logs")\
        .select("calories, protein_g, carbs_g, fat_g, water_ml")\
        .gte("logged_at", f"{today}T00:00:00")\
        .lt("logged_at", f"{today}T23:59:59")\
        .execute()
    
    totals = {
        "calories": sum(r["calories"] or 0 for r in result.data),
        "protein_g": sum(r["protein_g"] or 0 for r in result.data),
        "carbs_g": sum(r["carbs_g"] or 0 for r in result.data),
        "fat_g": sum(r["fat_g"] or 0 for r in result.data),
        "water_ml": sum(r["water_ml"] or 0 for r in result.data),
    }
    
    return totals

async def get_today_meals() -> list:
    """Get today's meals"""
    today = datetime.now().date().isoformat()
    
    result = supabase.table("nutrition_logs")\
        .select("*")\
        .gte("logged_at", f"{today}T00:00:00")\
        .lt("logged_at", f"{today}T23:59:59")\
        .neq("meal_type", "water")\
        .order("logged_at")\
        .execute()
    
    return result.data

async def get_week_summary() -> list:
    """Get last 7 days of totals"""
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)
    
    result = supabase.rpc("get_daily_totals", {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat()
    }).execute()
    
    return result.data
```

### domains/nutrition/services/garmin.py

```python
import os
from datetime import date
from garth.sso import login
from garth import Client

_client = None

def _get_client() -> Client:
    global _client
    if _client is None:
        _client = login(
            os.getenv("GARMIN_EMAIL"),
            os.getenv("GARMIN_PASSWORD")
        )
    return _client

async def get_steps() -> dict:
    """Get today's step count"""
    try:
        client = _get_client()
        today = date.today().isoformat()
        
        # Garth API call for daily summary
        data = client.connectapi(f"/usersummary-service/usersummary/daily/{today}")
        
        steps = data.get("totalSteps", 0)
        goal = data.get("dailyStepGoal", 15000)
        
        return {
            "steps": steps,
            "goal": goal,
            "percentage": round((steps / goal) * 100) if goal else 0
        }
    except Exception as e:
        return {"error": str(e), "steps": None}
```

### domains/nutrition/services/withings.py

```python
import os
import httpx
from datetime import datetime

async def get_weight() -> dict:
    """Get latest weight from Withings"""
    try:
        access_token = os.getenv("WITHINGS_ACCESS_TOKEN")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://wbsapi.withings.net/measure",
                data={
                    "action": "getmeas",
                    "meastype": 1,  # Weight
                    "category": 1,  # Real measurements
                    "lastupdate": 0
                },
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            data = response.json()
            
            if data["status"] != 0:
                # Token may need refresh
                await _refresh_token()
                return await get_weight()  # Retry once
            
            # Get most recent measurement
            measures = data["body"]["measuregrps"]
            if not measures:
                return {"weight_kg": None, "date": None}
            
            latest = measures[0]
            weight_raw = latest["measures"][0]["value"]
            unit = latest["measures"][0]["unit"]
            weight_kg = weight_raw * (10 ** unit)
            
            return {
                "weight_kg": round(weight_kg, 1),
                "date": datetime.fromtimestamp(latest["date"]).isoformat()
            }
    except Exception as e:
        return {"error": str(e), "weight_kg": None}

async def _refresh_token():
    """Refresh Withings OAuth token"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://wbsapi.withings.net/v2/oauth2",
            data={
                "action": "requesttoken",
                "grant_type": "refresh_token",
                "client_id": os.getenv("WITHINGS_CLIENT_ID"),
                "client_secret": os.getenv("WITHINGS_CLIENT_SECRET"),
                "refresh_token": os.getenv("WITHINGS_REFRESH_TOKEN")
            }
        )
        
        data = response.json()
        if data["status"] == 0:
            # Update tokens - in practice, write to .env or token file
            new_access = data["body"]["access_token"]
            new_refresh = data["body"]["refresh_token"]
            os.environ["WITHINGS_ACCESS_TOKEN"] = new_access
            os.environ["WITHINGS_REFRESH_TOKEN"] = new_refresh
```

### domains/nutrition/domain.py

```python
from domains.base import Domain, ToolDefinition, ScheduledTask
from .config import CHANNEL_ID, SYSTEM_PROMPT
from .tools import TOOLS
from .schedules import SCHEDULES

class NutritionDomain(Domain):
    
    @property
    def name(self) -> str:
        return "nutrition"
    
    @property
    def channel_id(self) -> int:
        return CHANNEL_ID
    
    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT
    
    @property
    def tools(self) -> list[ToolDefinition]:
        return TOOLS
    
    @property
    def schedules(self) -> list[ScheduledTask]:
        return SCHEDULES
```

### domains/nutrition/__init__.py

```python
from .domain import NutritionDomain

__all__ = ["NutritionDomain"]
```

---

## Domain: News (Stub)

### domains/news/config.py

```python
CHANNEL_ID = 123456789  # Your #news channel ID

SOURCES = {
    "tech": [
        "https://news.ycombinator.com/rss",
        "https://feeds.arstechnica.com/arstechnica/technology-lab",
    ],
    "uk": [
        "https://feeds.bbci.co.uk/news/uk/rss.xml",
    ],
    "f1": [
        "https://www.autosport.com/rss/f1/news/",
    ]
}

SYSTEM_PROMPT = """You are Chris's news assistant. Concise, factual, no fluff.

## Your Job
1. Summarise news when asked - 2-3 sentences per story max
2. Fetch full articles when asked to dig deeper
3. Morning briefings: top 5 stories across tech, UK news, F1
4. No editorialising - just the facts

## Tone
- Brief and scannable
- Use bullet points for multiple stories
- Include source attribution
"""
```

### domains/news/tools.py

```python
from domains.base import ToolDefinition
from .services.feeds import fetch_feed, fetch_article

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
                    "description": "Max headlines to return",
                    "default": 10
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
```

### domains/news/schedules.py

```python
from domains.base import ScheduledTask

async def morning_briefing(bot, domain):
    """Post 7am news briefing"""
    channel = bot.get_channel(domain.channel_id)
    if not channel:
        return
    
    # Fetch headlines and have Claude summarise
    # Similar pattern to nutrition daily_summary
    pass

SCHEDULES = [
    ScheduledTask(
        name="morning_briefing",
        handler=morning_briefing,
        hour=7,
        minute=0
    )
]
```

---

## Domain: API Usage (Stub)

### domains/api_usage/config.py

```python
CHANNEL_ID = 987654321  # Your #api-usage channel ID

BUDGET_ALERTS = {
    "daily_warning": 1.00,   # Warn if daily spend exceeds $1
    "monthly_budget": 20.00  # Monthly budget cap
}

SYSTEM_PROMPT = """You track Chris's AI API usage and costs.

## Your Job
1. Report usage when asked
2. Break down by model/project
3. Alert on unusual spend
4. Weekly summaries

## Tone
- Factual, numbers-focused
- Flag anomalies clearly
"""
```

### domains/api_usage/tools.py

```python
from domains.base import ToolDefinition
from .services.anthropic import get_anthropic_usage
from .services.openai import get_openai_usage

TOOLS = [
    ToolDefinition(
        name="get_anthropic_usage",
        description="Get Claude API usage for a period",
        input_schema={
            "type": "object",
            "properties": {
                "days": {"type": "number", "default": 7}
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
                "days": {"type": "number", "default": 7}
            }
        },
        handler=get_openai_usage
    ),
]
```

---

## Database Schema

### nutrition_logs (existing)

```sql
CREATE TABLE nutrition_logs (
    id BIGSERIAL PRIMARY KEY,
    meal_type TEXT NOT NULL,
    description TEXT,
    calories NUMERIC DEFAULT 0,
    protein_g NUMERIC DEFAULT 0,
    carbs_g NUMERIC DEFAULT 0,
    fat_g NUMERIC DEFAULT 0,
    water_ml NUMERIC DEFAULT 0,
    logged_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for date queries
CREATE INDEX idx_nutrition_logs_date ON nutrition_logs (logged_at);

-- Function for weekly summary
CREATE OR REPLACE FUNCTION get_daily_totals(start_date DATE, end_date DATE)
RETURNS TABLE (
    log_date DATE,
    calories NUMERIC,
    protein_g NUMERIC,
    carbs_g NUMERIC,
    fat_g NUMERIC,
    water_ml NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        DATE(logged_at) as log_date,
        SUM(n.calories) as calories,
        SUM(n.protein_g) as protein_g,
        SUM(n.carbs_g) as carbs_g,
        SUM(n.fat_g) as fat_g,
        SUM(n.water_ml) as water_ml
    FROM nutrition_logs n
    WHERE DATE(logged_at) BETWEEN start_date AND end_date
    GROUP BY DATE(logged_at)
    ORDER BY log_date;
END;
$$ LANGUAGE plpgsql;
```

---

## Adding a New Domain - Checklist

1. **Create folder:** `domains/your_domain/`

2. **Create files:**
   - `__init__.py` - Export your domain class
   - `config.py` - Channel ID, system prompt, any constants
   - `tools.py` - Tool definitions list
   - `schedules.py` - Scheduled tasks list (can be empty)
   - `domain.py` - Domain class inheriting from base
   - `services/` - Any external API integrations

3. **Implement domain class:**
   ```python
   from domains.base import Domain
   from .config import CHANNEL_ID, SYSTEM_PROMPT
   from .tools import TOOLS
   from .schedules import SCHEDULES
   
   class YourDomain(Domain):
       @property
       def name(self) -> str:
           return "your_domain"
       
       @property
       def channel_id(self) -> int:
           return CHANNEL_ID
       
       @property
       def system_prompt(self) -> str:
           return SYSTEM_PROMPT
       
       @property
       def tools(self) -> list:
           return TOOLS
       
       @property
       def schedules(self) -> list:
           return SCHEDULES
   ```

4. **Register in bot.py:**
   ```python
   from domains.your_domain import YourDomain
   
   # In on_ready()
   registry.register(YourDomain())
   ```

5. **Add channel ID to Discord** and update .env if new secrets needed

---

## Error Handling

| Error | Behaviour |
|-------|-----------|
| Supabase down | Log error, respond "Database unavailable" |
| Garmin API fails | Return nutrition data only, note steps unavailable |
| Withings token expired | Auto-refresh, retry once, then error |
| Claude API fails | Respond "AI unavailable, try again shortly" |
| Unknown tool called | Return error to Claude, let it recover |
| Domain not found for channel | Silently ignore message |

---

## Running

**Development:**
```bash
python bot.py
```

**Production (Windows):**
- Scheduled task on startup, or
- `pythonw.exe bot.py` for background, or
- PM2/forever equivalent for Windows

---

## Implementation Order

1. **Core framework:** `base.py`, `registry.py`, `claude_client.py`, `bot.py`
2. **Nutrition domain:** Get meal logging working end-to-end
3. **Garmin integration:** Add steps tracking
4. **Withings integration:** Add weight tracking (token refresh is fiddly)
5. **Daily summary:** Add scheduled task
6. **News domain:** Stub out, implement feeds
7. **API usage domain:** Stub out, implement usage APIs

Test each component independently before wiring together.

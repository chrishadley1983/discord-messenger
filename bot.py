"""Discord Personal Assistant - Main Bot.

A modular Discord bot with AI coaching/assistance via Claude API.
Routes messages to domain handlers based on channel.
"""

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from claude_client import ClaudeClient
from registry import registry
from logger import logger

# Import domains
from domains.nutrition import NutritionDomain
from domains.news import NewsDomain
from domains.api_usage import ApiUsageDomain

# Import Claude Code domain (special routing - no LLM)
from domains.claude_code import (
    handle_message as handle_claude_code,
    on_bot_startup as claude_code_startup,
    CHANNEL_ID as CLAUDE_CODE_CHANNEL
)

# Import Peterbot domain (special routing - Claude Code with memory)
from domains.peterbot import (
    handle_message as handle_peterbot,
    on_startup as peterbot_startup,
    CHANNEL_ID as PETERBOT_CHANNEL
)

# Import standalone jobs
from jobs import (
    register_morning_briefing,
    register_balance_monitor,
    register_school_run,
    register_nutrition_morning,
    register_hydration_checkin,
    register_weekly_health,
    register_monthly_health,
    register_withings_sync,
    register_youtube_feed
)
from jobs.balance_monitor import balance_monitor
from jobs.hydration_checkin import hydration_checkin
from jobs.morning_briefing import ai_morning_briefing
from jobs.nutrition_morning import nutrition_morning_message
from jobs.school_run import school_run_report, school_pickup_report
from jobs.weekly_health import weekly_health_summary
from jobs.monthly_health import monthly_health_summary
from jobs.youtube_feed import youtube_feed

load_dotenv()

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize Claude client - using renamed var to prevent Claude Code pickup
claude = ClaudeClient(
    api_key=os.getenv("DISCORD_BOT_CLAUDE_KEY"),
    model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
)

# Initialize scheduler
scheduler = AsyncIOScheduler()


@bot.event
async def on_ready():
    """Called when bot is connected and ready."""
    logger.info(f"Logged in as {bot.user}")

    # Register domains
    registry.register(NutritionDomain())
    registry.register(NewsDomain())
    registry.register(ApiUsageDomain())
    # Note: PeterbotDomain no longer registered - uses special routing like claude-code

    # Register domain scheduled tasks
    for domain in registry.all_domains():
        domain.register_schedules(scheduler, bot)
        logger.info(f"Registered domain: {domain.name} (channel: {domain.channel_id})")

    # Register standalone jobs
    register_morning_briefing(scheduler, bot)
    register_balance_monitor(scheduler, bot)
    register_school_run(scheduler, bot)
    register_withings_sync(scheduler)  # Sync weight data before morning message
    register_nutrition_morning(scheduler, bot)
    register_hydration_checkin(scheduler, bot)
    register_weekly_health(scheduler, bot)
    register_monthly_health(scheduler, bot)
    register_youtube_feed(scheduler, bot)

    # Start scheduler
    scheduler.start()
    logger.info(f"Scheduler started with {len(scheduler.get_jobs())} jobs")
    logger.info(f"Bot ready - {len(registry.all_domains())} domains registered")

    # Claude Code domain startup - restore active session
    startup_msg = claude_code_startup()
    if startup_msg:
        channel = bot.get_channel(CLAUDE_CODE_CHANNEL)
        if channel:
            await channel.send(startup_msg)

    # Peterbot domain startup - start memory retry task
    peterbot_startup()


async def fetch_conversation_history(channel, limit: int = 15) -> list[dict]:
    """Fetch recent messages and format as conversation history for Claude."""
    history = []

    async for msg in channel.history(limit=limit):
        # Skip if message is empty
        if not msg.content and not msg.attachments:
            continue

        # Determine role
        role = "assistant" if msg.author.bot else "user"

        # Build content
        content = []

        # Add images first (for user messages)
        if not msg.author.bot:
            for attachment in msg.attachments:
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    # We'll handle image fetching in claude_client
                    content.append({
                        "type": "image_url",
                        "url": attachment.url
                    })

        # Add text
        if msg.content:
            content.append({
                "type": "text",
                "text": msg.content
            })

        if content:
            history.append({
                "role": role,
                "content": content,
                "timestamp": msg.created_at
            })

    # Reverse to chronological order (oldest first)
    history.reverse()

    # Merge consecutive same-role messages (Claude requires alternating roles)
    merged = []
    for msg in history:
        if merged and merged[-1]["role"] == msg["role"]:
            # Merge content
            merged[-1]["content"].extend(msg["content"])
        else:
            merged.append(msg)

    return merged


@bot.event
async def on_message(message):
    """Handle incoming messages."""
    # Ignore bot messages
    if message.author.bot:
        return

    # Claude Code domain - direct routing, no LLM
    if message.channel.id == CLAUDE_CODE_CHANNEL:
        response = handle_claude_code(message.content)
        await message.channel.send(response)
        return

    # Peterbot domain - Claude Code routing WITH memory context
    if message.channel.id == PETERBOT_CHANNEL:
        async with message.channel.typing():
            response = await handle_peterbot(message.content, message.author.id)
            # Split long messages (Discord 2000 char limit)
            if len(response) > 2000:
                for i in range(0, len(response), 2000):
                    await message.channel.send(response[i:i+2000])
            else:
                await message.channel.send(response)
        return

    # Process commands first (e.g., !balance)
    # This must be called for @bot.command decorators to work
    await bot.process_commands(message)

    # If message is a command, don't also send to AI
    if message.content.startswith("!"):
        return

    # Find domain for this channel
    domain = registry.get_by_channel(message.channel.id)
    if not domain:
        # Silently ignore messages in unregistered channels
        return

    logger.info(f"Message in #{message.channel.name} ({domain.name}): {(message.content or '[image]')[:50]}...")

    # Fetch conversation history (includes current message)
    conversation_history = await fetch_conversation_history(message.channel, limit=15)
    logger.info(f"Fetched {len(conversation_history)} messages for context")

    # Build tool handlers dict
    tool_handlers = {tool.name: tool.handler for tool in domain.tools}

    # Get response from Claude
    async with message.channel.typing():
        try:
            response = await claude.chat_with_history(
                conversation=conversation_history,
                system=domain.system_prompt,
                tools=domain.get_tool_definitions(),
                tool_handlers=tool_handlers
            )

            # Split long messages (Discord has 2000 char limit)
            if len(response) > 2000:
                for i in range(0, len(response), 2000):
                    await message.channel.send(response[i:i+2000])
            else:
                await message.channel.send(response)

            logger.info(f"Response sent ({len(response)} chars)")

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await message.channel.send("AI unavailable, try again shortly.")


@bot.command(name="balance")
async def cmd_balance(ctx):
    """Manually trigger the balance monitor job."""
    logger.info(f"Manual balance check triggered by {ctx.author}")
    await ctx.send("🔄 Checking API balances...")
    await balance_monitor(bot)


@bot.command(name="hydration")
async def cmd_hydration(ctx):
    """Manually trigger the hydration check-in job."""
    logger.info(f"Manual hydration check triggered by {ctx.author}")
    await ctx.send("🔄 Checking hydration & steps...")
    await hydration_checkin(bot)


@bot.command(name="briefing")
async def cmd_briefing(ctx):
    """Manually trigger the AI morning briefing job."""
    logger.info(f"Manual AI briefing triggered by {ctx.author}")
    await ctx.send("🔄 Generating AI morning briefing...")
    await ai_morning_briefing(bot)


@bot.command(name="morning")
async def cmd_morning(ctx):
    """Manually trigger the morning health digest job."""
    logger.info(f"Manual morning digest triggered by {ctx.author}")
    await ctx.send("🔄 Generating morning health digest...")
    await nutrition_morning_message(bot)


@bot.command(name="schoolrun")
async def cmd_schoolrun(ctx):
    """Manually trigger the school run report job."""
    logger.info(f"Manual school run report triggered by {ctx.author}")
    await ctx.send("🔄 Generating school run report...")
    await school_run_report(bot)


@bot.command(name="schoolpickup")
async def cmd_schoolpickup(ctx):
    """Manually trigger the school pickup report job."""
    logger.info(f"Manual school pickup report triggered by {ctx.author}")
    await ctx.send("🔄 Generating school pickup report...")
    await school_pickup_report(bot)


@bot.command(name="weeklyhealth")
async def cmd_weeklyhealth(ctx):
    """Manually trigger the weekly health summary job."""
    logger.info(f"Manual weekly health summary triggered by {ctx.author}")
    await ctx.send("🔄 Generating weekly health summary with graphs...")
    await weekly_health_summary(bot)


@bot.command(name="monthlyhealth")
async def cmd_monthlyhealth(ctx):
    """Manually trigger the monthly health summary job."""
    logger.info(f"Manual monthly health summary triggered by {ctx.author}")
    await ctx.send("🔄 Generating monthly health summary with graphs...")
    await monthly_health_summary(bot)


@bot.command(name="youtube")
async def cmd_youtube(ctx):
    """Manually trigger the YouTube daily digest job."""
    logger.info(f"Manual YouTube digest triggered by {ctx.author}")
    await ctx.send("🔄 Generating YouTube daily digest...")
    await youtube_feed(bot)


@bot.event
async def on_error(event, *args, **kwargs):
    """Handle errors."""
    logger.error(f"Bot error in {event}: {args}")


def main():
    """Entry point."""
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN not set")
        return

    logger.info("Starting Discord Assistant...")
    bot.run(token)


if __name__ == "__main__":
    main()

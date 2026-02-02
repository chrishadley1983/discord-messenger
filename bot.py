"""Discord Personal Assistant - Main Bot.

A modular Discord bot with AI coaching/assistance via Claude API.
Routes messages to domain handlers based on channel.
"""

import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from claude_client import ClaudeClient
from registry import registry
from logger import logger
from config import DISCORD_TOKEN, ANTHROPIC_API_KEY, CLAUDE_MODEL

# Import domains
# NutritionDomain disabled - #food-log now routes through Peterbot with Hadley API
# from domains.nutrition import NutritionDomain
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
from domains.peterbot.config import PETERBOT_CHANNEL_IDS
from domains.peterbot.memory import is_buffer_empty, populate_buffer_from_history

# Import Response Processing Pipeline (Stage 1-5 processing)
from domains.peterbot.response.pipeline import process as process_response

# Import Peterbot scheduler (Phase 7)
from domains.peterbot.scheduler import PeterbotScheduler
from domains.peterbot.data_fetchers import SKILL_DATA_FETCHERS

# Import reminders handler (one-off reminders)
from domains.peterbot.reminders.handler import (
    reload_reminders_on_startup,
    handle_reminder_intent,
    start_reminder_polling
)

# Import standalone jobs (legacy - kept for manual triggers during migration)
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

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Initialize Claude client - using config vars
claude = ClaudeClient(
    api_key=ANTHROPIC_API_KEY,
    model=CLAUDE_MODEL
)

# Initialize scheduler
scheduler = AsyncIOScheduler()

# Message deduplication: track recently processed message IDs
_processed_messages: dict[int, float] = {}  # message_id -> timestamp
MESSAGE_DEDUP_SECONDS = 5

# Peterbot scheduler (Phase 7 - skill-based jobs)
# Set to True to use new SCHEDULE.md-based scheduler, False for legacy jobs
USE_PETERBOT_SCHEDULER = True  # Phase 7b complete - skills created
peterbot_scheduler = None  # Initialized in on_ready


@bot.event
async def on_ready():
    """Called when bot is connected and ready."""
    logger.info(f"Logged in as {bot.user}")

    # Sync slash commands with Discord
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash commands")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

    # Register domains
    # NutritionDomain disabled - #food-log now uses Peterbot routing with Hadley API
    # registry.register(NutritionDomain())
    registry.register(NewsDomain())
    registry.register(ApiUsageDomain())
    # Note: PeterbotDomain no longer registered - uses special routing like claude-code

    # Register domain scheduled tasks
    for domain in registry.all_domains():
        domain.register_schedules(scheduler, bot)
        logger.info(f"Registered domain: {domain.name} (channel: {domain.channel_id})")

    # Phase 7: Initialize Peterbot scheduler
    global peterbot_scheduler
    peterbot_scheduler = PeterbotScheduler(bot, scheduler, PETERBOT_CHANNEL)
    peterbot_scheduler.set_data_fetchers(SKILL_DATA_FETCHERS)

    if USE_PETERBOT_SCHEDULER:
        # Phase 7: Use SCHEDULE.md-based jobs via Claude Code
        job_count = peterbot_scheduler.load_schedule()
        logger.info(f"Peterbot scheduler loaded {job_count} jobs from SCHEDULE.md")
    else:
        # Legacy: Register standalone jobs (remove after Phase 7b migration)
        register_morning_briefing(scheduler, bot)
        register_balance_monitor(scheduler, bot)
        register_school_run(scheduler, bot)
        register_withings_sync(scheduler)  # Sync weight data before morning message
        register_nutrition_morning(scheduler, bot)
        register_hydration_checkin(scheduler, bot)
        register_weekly_health(scheduler, bot)
        register_monthly_health(scheduler, bot)
        register_youtube_feed(scheduler, bot)
        logger.info("Using legacy job registration (Phase 7 scheduler disabled)")

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

    # Reload pending reminders from Supabase
    try:
        reminder_count = await reload_reminders_on_startup(scheduler, bot)
        if reminder_count > 0:
            logger.info(f"Reloaded {reminder_count} pending reminders")
        # Start polling for reminders added by Peter/external systems
        start_reminder_polling(scheduler, bot)
    except Exception as e:
        logger.error(f"Failed to reload reminders: {e}")


async def fetch_peterbot_history(channel, limit: int = 10) -> list[dict]:
    """Fetch recent messages for Peterbot buffer population.

    Called when buffer is empty (e.g., after restart) to restore context.

    Args:
        channel: Discord channel object
        limit: Max messages to fetch (default 10, excluding current)

    Returns:
        List of {'role': 'user'|'assistant', 'content': str} in chronological order
    """
    messages = []

    try:
        async for msg in channel.history(limit=limit + 1):  # +1 to skip current
            # Skip empty messages
            if not msg.content:
                continue

            role = "assistant" if msg.author.bot else "user"
            messages.append({
                "role": role,
                "content": msg.content
            })

        # Reverse to chronological (oldest first) and skip the current message
        messages.reverse()
        if messages:
            messages = messages[:-1]  # Remove the most recent (current message)

        logger.debug(f"Fetched {len(messages)} messages from Discord history for buffer")
        return messages

    except Exception as e:
        logger.error(f"Failed to fetch Discord history: {e}")
        return []


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

    # Message deduplication - prevent processing same message twice
    import time
    now = time.time()
    if message.id in _processed_messages:
        logger.debug(f"Skipping duplicate message {message.id}")
        return
    _processed_messages[message.id] = now
    # Clean up old entries
    cutoff = now - MESSAGE_DEDUP_SECONDS * 2
    keys_to_delete = [k for k, v in _processed_messages.items() if v < cutoff]
    for k in keys_to_delete:
        del _processed_messages[k]

    # Note: Slash commands (/skill, /status, /reload-schedule) are handled
    # automatically by Discord - no need for prefix processing here

    # Claude Code domain - direct routing, no LLM
    if message.channel.id == CLAUDE_CODE_CHANNEL:
        response = handle_claude_code(message.content)
        await message.channel.send(response)
        return

    # Peterbot domain - Claude Code routing WITH memory context
    # Works in multiple channels (peterbot, ai-briefings, etc.)
    if message.channel.id in PETERBOT_CHANNEL_IDS:
        async with message.channel.typing():
            # Check for reminder intents first (handled locally, not via Claude Code)
            reminder_response = await handle_reminder_intent(
                message.content,
                message.author.id,
                message.channel.id,
                scheduler,
                bot
            )
            if reminder_response:
                await message.channel.send(reminder_response)
                return

            # Check if buffer needs populating from Discord history (e.g., after restart)
            if is_buffer_empty(message.channel.id):
                logger.info(f"Buffer empty for channel {message.channel.id}, fetching Discord history")
                history_messages = await fetch_peterbot_history(message.channel)
                if history_messages:
                    populate_buffer_from_history(message.channel.id, history_messages)

            # Define interim callback for "working on it" messages
            async def post_interim(text: str):
                """Post interim status update to channel."""
                await message.channel.send(text)

            # Define busy callback for when Peter is working on another task
            async def post_busy(text: str):
                """Post busy notification when Peter is handling another request."""
                await message.channel.send(text)

            # Normal peterbot routing to Claude Code (with interim updates)
            raw_response = await handle_peterbot(
                message.content,
                message.author.id,
                message.channel.id,
                interim_callback=post_interim,
                busy_callback=post_busy
            )

            # Process through Response Pipeline (sanitise → classify → format → chunk)
            processed = process_response(raw_response, {'user_prompt': message.content})

            # Send chunks (pipeline handles Discord 2000 char limit)
            for i, chunk in enumerate(processed.chunks):
                if not chunk.strip():
                    continue  # Skip empty chunks

                # First chunk can include embed
                if i == 0 and processed.embed:
                    embed_obj = discord.Embed.from_dict(processed.embed)
                    await message.channel.send(chunk, embed=embed_obj)
                else:
                    await message.channel.send(chunk)

            # Send additional embeds (e.g., image results)
            for embed_data in processed.embeds:
                embed_obj = discord.Embed.from_dict(embed_data)
                await message.channel.send(embed=embed_obj)

            # Add reactions if specified (for alerts)
            if processed.reactions:
                for reaction in processed.reactions:
                    try:
                        await message.add_reaction(reaction)
                    except discord.HTTPException:
                        pass  # Reaction failed, continue

            logger.debug(f"Response processed: type={processed.response_type.value}, "
                        f"chunks={len(processed.chunks)}, raw={processed.raw_length}, final={processed.final_length}")
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






@bot.tree.command(name="skill", description="Manually trigger a skill")
@app_commands.describe(skill_name="The skill to run (e.g., hydration, balance-monitor, news)")
async def cmd_skill(interaction: discord.Interaction, skill_name: str = None):
    """Manually trigger a skill via the Phase 7 scheduler."""
    if not USE_PETERBOT_SCHEDULER:
        await interaction.response.send_message("⚠️ Peterbot scheduler not enabled.")
        return

    if not skill_name:
        # List available skills
        skills = [
            "balance-monitor", "hydration", "morning-briefing", "health-digest",
            "school-run", "school-pickup", "weekly-health", "monthly-health",
            "nutrition-summary", "youtube-digest", "api-usage", "news", "heartbeat"
        ]
        await interaction.response.send_message(f"**Available skills:**\n`{'`, `'.join(skills)}`\n\nUsage: `/skill <name>`")
        return

    logger.info(f"Manual skill trigger: {skill_name} by {interaction.user}")
    await interaction.response.send_message(f"🔄 Running skill: {skill_name}...")

    try:
        # Create a minimal job config for manual execution
        from domains.peterbot.scheduler import JobConfig
        job = JobConfig(
            name=f"Manual: {skill_name}",
            skill=skill_name,
            schedule="manual",
            channel=f"#{interaction.channel.name}",
            enabled=True,
            job_type="manual",
            whatsapp=False
        )

        # Execute via scheduler (bypasses quiet hours for manual triggers)
        await peterbot_scheduler._execute_job_manual(job, interaction.channel.id)

    except Exception as e:
        logger.error(f"Skill execution failed: {e}")
        await interaction.followup.send(f"❌ Skill failed: {e}")


@bot.tree.command(name="reload-schedule", description="Reload SCHEDULE.md and re-register jobs")
async def cmd_reload_schedule(interaction: discord.Interaction):
    """Reload SCHEDULE.md and re-register jobs (Phase 7)."""
    if not USE_PETERBOT_SCHEDULER:
        await interaction.response.send_message("⚠️ Peterbot scheduler not enabled. Set USE_PETERBOT_SCHEDULER=True in bot.py")
        return

    logger.info(f"Schedule reload triggered by {interaction.user}")
    await interaction.response.send_message("🔄 Reloading SCHEDULE.md...")

    try:
        job_count = peterbot_scheduler.reload_schedule()
        await interaction.followup.send(f"✅ Loaded {job_count} jobs from SCHEDULE.md")
    except Exception as e:
        logger.error(f"Schedule reload failed: {e}")
        await interaction.followup.send(f"❌ Reload failed: {e}")


@bot.tree.command(name="remind", description="Set a one-off reminder")
@app_commands.describe(
    time="When to remind (e.g., '9am tomorrow', 'Monday 8:30am')",
    task="What to remind you about"
)
async def cmd_remind(interaction: discord.Interaction, time: str, task: str):
    """Set a one-off reminder."""
    from domains.peterbot.reminders.parser import parse_reminder
    from domains.peterbot.reminders.scheduler import add_reminder
    from domains.peterbot.reminders.executor import execute_reminder
    import uuid

    # Combine time and task for parsing
    full_text = f"at {time} to {task}"
    parsed = parse_reminder(full_text)

    if not parsed:
        await interaction.response.send_message(
            f"Couldn't parse time '{time}'. Try formats like '9am tomorrow', 'Monday 8:30am', '2pm today'.",
            ephemeral=True
        )
        return

    reminder_id = f"remind_{uuid.uuid4().hex[:8]}"

    async def executor_wrapper(t, uid, cid, rid):
        await execute_reminder(t, uid, cid, rid, bot)

    try:
        await add_reminder(
            scheduler=scheduler,
            reminder_id=reminder_id,
            run_at=parsed.run_at,
            task=task,  # Use original task, not parsed
            user_id=interaction.user.id,
            channel_id=interaction.channel.id,
            executor_func=executor_wrapper
        )

        await interaction.response.send_message(
            f"**Reminder set for {parsed.raw_time}**\n\n> {task}"
        )
    except Exception as e:
        logger.error(f"Failed to set reminder: {e}")
        await interaction.response.send_message(f"Failed to set reminder: {e}", ephemeral=True)


@bot.tree.command(name="reminders", description="List your pending reminders")
async def cmd_reminders(interaction: discord.Interaction):
    """List pending reminders."""
    from domains.peterbot.reminders.store import get_user_reminders
    from dateutil.parser import parse as parse_dt
    from zoneinfo import ZoneInfo

    UK_TZ = ZoneInfo("Europe/London")
    reminders = await get_user_reminders(interaction.user.id)

    if not reminders:
        await interaction.response.send_message("No active reminders.", ephemeral=True)
        return

    lines = ["**Your reminders:**\n"]
    for r in reminders:
        run_at = parse_dt(r['run_at'])
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=UK_TZ)
        else:
            run_at = run_at.astimezone(UK_TZ)

        lines.append(f"- {run_at.strftime('%a %d %b %H:%M')} - {r['task']}")
        lines.append(f"  `/cancel-reminder {r['id'][:8]}`")

    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="cancel-reminder", description="Cancel a pending reminder")
@app_commands.describe(reminder_id="The reminder ID (first 8 characters)")
async def cmd_cancel_reminder(interaction: discord.Interaction, reminder_id: str):
    """Cancel a pending reminder."""
    from domains.peterbot.reminders.store import get_user_reminders
    from domains.peterbot.reminders.scheduler import cancel_reminder

    reminders = await get_user_reminders(interaction.user.id)

    for r in reminders:
        if r['id'].startswith(reminder_id) or r['id'].endswith(reminder_id):
            if await cancel_reminder(scheduler, r['id']):
                await interaction.response.send_message(f"Cancelled reminder: {r['task']}")
                return
            else:
                await interaction.response.send_message("Failed to cancel reminder.", ephemeral=True)
                return

    await interaction.response.send_message(
        "Reminder not found. Use `/reminders` to see your reminders.",
        ephemeral=True
    )


@bot.tree.command(name="status", description="Show Peterbot system status")
async def cmd_status(interaction: discord.Interaction):
    """Show Peterbot system status."""
    import aiohttp
    from datetime import datetime
    from zoneinfo import ZoneInfo

    UK_TZ = ZoneInfo("Europe/London")

    if not USE_PETERBOT_SCHEDULER:
        await interaction.response.send_message("⚠️ Peterbot scheduler not enabled.")
        return

    lines = ["📊 **Peterbot Status**", ""]

    # Scheduler info
    job_count = len(peterbot_scheduler._job_ids)
    lines.append(f"**Scheduler:** {job_count} jobs loaded from SCHEDULE.md")

    # Skills info
    try:
        manifest_path = peterbot_scheduler.skills_path / "manifest.json"
        if manifest_path.exists():
            import json
            manifest = json.loads(manifest_path.read_text())
            total = len(manifest)
            conversational = sum(1 for s in manifest.values() if s.get("conversational", True))
            scheduled_only = total - conversational
            lines.append(f"**Skills:** {total} available ({conversational} conversational, {scheduled_only} scheduled-only)")
        else:
            lines.append("**Skills:** manifest.json not found (run /reload-schedule)")
    except Exception as e:
        lines.append(f"**Skills:** Error reading manifest: {e}")

    # Memory endpoint health
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:37777/health",
                timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                if resp.status == 200:
                    lines.append("**Memory endpoint:** healthy ✅")
                else:
                    lines.append(f"**Memory endpoint:** unhealthy ({resp.status}) ⚠️")
    except Exception:
        lines.append("**Memory endpoint:** not responding ❌")

    # Recent job status
    job_status = peterbot_scheduler.get_job_status()
    if job_status:
        lines.append("")
        lines.append("**Recent job status:**")
        for skill, success in list(job_status.items())[-5:]:  # Last 5
            icon = "✅" if success else "❌"
            lines.append(f"{icon} {skill}")
    else:
        lines.append("")
        lines.append("**Recent jobs:** No jobs have run yet")

    # Quiet hours check
    now = datetime.now(UK_TZ)
    if now.hour >= 23 or now.hour < 6:
        lines.append("")
        lines.append("⏸️ **Quiet hours active** (23:00-06:00 UK)")

    await interaction.response.send_message("\n".join(lines))


# =============================================================================
# SECOND BRAIN COMMANDS
# =============================================================================

@bot.tree.command(name="save", description="Save content to your Second Brain")
@app_commands.describe(
    content="URL or text to save",
    note="Optional note or annotation",
    tags="Optional tags (comma-separated)"
)
async def cmd_save(
    interaction: discord.Interaction,
    content: str,
    note: str = None,
    tags: str = None
):
    """Save content to Second Brain."""
    from domains.second_brain.commands import handle_save

    await interaction.response.defer()  # May take a while

    user_tags = [t.strip() for t in tags.split(",")] if tags else None

    try:
        response = await handle_save(content, user_note=note, user_tags=user_tags)
        await interaction.followup.send(response)
    except Exception as e:
        logger.error(f"Save command failed: {e}")
        await interaction.followup.send(f"❌ Save failed: {e}")


@bot.tree.command(name="recall", description="Search your Second Brain")
@app_commands.describe(
    query="What are you looking for?",
    limit="Max results (1-10, default 5)"
)
async def cmd_recall(
    interaction: discord.Interaction,
    query: str,
    limit: int = 5
):
    """Semantic search the Second Brain."""
    from domains.second_brain.commands import handle_recall

    await interaction.response.defer()

    limit = max(1, min(10, limit))  # Clamp to 1-10

    try:
        response = await handle_recall(query, limit=limit)
        await interaction.followup.send(response)
    except Exception as e:
        logger.error(f"Recall command failed: {e}")
        await interaction.followup.send(f"❌ Search failed: {e}")


@bot.tree.command(name="knowledge", description="Show Second Brain stats")
async def cmd_knowledge(interaction: discord.Interaction):
    """Show Second Brain stats and recent items."""
    from domains.second_brain.commands import handle_knowledge

    await interaction.response.defer()

    try:
        response = await handle_knowledge()
        await interaction.followup.send(response)
    except Exception as e:
        logger.error(f"Knowledge command failed: {e}")
        await interaction.followup.send(f"❌ Failed to load stats: {e}")


@bot.event
async def on_error(event, *args, **kwargs):
    """Handle errors."""
    logger.error(f"Bot error in {event}: {args}")


def main():
    """Entry point."""
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN not set")
        return

    logger.info("Starting Discord Assistant...")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()

"""Discord Personal Assistant - Main Bot.

A modular Discord bot with AI coaching/assistance via Claude API.
Routes messages to domain handlers based on channel.
"""

# Suppress RequestsDependencyWarning spam before any requests import
import warnings
warnings.filterwarnings("ignore", message="urllib3.*or chardet.*doesn't match")

import asyncio
import io
import os
import re
import subprocess
import sys
import time
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

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
from domains.peterbot.config import PETERBOT_CHANNEL_IDS
from domains.peterbot.router_v2 import handle_message as handle_peterbot
from domains.peterbot.router_v2 import on_startup as peterbot_startup

from domains.peterbot import CHANNEL_ID as PETERBOT_CHANNEL
from domains.peterbot.memory import is_buffer_empty, populate_buffer_from_history

# Import Response Processing Pipeline (Stage 1-5 processing)
from domains.peterbot.response.pipeline import process as process_response

# Import Peterbot scheduler (Phase 7)
from domains.peterbot.scheduler import PeterbotScheduler
from domains.peterbot.data_fetchers import SKILL_DATA_FETCHERS

# Import reminders handler (one-off reminders)
from domains.peterbot.reminders.handler import (
    reload_reminders_on_startup,
    start_reminder_polling
)

# Import Second Brain passive capture
from domains.second_brain.passive import (
    should_capture_message,
    process_passive_message,
)

# Import standalone jobs (legacy - kept for manual triggers during migration)
from jobs import (
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
scheduler = AsyncIOScheduler(job_defaults={"misfire_grace_time": 60})

# Message deduplication: track recently processed message IDs
_processed_messages: dict[int, float] = {}  # message_id -> timestamp
MESSAGE_DEDUP_SECONDS = 5

# Peterbot scheduler (Phase 7 - skill-based jobs)
# Set to True to use new SCHEDULE.md-based scheduler, False for legacy jobs
USE_PETERBOT_SCHEDULER = True  # Phase 7b complete - skills created
peterbot_scheduler = None  # Initialized in on_ready
_ready_initialized = False  # Guard against multiple on_ready calls


def _launch_channel_sessions():
    """Launch persistent Claude Code channel sessions in WSL tmux.

    Called from on_ready. Each session auto-restarts on crash (restart loop
    in launch.sh). If a session is already running, tmux has-session returns
    0 and we skip it.
    """
    import subprocess

    BASE = "/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger"
    sessions = [
        ("peter-channel", f"{BASE}/peter-channel/launch.sh"),
        ("whatsapp-channel", f"{BASE}/whatsapp-channel/launch.sh"),
        ("jobs-channel", f"{BASE}/jobs-channel/launch.sh"),
    ]

    for name, script in sessions:
        try:
            # Check if session already exists
            check = subprocess.run(
                ["wsl", "bash", "-c", f"tmux has-session -t {name} 2>/dev/null"],
                capture_output=True, timeout=5,
            )
            if check.returncode == 0:
                logger.info(f"Channel session '{name}' already running, skipping")
                continue

            # Launch new tmux session with the channel's launch script
            subprocess.Popen(
                ["wsl", "bash", "-c",
                 f'tmux new-session -d -s {name} -c $HOME/peterbot "bash \\"{script}\\""'],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            logger.info(f"Launched channel session '{name}'")
        except Exception as e:
            logger.warning(f"Failed to launch channel session '{name}': {e}")


def _create_logged_task(coro, name: str = None):
    """Create an asyncio task with exception logging.

    Replaces bare asyncio.create_task() to ensure background task exceptions
    are logged instead of silently swallowed.
    """
    task = asyncio.create_task(coro, name=name)

    def _on_done(t):
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.error(f"Background task {name or 'unnamed'} failed: {exc}", exc_info=exc)

    task.add_done_callback(_on_done)
    return task


def _tracked_job(job_id: str, func):
    """Wrap a legacy async job function with execution tracking and failure alerting.

    Records start/complete in job_history.db (same as skill-based jobs)
    and posts to #alerts webhook on failure.
    """
    from functools import wraps

    @wraps(func)
    async def wrapper(*args, **kwargs):
        from peter_dashboard.api.jobs import record_job_start, record_job_complete
        execution_id = None
        try:
            execution_id = record_job_start(job_id)
        except Exception as e:
            logger.warning(f"Failed to record job start for {job_id}: {e}")

        success = False
        result = None
        output_str = ""
        error_str = ""
        try:
            result = await func(*args, **kwargs)
            # Legacy jobs return dicts like {"Octopus Sync": (True, "output")}
            if isinstance(result, dict):
                all_ok = all(v[0] for v in result.values() if isinstance(v, tuple))
                success = all_ok
                parts = []
                for name, val in result.items():
                    if isinstance(val, tuple):
                        ok, out = val
                        parts.append(f"{name}: {'OK' if ok else 'FAILED'}")
                        if not ok:
                            error_str += f"{name}: {out[-200:]}\n"
                    else:
                        parts.append(f"{name}: {val}")
                output_str = "; ".join(parts)
            elif isinstance(result, list):
                # List of result objects (e.g. incremental_seed adapters)
                # Check for items_failed attribute on any result
                failed_count = sum(
                    getattr(r, 'items_failed', 0) for r in result
                    if hasattr(r, 'items_failed')
                )
                success = True  # Partial failures don't fail the job
                output_str = f"{len(result)} adapters, {failed_count} items failed"
                if failed_count > 0:
                    output_str += " (partial)"
            else:
                success = True
                output_str = str(result)[:500] if result else "completed"
        except Exception as e:
            success = False
            error_str = str(e)[:500]
            logger.error(f"Tracked job {job_id} exception: {e}")

        try:
            record_job_complete(
                job_id, success=success,
                output=output_str[:500] if output_str else None,
                error=error_str[:500] if error_str else None,
                execution_id=execution_id,
            )
        except Exception as e:
            logger.warning(f"Failed to record job complete for {job_id}: {e}")

        return result

    return wrapper


@bot.event
async def on_ready():
    """Called when bot is connected and ready.

    Note: Discord.py may call this multiple times on gateway reconnects.
    The _ready_initialized guard prevents duplicate scheduler/domain setup.
    """
    global _ready_initialized
    logger.info(f"Logged in as {bot.user}")

    if _ready_initialized:
        logger.info("on_ready called again (reconnect) - skipping initialization")
        return

    _ready_initialized = True

    # Sync slash commands with Discord
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash commands")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

    # Launch channel sessions in WSL (if not already running)
    _launch_channel_sessions()

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
        # Watch for API-triggered reloads (Hadley API writes trigger file)
        peterbot_scheduler.start_reload_watcher()
        peterbot_scheduler.start_nag_checker()
    else:
        # Legacy: Register standalone jobs (remove after Phase 7b migration)
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

    # Legacy jobs — wrap with execution tracking before registration
    # This records start/complete in job_history.db and alerts #alerts on failure
    import jobs.incremental_seed as _seed_mod
    import jobs.school_sync as _school_mod
    import jobs.energy_sync as _energy_mod
    import jobs.whatsapp_sync as _wa_mod

    _seed_mod.incremental_seed_import = _tracked_job(
        "incremental_seed", _seed_mod.incremental_seed_import)
    _school_mod.school_daily_sync = _tracked_job(
        "school_daily_sync", _school_mod.school_daily_sync)
    _school_mod.school_weekly_sync = _tracked_job(
        "school_weekly_sync", _school_mod.school_weekly_sync)
    _energy_mod.energy_daily_sync = _tracked_job(
        "energy_daily_sync", _energy_mod.energy_daily_sync)
    _energy_mod.energy_weekly_digest = _tracked_job(
        "energy_weekly_digest", _energy_mod.energy_weekly_digest)
    _energy_mod.energy_monthly_billing = _tracked_job(
        "energy_monthly_billing", _energy_mod.energy_monthly_billing)
    _wa_mod.whatsapp_web_scrape = _tracked_job(
        "whatsapp_web_scrape", _wa_mod.whatsapp_web_scrape)
    _wa_mod.whatsapp_export_scan = _tracked_job(
        "whatsapp_export_scan", _wa_mod.whatsapp_export_scan)

    # Incremental seed import — daily at 1am UK, loads calendar/email/GitHub/Garmin
    _seed_mod.register_incremental_seed(scheduler, bot=bot)
    logger.info("Incremental seed job registered (daily at 1:00 AM UK)")

    # School integration — daily emails at 7am, weekly scrape+sync Saturday 6am
    _school_mod.register_school_sync(scheduler, bot=bot)
    logger.info("School sync jobs registered (daily 7:00 AM + weekly Saturday 6:00 AM UK)")

    # Energy — daily consumption sync at 10am, weekly digest Sunday 9am, monthly billing 1st 10:30am
    _energy_mod.register_energy_sync(scheduler, bot=bot)
    logger.info("Energy sync jobs registered (daily 10:00 AM + weekly Sunday 9:00 AM + monthly 1st 10:30 AM UK)")

    # WhatsApp — daily export scan at 10am, weekly reminder Sunday 9am
    _wa_mod.register_whatsapp_sync(scheduler, bot=bot)
    logger.info("WhatsApp sync jobs registered (daily 10:00 AM + weekly Sunday 9:00 AM UK)")

    # Japan trip — proactive WhatsApp alerts every 15 min (active Apr 3-19 only)
    from domains.peterbot.japan_alerts import check_and_send_alerts as _japan_alerts
    scheduler.add_job(
        _japan_alerts,
        'interval', minutes=15,
        id='japan_trip_alerts',
        name='Japan Trip WhatsApp Alerts',
        replace_existing=True,
    )
    logger.info("Japan trip alerts registered (every 15 min, active during trip only)")

    # WhatsApp incoming messages — internal HTTP server for HadleyAPI to forward to
    from aiohttp import web as aio_web
    from integrations.whatsapp import send_text, send_audio

    WHATSAPP_VIRTUAL_CHANNEL_ID = 9999999999

    async def _whatsapp_handler(request):
        """Handle forwarded WhatsApp messages from HadleyAPI."""
        try:
            data = await request.json()
            sender_name = data.get("sender_name", "Unknown")
            sender_number = data.get("sender_number", "")
            reply_to = data.get("reply_to", sender_number)
            is_group = data.get("is_group", False)
            is_voice = data.get("is_voice", False)
            skip_whatsapp_reply = data.get("skip_whatsapp_reply", False)
            text = data.get("text", "")

            if not text.strip() or not sender_number:
                return aio_web.json_response({"status": "ignored"})

            # Check for nag acknowledgement before routing to Peter
            ack_patterns = {"done", "finished", "completed", "stop", "yes done", "stop nagging", "all done"}
            if text.strip().lower() in ack_patterns and not is_group:
                try:
                    import httpx as _httpx
                    # Map sender number to delivery target name
                    _wa_contacts = {"447855620978": "chris", "447856182831": "abby"}
                    _target_name = _wa_contacts.get(sender_number, sender_number)
                    async with _httpx.AsyncClient(timeout=5.0) as _client:
                        _nag_resp = await _client.get(
                            f"http://127.0.0.1:8100/reminders/active-nags?delivery=whatsapp:{_target_name}"
                        )
                        if _nag_resp.status_code == 200:
                            _active_nags = _nag_resp.json()
                            if _active_nags:
                                # Acknowledge the first active nag
                                _nag_id = _active_nags[0]["id"]
                                await _client.post(f"http://127.0.0.1:8100/reminders/{_nag_id}/acknowledge")
                                _task_name = _active_nags[0].get("task", "your task")
                                await send_text(reply_to, f"Nice one, ticked off for today ✅\n*{_task_name}* — no more reminders.")
                                logger.info(f"Nag {_nag_id} acknowledged by {sender_name} via WhatsApp")
                                return aio_web.json_response({"status": "ok", "replied": True})
                except Exception as _e:
                    logger.debug(f"Nag ack check failed: {_e}")

            source = "group" if is_group else "DM"
            voice_tag = " voice" if is_voice else ""
            logger.info(f"WhatsApp ({source}{voice_tag}) → Peter: [{sender_name}] {text[:100]}")
            tagged_message = f"[WhatsApp {source}{voice_tag} from {sender_name}] {text}"

            response = await handle_peterbot(
                message=tagged_message,
                user_id=int(sender_number),
                channel_id=WHATSAPP_VIRTUAL_CHANNEL_ID,
            )

            reply_text = response.strip() if response else ""
            if not reply_text or reply_text == "NO_REPLY":
                return aio_web.json_response({"status": "ok", "replied": False, "reply": ""})

            # For /voice/converse requests, return the reply text without sending on WhatsApp
            if skip_whatsapp_reply:
                return aio_web.json_response({"status": "ok", "replied": True, "reply": reply_text})

            # Always send text reply
            await send_text(reply_to, reply_text)
            logger.info(f"Peter → WhatsApp [{sender_name}, {source}]: {reply_text[:100]}")

            # If the incoming message was a voice note, also reply with audio
            if is_voice:
                try:
                    import base64 as b64
                    from hadley_api.voice_engine import synthesise
                    wav_bytes = await synthesise(reply_text)
                    audio_b64 = b64.b64encode(wav_bytes).decode()
                    await send_audio(reply_to, audio_b64)
                    logger.info(f"Peter → WhatsApp voice [{sender_name}]: {len(wav_bytes)} bytes")
                except Exception as e:
                    logger.error(f"Voice reply failed (text still sent): {e}")

            return aio_web.json_response({"status": "ok", "replied": True, "reply": reply_text})
        except Exception as e:
            logger.error(f"WhatsApp → Peter routing failed: {e}")
            return aio_web.json_response({"error": str(e)}, status=500)

    async def _start_whatsapp_server():
        # Pre-check port availability before attempting to bind
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", 8101))
            sock.close()
        except OSError:
            logger.warning("WhatsApp port 8101 already in use — skipping server start")
            sock.close()
            return

        app = aio_web.Application()
        app.router.add_post("/whatsapp/message", _whatsapp_handler)
        runner = aio_web.AppRunner(app)
        await runner.setup()
        site = aio_web.TCPSite(runner, "127.0.0.1", 8101)
        await site.start()
        logger.info("WhatsApp internal server listening on 127.0.0.1:8101")

    _create_logged_task(_start_whatsapp_server())
    logger.info("WhatsApp incoming message routing registered (port 8101)")

    # Reprocess pending passive captures — every 6 hours
    async def reprocess_pending():
        """Upgrade passive captures to full items with embeddings."""
        try:
            from domains.second_brain.pipeline import reprocess_pending_items
            count = await reprocess_pending_items(limit=20)
            logger.info(f"Reprocessed {count} pending items")
        except Exception as e:
            logger.error(f"Reprocess pending failed: {e}")

    reprocess_pending = _tracked_job("reprocess_pending", reprocess_pending)
    scheduler.add_job(
        reprocess_pending,
        IntervalTrigger(hours=6),
        id="__reprocess_pending",
        max_instances=1,
        replace_existing=True,
    )
    logger.info("Reprocess pending items registered (every 6h)")

    # Second Brain health check — daily at 7:05am UK (staggered from 07:00 to avoid collision)
    ALERTS_CHANNEL_ID = 1466019126194606286

    async def post_to_discord(channel_id: int, text: str):
        """Post a text message via peter-channel HTTP, fallback to bot client."""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://127.0.0.1:8104/post",
                    json={"channel_id": str(channel_id), "chunks": [text]},
                    timeout=15,
                )
                if resp.status_code == 200:
                    return
                logger.warning(f"peter-channel returned {resp.status_code}, falling back to bot client")
        except Exception as e:
            logger.warning(f"peter-channel HTTP failed ({e}), falling back to bot client")
        # Fallback: use bot's discord.py client
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        if channel:
            await channel.send(text)

    async def daily_health_check():
        """Post daily health status to #alerts."""
        try:
            from domains.second_brain.health import get_health_report, format_daily_discord
            report = await get_health_report()
            message = format_daily_discord(report)
            await post_to_discord(ALERTS_CHANNEL_ID, message)
            logger.info("Posted daily health check to #alerts")
        except Exception as e:
            logger.error(f"Daily health check failed: {e}")

    daily_health_check = _tracked_job("daily_health_check", daily_health_check)
    scheduler.add_job(
        daily_health_check,
        'cron',
        hour=7,
        minute=5,
        timezone="Europe/London",
        id="__daily_health_check",
        max_instances=1,
        coalesce=True,
    )
    logger.info("Daily health check registered (7:05 AM UK)")

    # Second Brain weekly digest — Sunday 9:04am UK (staggered to avoid Sunday collision)
    async def weekly_health_digest():
        """Post weekly health + content digest to #alerts."""
        try:
            from domains.second_brain.health import get_health_report, format_weekly_discord
            from domains.second_brain.digest import generate_weekly_digest
            report = await get_health_report()
            digest_data = await generate_weekly_digest()
            message = format_weekly_discord(report, digest_data)
            await post_to_discord(ALERTS_CHANNEL_ID, message)
            logger.info("Posted weekly health digest to #alerts")
        except Exception as e:
            logger.error(f"Weekly health digest failed: {e}")

    weekly_health_digest = _tracked_job("weekly_health_digest", weekly_health_digest)
    scheduler.add_job(
        weekly_health_digest,
        'cron',
        day_of_week='sun',
        hour=9,
        minute=4,
        timezone="Europe/London",
        id="__weekly_health_digest",
        max_instances=1,
        coalesce=True,
    )
    logger.info("Weekly health digest registered (Sunday 9:04 AM UK)")

    logger.info(f"Bot ready - {len(registry.all_domains())} domains registered")

    # Claude Code domain startup - restore active session
    startup_msg = claude_code_startup()
    if startup_msg:
        await post_to_discord(CLAUDE_CODE_CHANNEL, startup_msg)

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
            # Skip messages with no content and no attachments
            if not msg.content and not msg.attachments:
                continue

            role = "assistant" if msg.author.bot else "user"
            content = msg.content or ""

            # Append attachment info for user messages
            if not msg.author.bot and msg.attachments:
                att_lines = []
                for att in msg.attachments:
                    is_image = att.content_type and att.content_type.startswith("image/")
                    label = "Image" if is_image else "File"
                    att_lines.append(f"[{label}: {att.filename}]({att.url})")
                if att_lines:
                    content = (content + "\n" if content else "") + "\n".join(att_lines)

            if not content:
                continue

            messages.append({
                "role": role,
                "content": content
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


async def _passive_capture_check(message_content: str, channel_name: str):
    """Background task for passive Second Brain capture.

    Detects URLs and ideas in messages and captures them passively.
    Runs async to not delay responses.
    """
    try:
        # Quick pre-filter
        if not should_capture_message(message_content):
            return

        # Process for captures
        captured_ids = await process_passive_message(
            message_content,
            channel_name=channel_name
        )

        if captured_ids:
            logger.info(f"Passive captures: {len(captured_ids)} items from #{channel_name}")

    except Exception as e:
        # Non-critical - just log and continue
        logger.debug(f"Passive capture check failed: {e}")


@bot.event
async def on_message(message):
    """Handle incoming messages."""
    # Ignore bot messages (but allow "Chris (Voice)" webhook messages through)
    if message.author.bot:
        if not (message.webhook_id and message.author.display_name == "Chris (Voice)"):
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
    # When PETERBOT_USE_CHANNEL=1, Discord messages are handled by the
    # channel MCP server (Peter H bot) — skip router_v2 processing here.
    _PETERBOT_USE_CHANNEL = os.environ.get("PETERBOT_USE_CHANNEL", "0") == "1"
    if message.channel.id in PETERBOT_CHANNEL_IDS and _PETERBOT_USE_CHANNEL:
        return  # Peter H handles all chat — no fallback to router_v2
    if message.channel.id in PETERBOT_CHANNEL_IDS:
        async with message.channel.typing():
            # Check if buffer needs populating from Discord history (e.g., after restart)
            if is_buffer_empty(message.channel.id):
                logger.info(f"Buffer empty for channel {message.channel.id}, fetching Discord history")
                history_messages = await fetch_peterbot_history(message.channel)
                if history_messages:
                    populate_buffer_from_history(message.channel.id, history_messages)

            # Live status embed that updates in place with tool activity
            status_msg = None
            status_lines = []
            status_start = time.monotonic()
            GOLD = 0xFFD700

            def _format_elapsed(seconds: float) -> str:
                m, s = divmod(int(seconds), 60)
                return f"{m}m {s:02d}s" if m else f"{s}s"

            def _build_status_embed(turn: int, elapsed: float, finished: bool = False) -> discord.Embed:
                if finished:
                    title = f"Completed · {_format_elapsed(elapsed)} · {turn} turns"
                    colour = 0x2ECC71  # green
                else:
                    title = f"⏱️ {_format_elapsed(elapsed)} · Turn {turn}"
                    colour = GOLD

                embed = discord.Embed(title=title, colour=colour)

                # Build activity log inside a code block for contained "code window" look
                visible = status_lines[-15:]
                if len(status_lines) > 15:
                    visible = [f"... {len(status_lines) - 15} earlier steps"] + visible

                if visible:
                    code_body = "\n".join(visible)
                    embed.description = f"```\n{code_body}\n```"

                return embed

            async def post_interim(info):
                """Post/update live status embed with tool activity."""
                nonlocal status_msg

                # Handle string messages (credit exhaustion, kimi fallback, etc.)
                if isinstance(info, str):
                    status_lines.append(f"!! {info}" if not info.startswith("⚠️") else info)
                elif isinstance(info, dict):
                    tool_name = info.get("tool_name", "")
                    context = info.get("context", "")
                    # Short display name for the tool (no emojis — inside code block)
                    short_name = tool_name.split("__")[-1] if "__" in tool_name else tool_name
                    line = short_name
                    if context:
                        line += f"  {context}"
                    status_lines.append(line)

                turn = info.get("turn", 0) if isinstance(info, dict) else 0
                elapsed = info.get("elapsed_seconds", 0) if isinstance(info, dict) else (time.monotonic() - status_start)
                embed = _build_status_embed(max(turn, 1), elapsed)

                try:
                    if status_msg is None:
                        status_msg = await message.channel.send(embed=embed)
                    else:
                        await status_msg.edit(embed=embed)
                except Exception:
                    pass  # Don't let status updates break the main flow

            # Define busy callback for when Peter is working on another task
            async def post_busy(text: str):
                """Post busy notification when Peter is handling another request."""
                await message.channel.send(text)

            # Extract attachment URLs (images, files)
            attachment_urls = []
            for att in message.attachments:
                attachment_urls.append({
                    "url": att.url,
                    "filename": att.filename,
                    "content_type": att.content_type or "",
                    "size": att.size,
                })

            # Normal peterbot routing to Claude Code (with interim updates)
            raw_response = await handle_peterbot(
                message.content,
                message.author.id,
                message.channel.id,
                interim_callback=post_interim,
                busy_callback=post_busy,
                attachment_urls=attachment_urls if attachment_urls else None,
                message_id=message.id,
            )

            # Update status embed to show completion
            if status_msg is not None:
                try:
                    elapsed = time.monotonic() - status_start
                    turn = len(status_lines)
                    embed = _build_status_embed(max(turn, 1), elapsed, finished=True)
                    await status_msg.edit(embed=embed)
                except Exception:
                    pass

            # Process through Response Pipeline (sanitise → classify → format → chunk)
            # Router v2 output is clean JSON — skip sanitiser
            processed = process_response(
                raw_response,
                {'user_prompt': message.content},
                pre_sanitised=True,
            )

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

            # Detect file paths in response and attach them
            # Matches WSL paths like /tmp/..., /home/..., or Windows paths
            file_paths = re.findall(
                r'(?:^|[\s`(])(/(?:tmp|home|mnt)[^\s`),\]]+\.(?:jpg|jpeg|png|gif|webp|pdf|csv|txt|json|zip))',
                raw_response or "",
                re.IGNORECASE,
            )
            # Deduplicate while preserving order
            seen = set()
            unique_paths = []
            for fp in file_paths:
                if fp not in seen:
                    seen.add(fp)
                    unique_paths.append(fp)

            if unique_paths:
                discord_files = []
                for wsl_path in unique_paths[:10]:  # Cap at 10 files
                    try:
                        result = subprocess.run(
                            ["wsl", "cat", wsl_path],
                            capture_output=True, timeout=10,
                        )
                        if result.returncode == 0 and result.stdout:
                            filename = wsl_path.rsplit("/", 1)[-1]
                            discord_files.append(
                                discord.File(io.BytesIO(result.stdout), filename=filename)
                            )
                    except Exception as e:
                        logger.warning(f"Failed to read WSL file {wsl_path}: {e}")

                # Send files in batches of 10 (Discord limit per message)
                if discord_files:
                    try:
                        await message.channel.send(files=discord_files)
                    except Exception as e:
                        logger.warning(f"Failed to send file attachments: {e}")

            # Add reactions if specified (for alerts)
            if processed.reactions:
                for reaction in processed.reactions:
                    try:
                        await message.add_reaction(reaction)
                    except discord.HTTPException:
                        pass  # Reaction failed, continue

            logger.debug(f"Response processed: type={processed.response_type.value}, "
                        f"chunks={len(processed.chunks)}, raw={processed.raw_length}, final={processed.final_length}")

            # Passive capture: fire-and-forget async task for URL/idea detection
            # This runs in background after response is sent
            _create_logged_task(_passive_capture_check(
                message.content,
                message.channel.name
            ), name="passive_capture")

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

    # Memory system: Second Brain (Supabase)
    lines.append("**Memory:** Second Brain (Supabase + pgvector)")

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
    import traceback
    logger.error(f"Bot error in {event}: {args}")
    logger.error(traceback.format_exc())


def _kill_orphaned_bots():
    """Kill any orphaned bot.py processes from previous restarts.

    NSSM restarts can leave zombie bot.py processes (especially via PythonManager chains).
    Each orphan runs its own scheduler, causing duplicate job execution.

    Strategy:
    1. Read PID from bot.lock (most reliable — we control the file)
    2. Fall back to wmic scan (handles cases where lock file is stale/missing)
    3. Wait briefly after killing to ensure process is dead before we continue
    """
    import subprocess
    import signal
    from pathlib import Path

    my_pid = os.getpid()
    killed = 0
    lock_path = Path(__file__).parent / "bot.lock"

    # --- Phase 1: Kill process from lock file (most reliable) ---
    if lock_path.exists():
        try:
            old_pid = int(lock_path.read_text().strip())
            if old_pid != my_pid:
                try:
                    os.kill(old_pid, signal.SIGTERM)
                    killed += 1
                    logger.warning(f"Killed previous bot.py from lock file (PID {old_pid})")
                except (ProcessLookupError, PermissionError):
                    pass  # Process already dead or inaccessible
        except (ValueError, OSError):
            pass  # Corrupt lock file

    # --- Phase 2: Stop DiscordBot NSSM service if running (it spawns a hidden bot.py) ---
    # Skip when WE are the service to avoid self-kill deadlock.
    # NSSM chain: nssm.exe → python.exe (PythonManager) → python.exe (bot.py)
    # So we walk up the ancestor chain (up to 5 levels) looking for nssm.exe.
    is_nssm = False
    try:
        current_pid = os.getppid()
        for _ in range(5):
            wmic_out = subprocess.run(
                ["wmic", "process", "where", f"processid={current_pid}",
                 "get", "name,parentprocessid", "/format:csv"],
                capture_output=True, text=True, timeout=5
            )
            if "nssm" in wmic_out.stdout.lower():
                is_nssm = True
                break
            # Extract parent PID from CSV output to continue walking up
            for line in wmic_out.stdout.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("Node"):
                    parts = line.split(",")
                    # CSV format: Node,Name,ParentProcessId
                    if len(parts) >= 3 and parts[-1].strip().isdigit():
                        next_pid = int(parts[-1].strip())
                        if next_pid == current_pid or next_pid == 0:
                            break  # Reached root or loop
                        current_pid = next_pid
                        break
            else:
                break  # No valid parent found
    except Exception:
        pass

    if not is_nssm:
        try:
            svc_result = subprocess.run(
                ["sc", "queryex", "DiscordBot"],
                capture_output=True, text=True, timeout=10
            )
            if "RUNNING" in svc_result.stdout:
                logger.error(
                    "DiscordBot NSSM service is already running. "
                    "Refusing to start a duplicate — exiting. "
                    "Use 'nssm restart DiscordBot' to restart the service instead."
                )
                sys.exit(1)
        except Exception as e:
            logger.debug(f"Service check skipped: {e}")
    else:
        logger.debug("Skipping Phase 2 — running as NSSM service")

    # --- Phase 3: wmic scan for any remaining python+bot.py processes ---
    try:
        # Use encoding="utf-16-le" — wmic outputs UTF-16 on Windows
        result = subprocess.run(
            ["wmic", "process", "where",
             "name like 'python%' and commandline like '%bot.py%'",
             "get", "processid", "/format:csv"],
            capture_output=True, timeout=10
        )
        # Decode as UTF-16-LE, falling back to UTF-8 then latin-1
        stdout = ""
        for enc in ("utf-16-le", "utf-8", "latin-1"):
            try:
                stdout = result.stdout.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue

        for line in stdout.strip().split("\n"):
            line = line.strip().strip("\x00")  # Strip null bytes from UTF-16
            if not line:
                continue
            parts = line.split(",")
            pid_str = parts[-1].strip()
            if pid_str.isdigit():
                pid = int(pid_str)
                if pid != my_pid:
                    try:
                        os.kill(pid, signal.SIGTERM)
                        killed += 1
                        logger.warning(f"Killed orphaned bot.py process PID {pid}")
                    except (ProcessLookupError, PermissionError):
                        pass
    except Exception as e:
        logger.info(f"wmic orphan scan skipped: {e}")

    # --- Phase 4: Wait for killed processes to actually die ---
    if killed:
        import time
        time.sleep(2)  # Give OS time to terminate processes
        logger.info(f"Cleaned up {killed} orphaned bot process(es)")

    # Update lockfile with our PID
    lock_path.write_text(str(my_pid))


def main():
    """Entry point."""
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN not set")
        return

    _kill_orphaned_bots()
    logger.info("Starting Discord Assistant...")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()

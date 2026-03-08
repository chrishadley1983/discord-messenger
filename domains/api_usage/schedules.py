"""API Usage domain scheduled tasks."""

from datetime import datetime

from domains.base import ScheduledTask
from .services import get_anthropic_usage, get_openai_usage, get_google_usage, get_google_daily_breakdown, get_vision_effectiveness
from .config import CHANNEL_ID

from logger import logger


async def weekly_summary(bot, domain):
    """Post weekly API usage summary."""
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        logger.error(f"Could not find api-usage channel {CHANNEL_ID}")
        return

    try:
        anthropic_data = await get_anthropic_usage(days=7)
        openai_data = await get_openai_usage(days=7)
        google_data = await get_google_usage(days=7)

        today = datetime.now()
        date_str = today.strftime("%d %b %Y")

        lines = [
            f"📊 **Weekly API Usage Summary** - {date_str}",
            ""
        ]

        # Anthropic
        if anthropic_data.get("total_cost") is not None:
            lines.append(f"🔮 **Claude (Anthropic):** ${anthropic_data['total_cost']:.2f}")
        else:
            lines.append(f"🔮 **Claude (Anthropic):** {anthropic_data.get('note', 'unavailable')}")

        # OpenAI
        if openai_data.get("total_cost") is not None:
            lines.append(f"🤖 **OpenAI:** ${openai_data['total_cost']:.2f}")
        else:
            lines.append(f"🤖 **OpenAI:** {openai_data.get('note', 'unavailable')}")

        # Google (Gemini)
        if google_data.get("total_cost") is not None:
            req_str = f" ({google_data.get('total_requests', '?')} reqs)" if google_data.get("total_requests") else ""
            # Check if all models are free tier
            breakdown = google_data.get("breakdown", {})
            all_free = all(info.get("free_tier", False) for info in breakdown.values()) if breakdown else False
            if all_free:
                lines.append(f"🔷 **Google (Gemini):** $0.00 (free tier){req_str}")
            else:
                lines.append(f"🔷 **Google (Gemini):** ~${google_data['total_cost']:.2f}{req_str}")
            for model, info in breakdown.items():
                if info.get("requests", 0) > 0:
                    free_label = " ✓free" if info.get("free_tier") else ""
                    lines.append(f"   ↳ {model}: {info['requests']} reqs (~${info['estimated_cost']:.2f} equiv{free_label})")
        else:
            note = google_data.get("note", google_data.get("error", "unavailable"))
            lines.append(f"🔷 **Google (Gemini):** {note}")

        # Total (exclude free-tier Gemini from billable total)
        total = 0
        if anthropic_data.get("total_cost"):
            total += anthropic_data["total_cost"]
        if openai_data.get("total_cost"):
            total += openai_data["total_cost"]
        if google_data.get("total_cost") and not all_free:
            total += google_data["total_cost"]

        if total > 0:
            lines.append("")
            lines.append(f"💰 **Total (billable):** ${total:.2f}")

        message = "\n".join(lines)
        await channel.send(message)
        logger.info("Posted weekly API usage summary")

    except Exception as e:
        logger.error(f"Failed to post weekly summary: {e}")


async def daily_google_spend(bot, domain):
    """Post daily Google AI spend report — short-term focused monitoring."""
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        logger.error(f"Could not find api-usage channel {CHANNEL_ID}")
        return

    try:
        daily_data = await get_google_daily_breakdown(days=7)

        if daily_data.get("error"):
            await channel.send(f"⚠️ Google spend check failed: {daily_data['error']}")
            return

        days = daily_data.get("days", [])
        if not days:
            await channel.send("🔷 **Google AI Daily Spend:** No usage data found for the last 7 days")
            return

        # Check if all usage is free tier
        all_free = all(
            m.get("free_tier", False)
            for day in days for m in day.get("models", [])
        )
        cost_header = "Equiv. Cost" if all_free else "Est. Cost"

        lines = [
            "🔷 **Google AI (Gemini) — Daily Spend Report**" + (" _(free tier)_" if all_free else ""),
            "```",
            f"{'Date':<12} {'Requests':>8} {cost_header:>12}",
            f"{'─'*12} {'─'*8} {'─'*12}",
        ]

        total_cost = 0
        total_reqs = 0
        for day in days:
            date_str = day["date"]
            reqs = day["total_requests"]
            cost = day["estimated_cost"]
            total_cost += cost
            total_reqs += reqs
            lines.append(f"{date_str:<12} {reqs:>8} {'$' + f'{cost:.2f}':>12}")

        lines.append(f"{'─'*12} {'─'*8} {'─'*12}")
        cost_label = f"$0.00 (free)" if all_free else f"${total_cost:.2f}"
        lines.append(f"{'TOTAL':<12} {total_reqs:>8} {cost_label:>12}")
        lines.append("```")

        # Show model breakdown for the most recent day
        if days:
            latest = days[-1]
            if latest.get("models"):
                lines.append(f"**Today's models:**")
                for m in latest["models"]:
                    free_label = " ✓free" if m.get("free_tier") else ""
                    lines.append(f"  • {m['model']}: {m['requests']} reqs (~${m['estimated_cost']:.2f} equiv{free_label})")

        message = "\n".join(lines)
        await channel.send(message)

        # Vision effectiveness report (last 24h)
        eff = await get_vision_effectiveness(days=1)
        if eff.get("total", 0) > 0:
            eff_lines = [
                "",
                "**Vinted Sniper Vision Effectiveness (24h)**",
                "```",
                f"Total calls:  {eff['total']}",
                f"Identified:   {eff['found']} ({eff['hit_rate_pct']}%)",
                f"Missed:       {eff['missed']} ({100 - eff['hit_rate_pct']:.1f}%)",
                f"Avg response: {eff.get('avg_response_ms', '?')}ms",
                "```",
            ]

            sets = eff.get("sets_identified", [])
            if sets:
                eff_lines.append(f"Sets found: {', '.join(sets)}")

            await channel.send("\n".join(eff_lines))

        logger.info("Posted daily Google AI spend report")

    except Exception as e:
        logger.error(f"Failed to post daily Google spend: {e}")


SCHEDULES = [
    ScheduledTask(
        name="weekly_summary",
        handler=weekly_summary,
        hour=9,
        minute=0,
        day_of_week="mon",  # Weekly on Monday
        timezone="Europe/London"
    ),
    ScheduledTask(
        name="daily_google_spend",
        handler=daily_google_spend,
        hour=8,
        minute=0,
        timezone="Europe/London"
    ),
]

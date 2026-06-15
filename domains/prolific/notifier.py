"""Post a Discord embed for a newly-spotted Prolific study."""

from __future__ import annotations

import httpx

from logger import logger

from .config import DISCORD_WEBHOOK
from .fx import usd_pence_to_gbp_pence, usd_to_gbp_rate
from .scraper import Study


def _colour_for(hourly_pence_gbp: int | None) -> int:
    # Discord embed colour as 0xRRGGBB int, based on GBP hourly rate.
    if hourly_pence_gbp is None:
        return 0x9CA3AF  # grey
    if hourly_pence_gbp >= 1000:  # £10/hr+
        return 0x22C55E  # green
    if hourly_pence_gbp >= 700:   # £7/hr+
        return 0xF59E0B  # amber
    return 0xEF4444               # red


def _gbp(pence: int | None) -> str:
    return f"£{pence / 100:.2f}" if pence is not None else "?"


def _to_gbp(pence_native: int | None, currency: str) -> int | None:
    """Convert a native-currency pence value to GBP pence."""
    if pence_native is None:
        return None
    if currency == "GBP":
        return pence_native
    if currency == "USD":
        return usd_pence_to_gbp_pence(pence_native)
    # Unknown currency — assume GBP rather than block the alert
    logger.warning(f"Unknown Prolific currency '{currency}', treating as GBP")
    return pence_native


def build_embed(study: Study) -> dict:
    reward_gbp = _to_gbp(study.reward_pence, study.reward_currency)
    hourly_gbp = _to_gbp(study.hourly_rate_pence, study.reward_currency)

    fields = [
        {"name": "Pay",        "value": _gbp(reward_gbp),                                                    "inline": True},
        {"name": "Hourly",     "value": f"{_gbp(hourly_gbp)}/hr" if hourly_gbp is not None else "?",         "inline": True},
        {"name": "Duration",   "value": f"{study.duration_mins} mins" if study.duration_mins else "?",       "inline": True},
        {"name": "Places",     "value": str(study.places) if study.places is not None else "?",              "inline": True},
        {"name": "Researcher", "value": study.researcher or "?",                                             "inline": True},
    ]
    if study.tags:
        fields.append({"name": "Tags", "value": ", ".join(study.tags), "inline": False})

    # If the source currency wasn't GBP, surface the original numbers in the footer.
    if study.reward_currency != "GBP" and study.reward_pence is not None:
        sym = "$" if study.reward_currency == "USD" else study.reward_currency
        rate = usd_to_gbp_rate() if study.reward_currency == "USD" else None
        rate_note = f" • 1 USD = £{rate:.4f}" if rate is not None else ""
        footer_text = (
            f"Prolific • {study.study_id[:8]} • Originally "
            f"{sym}{study.reward_pence/100:.2f} / "
            f"{sym}{(study.hourly_rate_pence or 0)/100:.2f}/hr{rate_note}"
        )
    else:
        footer_text = f"Prolific • {study.study_id[:8]}"

    return {
        "title": study.title[:256],
        "url": study.url,
        "color": _colour_for(hourly_gbp),
        "fields": fields,
        "footer": {"text": footer_text},
    }


async def notify_new_study(study: Study) -> None:
    if not DISCORD_WEBHOOK:
        logger.warning(f"No DISCORD_WEBHOOK_PROLIFIC set; skipping notify for {study.study_id}")
        return

    payload = {
        "username": "Prolific Sniper",
        "embeds": [build_embed(study)],
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(DISCORD_WEBHOOK, json=payload)
            r.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"Prolific webhook post failed for {study.study_id}: {e}")


async def notify_session_expired() -> None:
    """Ping Discord that the Prolific session has expired and needs re-login."""
    if not DISCORD_WEBHOOK:
        logger.warning("No DISCORD_WEBHOOK_PROLIFIC set; skipping session-expired alert")
        return

    payload = {
        "username": "Prolific Sniper",
        "embeds": [{
            "title": "Prolific session expired",
            "description": (
                "The headless Chrome-Prolific session is hitting `/login` — "
                "no studies will be detected until you re-authenticate.\n\n"
                "Run on the bot host:\n"
                "```powershell\n"
                ".\\_prolific-relogin.ps1\n"
                "```"
            ),
            "color": 0xEF4444,  # red
            "footer": {"text": "Re-alerts every 3h until fixed"},
        }],
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(DISCORD_WEBHOOK, json=payload)
            r.raise_for_status()
    except httpx.HTTPError as e:
        logger.error(f"Prolific session-expired webhook post failed: {e}")

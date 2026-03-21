"""Japan Trip Proactive Alerts — WhatsApp notifications for upcoming events.

Runs every 15 min via APScheduler. Checks current JST time against today's
plan and sends timely WhatsApp alerts for bookings, cash warnings, pack
reminders, and confirmation nudges.

No AI involved — pure Python time logic. Cheap, fast, reliable.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Optional

from logger import logger

JAPAN_TZ = ZoneInfo("Asia/Tokyo")
TRIP_START = datetime(2026, 4, 3)
TRIP_END = datetime(2026, 4, 19)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://modjoikyuhqzouxvieua.supabase.co")
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1vZGpvaWt5dWhxem91eHZpZXVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjYxNDE3MjksImV4cCI6MjA4MTcxNzcyOX0.EWGr0LOwFKFw3krrzZQZP_Gcew13s1Z9H3LxB0-JmPA",
)

# Chris's WhatsApp number
CHRIS_WHATSAPP = "447855620978"
# Family group (optional — for shared alerts)
# FAMILY_GROUP = "your_group_jid@g.us"

DEDUP_FILE = Path(__file__).parent.parent.parent / "data" / "japan_alerts_sent.json"
SIM_DATE_FILE = Path(__file__).parent.parent.parent / "data" / "japan_sim_date.txt"
SIM_TIME_FILE = Path(__file__).parent.parent.parent / "data" / "japan_sim_time.txt"

# Accommodation details for pack/move alerts
STAY_BY_DAY = {
    1: "Kitashinjuku Apartment", 2: "Kitashinjuku Apartment", 3: "Kitashinjuku Apartment",
    4: "Dotonbori Apartment", 5: "Dotonbori Apartment", 6: "Dotonbori Apartment", 7: "Dotonbori Apartment",
    8: "Kyoto Machiya", 9: "Kyoto Machiya", 10: "Kyoto Machiya", 11: "Kyoto Machiya",
    12: "Nezu Apartment", 13: "Nezu Apartment", 14: "Nezu Apartment", 15: "Nezu Apartment", 16: "Nezu Apartment",
    17: "Departure",
}

CHECKOUT_TIMES = {
    "Kitashinjuku Apartment": "10:00",
    "Dotonbori Apartment": "10:00",
    "Kyoto Machiya": "11:00",
    "Nezu Apartment": "11:00",
}

# Food picks that need cash warnings
CASH_ONLY_KEYWORDS = ["cash only", "cash", "bring yen", "bring cash"]

# Confirmation action keywords
CONFIRM_KEYWORDS = ["pending", "call ", "dm @", "confirm"]


def _get_jst_now() -> datetime:
    """Get current JST time, with sim override support."""
    # Check sim date
    sim_date = ""
    if SIM_DATE_FILE.exists():
        sim_date = SIM_DATE_FILE.read_text().strip()

    # Check sim time
    sim_time = ""
    if SIM_TIME_FILE.exists():
        sim_time = SIM_TIME_FILE.read_text().strip()

    if sim_date:
        try:
            dt = datetime.strptime(sim_date, "%Y-%m-%d")
            if sim_time:
                parts = sim_time.split(":")
                dt = dt.replace(hour=int(parts[0]), minute=int(parts[1]))
            else:
                # Use actual UK time mapped to JST for realistic testing
                now_uk = datetime.now()
                dt = dt.replace(hour=now_uk.hour, minute=now_uk.minute)
            return dt.replace(tzinfo=JAPAN_TZ)
        except (ValueError, IndexError):
            pass

    return datetime.now(JAPAN_TZ)


def _load_dedup() -> dict:
    """Load sent alerts dedup file."""
    if DEDUP_FILE.exists():
        try:
            return json.loads(DEDUP_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_dedup(data: dict):
    """Save sent alerts dedup file. Keep only last 3 days."""
    # Clean old entries
    cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    cleaned = {k: v for k, v in data.items() if k >= cutoff}
    DEDUP_FILE.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")


def _is_sent(dedup: dict, date_str: str, alert_id: str) -> bool:
    return alert_id in dedup.get(date_str, [])


def _mark_sent(dedup: dict, date_str: str, alert_id: str):
    if date_str not in dedup:
        dedup[date_str] = []
    dedup[date_str].append(alert_id)


def _time_to_minutes(time_str: str) -> int:
    """Convert "HH:MM" to minutes since midnight."""
    try:
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return -1


def _fetch_plan(date_str: str) -> dict | None:
    """Fetch day plan from Supabase."""
    try:
        import httpx
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept-Profile": "japan",
        }
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/japan_day_plans",
            headers=headers,
            params={"select": "*", "day_date": f"eq.{date_str}"},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
    except Exception as e:
        logger.debug(f"Japan alerts: failed to fetch plan: {e}")
    return None


def _fetch_bookings(date_str: str) -> list:
    """Fetch bookings from Supabase."""
    try:
        import httpx
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept-Profile": "japan",
        }
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/japan_bookings",
            headers=headers,
            params={"select": "*", "day_date": f"eq.{date_str}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug(f"Japan alerts: failed to fetch bookings: {e}")
    return []


def _load_food_picks() -> list:
    """Load food picks."""
    fp = Path("C:/Users/Chris Hadley/claude-projects/japan-family-guide/site/food-picks.json")
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


async def _send_whatsapp(text: str, target: str = CHRIS_WHATSAPP):
    """Send WhatsApp message."""
    try:
        from integrations.whatsapp import send_text
        await send_text(target, text)
        logger.info(f"Japan alert → WhatsApp: {text[:80]}")
    except Exception as e:
        logger.error(f"Japan alert WhatsApp send failed: {e}")


async def check_and_send_alerts(dry_run: bool = False) -> list[str]:
    """Check for alerts to send based on current JST time.

    Args:
        dry_run: If True, return alert messages without sending

    Returns:
        List of alert messages that were (or would be) sent
    """
    now_jst = _get_jst_now()
    today = datetime(now_jst.year, now_jst.month, now_jst.day)
    date_str = today.strftime("%Y-%m-%d")
    jst_hour = now_jst.hour
    jst_min = now_jst.minute
    current_minutes = jst_hour * 60 + jst_min

    # Check trip range
    today_naive = datetime(today.year, today.month, today.day)
    if today_naive < TRIP_START or today_naive > TRIP_END:
        return []

    trip_day = (today_naive - TRIP_START).days + 1

    # Load dedup
    dedup = _load_dedup()
    alerts_to_send = []

    # Fetch today's data
    plan = _fetch_plan(date_str)
    if not plan:
        return []

    items = plan.get("plan_data") or []
    city = plan.get("city", "")
    stay = plan.get("stay_name", "")
    bookings = _fetch_bookings(date_str)
    food_picks = _load_food_picks()
    today_picks = [p for p in food_picks if p.get("day") == trip_day]

    # ════════════════════════════════════════
    # RULE 1: Morning briefing (07:00 JST)
    # ════════════════════════════════════════
    if 7 * 60 <= current_minutes < 7 * 60 + 15:
        alert_id = "morning"
        if not _is_sent(dedup, date_str, alert_id):
            booked_count = sum(1 for i in items if i.get("booked"))
            highlights = [i.get("title", "") for i in items if i.get("booked")][:3]
            highlights_str = ", ".join(highlights) if highlights else "no bookings"

            msg = (
                f"🌅 *Good morning from {city}!*\n"
                f"Day {trip_day} of 17 · {today.strftime('%A, %B %-d' if os.name != 'nt' else '%A, %B %#d')}\n\n"
                f"📋 {len(items)} activities today"
                + (f" · {booked_count} booked ({highlights_str})" if booked_count else "")
                + f"\n\n📱 Full guide: hadley-japan-2026.surge.sh/day-{trip_day}.html"
            )
            alerts_to_send.append(("morning", alert_id, msg))

    # ════════════════════════════════════════
    # RULE 2: Pre-booking alerts (30 min before booked items)
    # ════════════════════════════════════════
    for i, item in enumerate(items):
        if not item.get("booked"):
            continue

        item_start = _time_to_minutes(item.get("time", ""))
        if item_start < 0:
            continue

        minutes_until = item_start - current_minutes
        alert_id = f"booking_{i}_{item.get('title', '')[:20]}"

        if 25 <= minutes_until <= 35 and not _is_sent(dedup, date_str, alert_id):
            title = item.get("title", "")
            location = item.get("location", "")
            notes = str(item.get("notes", ""))

            # Find matching booking for ref number
            ref = ""
            for b in bookings:
                if b.get("activity_title", "").lower() in title.lower() or title.lower() in b.get("activity_title", "").lower():
                    if b.get("confirmation_ref"):
                        ref = f"\n📋 Ref: {b['confirmation_ref']}"
                    break

            # Check for QR code mentions
            qr_note = ""
            if "qr" in notes.lower():
                qr_note = "\n📱 Show QR code on phone"

            # Check for cash-only
            cash_note = ""
            if any(kw in notes.lower() for kw in CASH_ONLY_KEYWORDS):
                cash_note = "\n💴 CASH ONLY — bring yen!"

            msg = (
                f"⏰ *{title}* in 30 minutes!\n"
                + (f"📍 {location}\n" if location else "")
                + (f"🕐 Entry: {item.get('time', '')}" + (f"–{item.get('end_time', '')}" if item.get("end_time") else ""))
                + ref + qr_note + cash_note
            )
            alerts_to_send.append(("booking", alert_id, msg))

    # ════════════════════════════════════════
    # RULE 3: Cash warning (60 min before cash-only food picks)
    # ════════════════════════════════════════
    for pick in today_picks:
        notes = str(pick.get("notes", "")).lower()
        if not any(kw in notes for kw in CASH_ONLY_KEYWORDS):
            continue

        # Try to find the time from the plan items
        restaurant = pick.get("restaurant", "")
        for item in items:
            if restaurant.lower() in item.get("title", "").lower():
                item_start = _time_to_minutes(item.get("time", ""))
                if item_start < 0:
                    continue
                minutes_until = item_start - current_minutes
                alert_id = f"cash_{restaurant[:20]}"
                if 55 <= minutes_until <= 65 and not _is_sent(dedup, date_str, alert_id):
                    msg = (
                        f"💴 *{restaurant}* in ~1 hour\n"
                        f"⚠️ CASH ONLY — make sure you have yen!\n"
                        f"💰 Budget: {pick.get('price', '?')} per person"
                    )
                    alerts_to_send.append(("cash", alert_id, msg))
                break

    # ════════════════════════════════════════
    # RULE 4: Pack/move reminder (20:00 JST)
    # ════════════════════════════════════════
    if 20 * 60 <= current_minutes < 20 * 60 + 15:
        alert_id = "pack_reminder"
        if not _is_sent(dedup, date_str, alert_id):
            # Check if moving tomorrow
            tomorrow_day = trip_day + 1
            if tomorrow_day <= 17:
                today_stay = STAY_BY_DAY.get(trip_day, "")
                tomorrow_stay = STAY_BY_DAY.get(tomorrow_day, "")
                if today_stay != tomorrow_stay:
                    checkout = CHECKOUT_TIMES.get(today_stay, "10:00")
                    msg = (
                        f"📦 *Moving tomorrow!*\n"
                        f"🏠 Checkout: {today_stay} by {checkout}\n"
                        f"🏠 Next: {tomorrow_stay}\n"
                        f"🧳 Pack tonight — early start tomorrow!"
                    )
                    alerts_to_send.append(("pack", alert_id, msg))

    # ════════════════════════════════════════
    # RULE 5: Confirmation reminder (20:00 JST, day before pending bookings)
    # ════════════════════════════════════════
    if 20 * 60 <= current_minutes < 20 * 60 + 15:
        tomorrow_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_day = trip_day + 1
        tomorrow_picks = [p for p in food_picks if p.get("day") == tomorrow_day]

        for pick in tomorrow_picks:
            notes = str(pick.get("notes", "")).lower()
            if any(kw in notes for kw in CONFIRM_KEYWORDS):
                alert_id = f"confirm_{pick.get('restaurant', '')[:20]}"
                if not _is_sent(dedup, date_str, alert_id):
                    msg = (
                        f"📱 *Action needed for tomorrow:*\n"
                        f"🍽️ {pick.get('restaurant', '')}\n"
                        f"📝 {pick.get('notes', '')[:150]}"
                    )
                    alerts_to_send.append(("confirm", alert_id, msg))

        # Also check bookings table for pending items tomorrow
        tomorrow_bookings = _fetch_bookings(tomorrow_str)
        for b in tomorrow_bookings:
            if b.get("status") == "pending":
                alert_id = f"confirm_booking_{b.get('activity_title', '')[:20]}"
                if not _is_sent(dedup, date_str, alert_id):
                    msg = (
                        f"📱 *Pending booking for tomorrow:*\n"
                        f"🍽️ {b.get('activity_title', '')}\n"
                        f"📝 {b.get('notes', '')[:150]}"
                    )
                    alerts_to_send.append(("confirm", alert_id, msg))

    # ════════════════════════════════════════
    # Send or return alerts
    # ════════════════════════════════════════
    sent_messages = []
    for alert_type, alert_id, msg in alerts_to_send:
        if dry_run:
            sent_messages.append(f"[{alert_type}] {msg}")
        else:
            await _send_whatsapp(msg)
            _mark_sent(dedup, date_str, alert_id)
            sent_messages.append(msg)

    # Save dedup
    if not dry_run and alerts_to_send:
        _save_dedup(dedup)

    return sent_messages

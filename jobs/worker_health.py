"""Memory System Health Check job.

Runs every 15 minutes to check Second Brain and capture queue status.
Posts alerts to #alerts if queue is stuck or circuit breaker is open.
"""

from logger import logger
from domains.peterbot import capture_store
from domains.peterbot.circuit_breaker import get_circuit_breaker

# Channel ID for #alerts
ALERTS_CHANNEL_ID = 1466019126194606286

# Thresholds
LOCAL_QUEUE_WARNING_THRESHOLD = 20  # Local pending captures
CIRCUIT_OPEN_ALERT_SECONDS = 1800  # Alert if circuit open for 30+ minutes


async def worker_health_check(bot):
    """Check memory system health and alert if degraded."""
    logger.debug("Running memory health check")

    # Check circuit breaker state
    circuit = get_circuit_breaker()
    circuit_stats = circuit.get_stats()
    circuit_state = circuit_stats["state"]
    time_in_state = circuit_stats.get("time_in_current_state")

    # Alert if circuit has been OPEN for too long
    if circuit_state == "open" and time_in_state and time_in_state >= CIRCUIT_OPEN_ALERT_SECONDS:
        await _send_alert(
            bot,
            f"🔴 **Circuit Breaker OPEN**\n\n"
            f"Memory circuit has been **OPEN** for **{time_in_state // 60}** minutes.\n"
            f"Failures: {circuit_stats['total_failures']} | "
            f"Times opened: {circuit_stats['times_opened']}\n\n"
            f"Second Brain may be unreachable. Memory context and captures are degraded."
        )
        logger.warning(f"Circuit breaker OPEN for {time_in_state}s")

    # Check local capture queue
    local_stats = capture_store.get_queue_stats()
    local_pending = local_stats.get("pending_count", 0)
    oldest_age = local_stats.get("oldest_pending_age", 0)

    # Alert if local queue is building up
    if local_pending > LOCAL_QUEUE_WARNING_THRESHOLD:
        circuit_info = f"Circuit: **{circuit_state.upper()}**\n" if circuit_state != "closed" else ""
        await _send_alert(
            bot,
            f"⚠️ **Local Capture Queue Building**\n\n"
            f"{circuit_info}"
            f"Pending captures: **{local_pending}**\n"
            f"Oldest pending: **{oldest_age}s** ago\n"
            f"Sent: {local_stats.get('sent_count', 0)} | "
            f"Failed: {local_stats.get('failed_count', 0)}\n\n"
            f"Messages are being queued locally. Second Brain may be slow or unreachable."
        )
        logger.warning(f"Local capture queue building: {local_pending} pending, circuit={circuit_state}")

    # Log normal status
    if local_pending > 0 or circuit_state != "closed":
        logger.info(f"Memory health: local_pending={local_pending}, circuit={circuit_state}")
    else:
        logger.debug(f"Memory health: local_pending={local_pending}, circuit={circuit_state}")


async def _send_alert(bot, message: str):
    """Send alert to #alerts channel."""
    try:
        channel = bot.get_channel(ALERTS_CHANNEL_ID)
        if not channel:
            channel = await bot.fetch_channel(ALERTS_CHANNEL_ID)

        if channel:
            await channel.send(message)
            logger.info("Sent memory health alert to #alerts")
        else:
            logger.error(f"Could not find #alerts channel {ALERTS_CHANNEL_ID}")
    except Exception as e:
        logger.error(f"Failed to send memory health alert: {e}")


def register_worker_health(scheduler, bot):
    """Register the memory health check job with the scheduler."""
    scheduler.add_job(
        worker_health_check,
        'interval',
        args=[bot],
        minutes=15,
        id="worker_health_check"
    )
    logger.info("Registered memory health check job (every 15 mins)")

"""Memory Worker Health Check job.

Runs every 15 minutes to check peterbot-mem worker status.
Posts alerts to #alerts if queue is stuck or worker unreachable.
Also monitors the local capture queue for pending messages.
Includes circuit breaker state monitoring.
"""

import httpx

from logger import logger
from domains.peterbot import config
from domains.peterbot import capture_store
from domains.peterbot.circuit_breaker import get_circuit_breaker, CircuitState

# Channel ID for #alerts
ALERTS_CHANNEL_ID = 1466019126194606286

# Thresholds
QUEUE_WARNING_THRESHOLD = 50
QUEUE_ALERT_THRESHOLD = 100
LOCAL_QUEUE_WARNING_THRESHOLD = 20  # Local pending captures
CIRCUIT_OPEN_ALERT_SECONDS = 1800  # Alert if circuit open for 30+ minutes


async def _get_worker_status() -> dict:
    """Get worker processing status."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{config.WORKER_URL}/api/processing-status",
                timeout=5
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}"}
    except httpx.ConnectError:
        return {"error": "Worker unreachable"}
    except Exception as e:
        return {"error": str(e)}


async def worker_health_check(bot):
    """Check memory worker health and alert if stuck."""
    logger.debug("Running worker health check")

    # Check circuit breaker state first
    circuit = get_circuit_breaker()
    circuit_stats = circuit.get_stats()
    circuit_state = circuit_stats["state"]
    time_in_state = circuit_stats.get("time_in_current_state")

    # Alert if circuit has been OPEN for too long
    if circuit_state == "open" and time_in_state and time_in_state >= CIRCUIT_OPEN_ALERT_SECONDS:
        await _send_alert(
            bot,
            f"🔴 **Circuit Breaker OPEN**\n\n"
            f"Memory worker circuit has been **OPEN** for **{time_in_state // 60}** minutes.\n"
            f"Failures: {circuit_stats['total_failures']} | "
            f"Times opened: {circuit_stats['times_opened']}\n\n"
            f"Worker may need manual intervention. Memory context and captures are degraded."
        )
        logger.warning(f"Circuit breaker OPEN for {time_in_state}s")

    # Check local capture queue
    local_stats = capture_store.get_queue_stats()
    local_pending = local_stats.get("pending_count", 0)
    oldest_age = local_stats.get("oldest_pending_age", 0)

    # Alert if local queue is building up (indicates worker may be down)
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
            f"Messages are being queued locally. Worker may be slow or unreachable."
        )
        logger.warning(f"Local capture queue building: {local_pending} pending, circuit={circuit_state}")

    # Check remote worker status
    status = await _get_worker_status()

    # Check for errors first
    if "error" in status:
        await _send_alert(
            bot,
            f"🔴 **Memory Worker Error**\n\n"
            f"Cannot reach peterbot-mem worker:\n`{status['error']}`\n\n"
            f"Circuit: **{circuit_state.upper()}**\n"
            f"Local queue: **{local_pending}** captures pending\n"
            f"Self-reflect observations are being queued locally for retry."
        )
        logger.error(f"Worker health check failed: {status['error']}, circuit={circuit_state}")
        return

    queue_depth = status.get("queueDepth", 0)
    is_processing = status.get("isProcessing", False)

    # Critical: Queue has items but nothing processing (stuck)
    if queue_depth > 0 and not is_processing:
        await _send_alert(
            bot,
            f"🔴 **Memory Worker Stuck**\n\n"
            f"Queue depth: **{queue_depth}** messages\n"
            f"Processing: **stopped**\n\n"
            f"Self-reflect observations are backing up. Worker restart needed."
        )
        logger.error(f"Worker stuck: {queue_depth} pending, not processing")
        return

    # Warning: Queue backlog building
    if queue_depth > QUEUE_ALERT_THRESHOLD:
        await _send_alert(
            bot,
            f"⚠️ **Memory Queue Backlog**\n\n"
            f"Queue depth: **{queue_depth}** messages\n"
            f"Processing: {'active' if is_processing else 'stopped'}\n\n"
            f"Consider checking worker performance."
        )
        logger.warning(f"Queue backlog: {queue_depth} pending")
        return

    # Log normal status at debug level
    if queue_depth > QUEUE_WARNING_THRESHOLD or circuit_state != "closed":
        logger.info(f"Worker health: queue={queue_depth}, processing={is_processing}, local_pending={local_pending}, circuit={circuit_state}")
    else:
        logger.debug(f"Worker health: queue={queue_depth}, processing={is_processing}, local_pending={local_pending}, circuit={circuit_state}")


async def _send_alert(bot, message: str):
    """Send alert to #alerts channel."""
    try:
        channel = bot.get_channel(ALERTS_CHANNEL_ID)
        if not channel:
            channel = await bot.fetch_channel(ALERTS_CHANNEL_ID)

        if channel:
            await channel.send(message)
            logger.info(f"Sent worker health alert to #alerts")
        else:
            logger.error(f"Could not find #alerts channel {ALERTS_CHANNEL_ID}")
    except Exception as e:
        logger.error(f"Failed to send worker health alert: {e}")


def register_worker_health(scheduler, bot):
    """Register the worker health check job with the scheduler."""
    scheduler.add_job(
        worker_health_check,
        'interval',
        args=[bot],
        minutes=15,
        id="worker_health_check"
    )
    logger.info("Registered worker health check job (every 15 mins)")

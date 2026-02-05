"""Background Capture Processor job.

Drains the pending capture queue by sending captures to the worker.
Runs every 30 seconds, processes up to 10 captures per cycle.
Respects circuit breaker to avoid hammering dead worker.
"""

import asyncio

from logger import logger
from domains.peterbot import config
from domains.peterbot import capture_store
from domains.peterbot import memory
from domains.peterbot.circuit_breaker import get_circuit_breaker, CircuitState


async def process_pending_captures():
    """Process pending captures from the queue.

    Logic:
    1. Check circuit state - if OPEN, skip entire cycle
    2. Get oldest pending capture
    3. Attempt send (with 5s timeout)
    4. On success: mark sent
    5. On failure: increment retries (mark failed if >= max retries)
    6. Wait 2 seconds before next item
    7. Process max 10 per cycle (prevent runaway)
    """
    circuit = get_circuit_breaker()

    # Check circuit state first
    if circuit.state == CircuitState.OPEN:
        logger.debug("Capture processor: circuit OPEN, skipping cycle")
        return

    stats = capture_store.get_queue_stats()
    pending_count = stats.get("pending_count", 0)

    if pending_count == 0:
        logger.debug("Capture processor: no pending captures")
        return

    logger.info(f"Capture processor: starting cycle with {pending_count} pending")

    processed = 0
    sent = 0
    failed = 0
    max_per_cycle = config.CAPTURE_PROCESSOR_MAX_PER_CYCLE
    delay_between = config.CAPTURE_PROCESSOR_DELAY_BETWEEN

    while processed < max_per_cycle:
        # Check circuit again in case it opened during processing
        if circuit.state == CircuitState.OPEN:
            logger.info(f"Capture processor: circuit opened mid-cycle, stopping")
            break

        # Get oldest pending capture
        pending = capture_store.get_pending(limit=1)
        if not pending:
            break

        capture = pending[0]
        processed += 1

        # Mark as sending to prevent duplicate processing
        capture_store.mark_sending(capture.id)

        # Attempt to send
        try:
            success = await memory.send_capture_to_worker(capture)

            if success:
                capture_store.mark_sent(capture.id)
                sent += 1
                logger.debug(f"Capture {capture.id} sent successfully")
            else:
                # Send failed - mark_failed handles retry logic
                capture_store.mark_failed(capture.id, "Background processor send failed")
                failed += 1
                logger.debug(f"Capture {capture.id} send failed, will retry")

        except Exception as e:
            # Unexpected error
            capture_store.mark_failed(capture.id, str(e))
            failed += 1
            logger.warning(f"Capture {capture.id} unexpected error: {e}")

        # Wait before next item (don't hammer worker)
        if processed < max_per_cycle:
            await asyncio.sleep(delay_between)

    logger.info(f"Capture processor: cycle complete - processed={processed}, sent={sent}, failed={failed}")


async def cleanup_old_captures():
    """Daily cleanup of old captures.

    Deletes:
    - Sent captures older than CAPTURE_SENT_RETENTION_DAYS (default 7)
    - Failed captures older than CAPTURE_FAILED_RETENTION_DAYS (default 30)
    """
    logger.info("Running capture cleanup job")

    try:
        sent_deleted, failed_deleted = capture_store.cleanup_old_captures()

        if sent_deleted or failed_deleted:
            logger.info(f"Capture cleanup: deleted {sent_deleted} sent, {failed_deleted} failed")
        else:
            logger.debug("Capture cleanup: no old captures to delete")

        # Also cleanup expired context cache
        cache_deleted = capture_store.cleanup_expired_cache()
        if cache_deleted:
            logger.info(f"Cache cleanup: deleted {cache_deleted} expired entries")

    except Exception as e:
        logger.error(f"Capture cleanup failed: {e}")


def register_capture_processor(scheduler, bot=None):
    """Register the capture processor job with the scheduler.

    Args:
        scheduler: APScheduler instance
        bot: Discord bot instance (not used, but kept for API consistency)
    """
    # Main processor job - runs every 30 seconds
    scheduler.add_job(
        process_pending_captures,
        'interval',
        seconds=config.CAPTURE_PROCESSOR_INTERVAL,
        id="capture_processor",
        max_instances=1,  # Prevent overlapping runs
        coalesce=True,    # Combine missed runs
    )
    logger.info(f"Registered capture processor job (every {config.CAPTURE_PROCESSOR_INTERVAL}s)")

    # Daily cleanup job - runs at 3:00 AM
    scheduler.add_job(
        cleanup_old_captures,
        'cron',
        hour=3,
        minute=0,
        id="capture_cleanup",
    )
    logger.info("Registered capture cleanup job (daily at 3:00 AM)")

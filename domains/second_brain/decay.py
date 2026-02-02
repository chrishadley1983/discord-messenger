"""Decay model for Second Brain.

Implements time-based decay with access boost:
- 90-day half-life exponential decay
- Access boost: decay_score * (1 + log2(access_count + 1))
- Priority multipliers: explicit=1.0, seed=0.8, passive=0.3
"""

import math
from datetime import datetime, timezone

from .config import DECAY_HALF_LIFE_DAYS


def calculate_decay_score(
    created_at: datetime,
    last_accessed_at: datetime | None = None,
    access_count: int = 0,
    base_priority: float = 1.0,
    now: datetime | None = None,
) -> float:
    """Calculate the current decay score for an item.

    Formula:
        base_decay = 0.5 ^ (days_since_last_access / 90)
        access_boost = 1 + log2(access_count + 1)
        final_score = base_priority * base_decay * access_boost

    Args:
        created_at: When item was created
        last_accessed_at: When item was last accessed (or created if None)
        access_count: Number of times item has been accessed
        base_priority: Priority multiplier (1.0 explicit, 0.8 seed, 0.3 passive)
        now: Current time (defaults to utcnow)

    Returns:
        Decay score between 0 and infinity (higher = more relevant)
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Use last_accessed_at or created_at
    reference_time = last_accessed_at or created_at

    # Handle timezone-naive datetimes
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # Calculate days since last access
    days_elapsed = (now - reference_time).total_seconds() / 86400

    # Exponential decay with 90-day half-life
    # decay = 0.5^(days/90)
    base_decay = math.pow(0.5, days_elapsed / DECAY_HALF_LIFE_DAYS)

    # Access boost using log2
    # Adds logarithmic bonus for frequently accessed items
    access_boost = 1 + math.log2(access_count + 1)

    # Final score
    return base_priority * base_decay * access_boost


def estimate_days_until_threshold(
    current_decay: float,
    threshold: float = 0.1,
    access_count: int = 0,
    base_priority: float = 1.0,
) -> int:
    """Estimate days until an item falls below a decay threshold.

    Useful for "fading items" detection.

    Args:
        current_decay: Current decay score
        threshold: Score threshold (default 0.1)
        access_count: Current access count
        base_priority: Base priority

    Returns:
        Estimated days until threshold, or -1 if already below
    """
    if current_decay <= threshold:
        return -1

    access_boost = 1 + math.log2(access_count + 1)

    # Solve for days: threshold = priority * 0.5^(d/90) * access_boost
    # 0.5^(d/90) = threshold / (priority * access_boost)
    # d/90 = log(threshold / (priority * access_boost)) / log(0.5)
    # d = 90 * log(threshold / (priority * access_boost)) / log(0.5)

    target_decay = threshold / (base_priority * access_boost)

    if target_decay >= 1:
        return 0  # Already above threshold with just priority

    days = DECAY_HALF_LIFE_DAYS * math.log(target_decay) / math.log(0.5)
    return max(0, int(days))


def decay_score_at_days(
    days: int,
    access_count: int = 0,
    base_priority: float = 1.0,
) -> float:
    """Calculate what the decay score will be after N days.

    Assumes no additional accesses.

    Args:
        days: Days in the future
        access_count: Current access count
        base_priority: Base priority

    Returns:
        Predicted decay score
    """
    base_decay = math.pow(0.5, days / DECAY_HALF_LIFE_DAYS)
    access_boost = 1 + math.log2(access_count + 1)
    return base_priority * base_decay * access_boost


def is_fading(
    decay_score: float,
    threshold: float = 0.3,
) -> bool:
    """Check if an item is considered "fading" (low relevance).

    Args:
        decay_score: Current decay score
        threshold: Fading threshold

    Returns:
        True if item is fading
    """
    return decay_score < threshold


def calculate_access_boost_needed(
    current_decay: float,
    target_decay: float,
    base_priority: float = 1.0,
    base_decay: float = 1.0,
) -> int:
    """Calculate how many accesses needed to reach a target score.

    Args:
        current_decay: Current decay score
        target_decay: Target decay score
        base_priority: Base priority
        base_decay: Current time-based decay component

    Returns:
        Number of additional accesses needed, or 0 if already met
    """
    if current_decay >= target_decay:
        return 0

    # target = priority * base_decay * (1 + log2(n + 1))
    # (1 + log2(n + 1)) = target / (priority * base_decay)
    # log2(n + 1) = target / (priority * base_decay) - 1
    # n + 1 = 2^(target / (priority * base_decay) - 1)
    # n = 2^(target / (priority * base_decay) - 1) - 1

    needed_boost = target_decay / (base_priority * base_decay)
    if needed_boost <= 1:
        return 0

    access_needed = math.pow(2, needed_boost - 1) - 1
    return max(0, int(math.ceil(access_needed)))

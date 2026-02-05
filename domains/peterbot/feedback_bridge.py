"""Feedback Bridge: Integration between peterbot-mem observations and Second Brain.

When peterbot-mem captures an observation indicating user validated content
(e.g., "user enjoyed the recipe"), this module:
1. Searches Second Brain for matching passive capture
2. If found: promotes it to higher priority with validation metadata
3. If not found: searches conversation history and backfills to Second Brain

This bridges the two memory systems - peterbot-mem knows facts ABOUT the user,
Second Brain knows the CONTENT itself.
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from logger import logger


# Patterns indicating positive feedback/validation
POSITIVE_FEEDBACK_PATTERNS = [
    r"was delicious",
    r"worked perfectly",
    r"worked great",
    r"worked well",
    r"exactly what i needed",
    r"that's great",
    r"that was great",
    r"perfect\b",
    r"loved it",
    r"thanks.*(that|this)",
    r"brilliant",
    r"amazing",
    r"spot on",
    r"nailed it",
    r"just what i (needed|wanted)",
    r"really helpful",
    r"super helpful",
    # Document/report feedback patterns
    r"good work",
    r"nice work",
    r"great work",
    r"well done",
    r"useful\b",
    r"helpful\b",
    r"thanks for (that|the|this)",
    r"great (analysis|report|summary|document|breakdown)",
    r"good (analysis|report|summary|document|breakdown)",
    r"appreciate (that|this|the)",
    r"exactly (right|correct)",
    r"this is (great|good|useful|helpful)",
    r"that was (great|good|useful|helpful)",
]

# Patterns indicating the feedback references something Peter provided
REFERENCE_PATTERNS = [
    r"that (recipe|script|code|recommendation|suggestion|idea|report|analysis|summary|document|breakdown|overview)",
    r"(the|your) (recipe|script|code|recommendation|suggestion|idea|report|analysis|summary|document|breakdown|overview)",
    r"(it|that) worked",
    r"(made|tried|used|read) (it|that|the)",
    r"(it|that) (was|is) (useful|helpful|great|good)",
]


def detect_positive_feedback(message: str) -> bool:
    """Detect if a message contains positive feedback about something Peter provided.

    Args:
        message: User's message text

    Returns:
        True if message appears to be positive feedback
    """
    message_lower = message.lower()

    # Check for positive feedback patterns
    has_positive = any(
        re.search(pattern, message_lower)
        for pattern in POSITIVE_FEEDBACK_PATTERNS
    )

    if not has_positive:
        return False

    # Check if it references something Peter provided
    has_reference = any(
        re.search(pattern, message_lower)
        for pattern in REFERENCE_PATTERNS
    )

    # Also accept short messages that are clearly feedback
    # (e.g., "was delicious!" by itself)
    is_short_feedback = len(message.split()) <= 10 and has_positive

    return has_reference or is_short_feedback


async def search_second_brain_for_content(query: str, limit: int = 5) -> list[dict]:
    """Search Second Brain for content matching the query.

    Args:
        query: Search query (e.g., "raspberry baked oats recipe")
        limit: Max results

    Returns:
        List of matching items with id, title, similarity
    """
    try:
        from domains.second_brain.db import semantic_search

        results = await semantic_search(
            query=query,
            min_similarity=0.6,  # Lower threshold to catch more candidates
            limit=limit,
        )

        return [
            {
                "id": str(result.item.id),
                "title": result.item.title,
                "similarity": result.best_similarity,
                "capture_type": result.item.capture_type.value,
                "created_at": result.item.created_at.isoformat() if result.item.created_at else None,
            }
            for result in results
        ]
    except Exception as e:
        logger.warning(f"Second Brain search failed: {e}")
        return []


async def promote_second_brain_item(
    item_id: str,
    validation_context: str,
) -> bool:
    """Promote a Second Brain item based on user validation.

    Increases priority and adds validation metadata.

    Args:
        item_id: UUID of the item to promote
        validation_context: Description of the validation (e.g., "User said 'was delicious!'")

    Returns:
        True if promotion succeeded
    """
    try:
        from uuid import UUID
        from domains.second_brain.db import update_knowledge_item, get_knowledge_item

        item_uuid = UUID(item_id)

        # Get current item to check capture_type
        item = await get_knowledge_item(item_uuid)
        if not item:
            logger.warning(f"Item {item_id} not found for promotion")
            return False

        # Build new priority - boost from passive (0.3) to near-explicit (0.9)
        # If already explicit, still boost to 1.0
        new_priority = 0.9 if item.capture_type.value == "passive" else 1.0

        # Update with promotion
        await update_knowledge_item(
            item_uuid,
            base_priority=new_priority,
            decay_score=new_priority,  # Reset decay
            capture_type="explicit",  # Promote to explicit
            promoted_at=datetime.now(timezone.utc).isoformat(),
            user_note=f"Validated: {validation_context}",
        )

        logger.info(f"Promoted Second Brain item {item_id}: {validation_context}")
        return True

    except Exception as e:
        logger.error(f"Failed to promote item {item_id}: {e}")
        return False


async def extract_topic_from_observation(observation_text: str) -> Optional[str]:
    """Extract the topic/subject from an observation about validated content.

    Args:
        observation_text: The observation title or subtitle from peterbot-mem
                         e.g., "User enjoyed the raspberry baked oats recipe"

    Returns:
        Extracted topic for Second Brain search, or None
    """
    text_lower = observation_text.lower()

    # Common patterns: "enjoyed the X", "loved the X", "found X delicious"
    patterns = [
        r"enjoyed (?:the )?(.+?)(?:\s+and|\s+recipe|\s+$)",
        r"loved (?:the )?(.+?)(?:\s+and|\s+recipe|\s+$)",
        r"found (?:the )?(.+?) (?:delicious|helpful|useful)",
        r"(.+?) (?:recipe|script|code|recommendation) (?:was|worked)",
        r"validated (?:the )?(.+?)(?:\s+$|\s+as)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            topic = match.group(1).strip()
            # Clean up common words
            topic = re.sub(r"^(that|the|this|a|an)\s+", "", topic)
            if len(topic) > 3:  # Avoid too-short topics
                return topic

    # Fallback: extract noun phrases (simple approach)
    # Look for content after "enjoyed" or "loved"
    for trigger in ["enjoyed", "loved", "validated", "liked"]:
        if trigger in text_lower:
            after = text_lower.split(trigger, 1)[1].strip()
            # Take first few words as topic
            words = after.split()[:5]
            topic = " ".join(words).strip(".,!?")
            if len(topic) > 3:
                return topic

    return None


async def handle_feedback_observation(
    observation_title: str,
    observation_subtitle: str,
    observation_narrative: str,
    session_id: str,
) -> dict:
    """Handle a peterbot-mem observation that indicates user validated content.

    This is the main integration point. Called when peterbot-mem extracts
    an observation about user enjoying/validating something Peter provided.

    Args:
        observation_title: Title from peterbot-mem observation
        observation_subtitle: Subtitle from observation
        observation_narrative: Full narrative
        session_id: Peterbot-mem session ID (for backfill search)

    Returns:
        Dict with action taken: {action: 'promoted'|'backfilled'|'not_found', item_id: str|None}
    """
    # Extract what the user validated
    topic = await extract_topic_from_observation(observation_title)
    if not topic:
        topic = await extract_topic_from_observation(observation_subtitle)

    if not topic:
        logger.debug(f"Could not extract topic from observation: {observation_title}")
        return {"action": "no_topic", "item_id": None}

    logger.info(f"Feedback bridge: Searching Second Brain for '{topic}'")

    # Search Second Brain for matching content
    results = await search_second_brain_for_content(topic, limit=3)

    if results:
        # Found matching content - promote the best match
        best = results[0]
        validation_context = f"User feedback: {observation_title[:100]}"

        success = await promote_second_brain_item(best["id"], validation_context)

        if success:
            logger.info(f"Feedback bridge: Promoted item '{best['title']}' based on validation")
            return {"action": "promoted", "item_id": best["id"], "title": best["title"]}
        else:
            return {"action": "promote_failed", "item_id": best["id"]}

    # Not found in Second Brain - try to backfill from conversation history
    logger.info(f"Feedback bridge: Content not in Second Brain, attempting backfill")

    backfill_result = await _attempt_backfill(topic, observation_narrative, session_id)

    if backfill_result:
        return {"action": "backfilled", "item_id": backfill_result}
    else:
        return {"action": "not_found", "item_id": None, "topic": topic}


async def _attempt_backfill(
    topic: str,
    observation_narrative: str,
    session_id: str,
) -> Optional[str]:
    """Attempt to find and backfill content from conversation history.

    Args:
        topic: What we're looking for (e.g., "raspberry baked oats")
        observation_narrative: Full narrative which might contain the content
        session_id: Session ID for log search

    Returns:
        New item ID if backfilled, None otherwise
    """
    # First, check if the observation narrative contains the actual content
    # (Sometimes the observation includes the recipe/content itself)
    if _looks_like_actionable_content(observation_narrative):
        return await _save_content_to_second_brain(
            title=f"Validated: {topic}",
            content=observation_narrative,
            context="Backfilled from observation - user validated this content",
        )

    # Otherwise, we'd need to search conversation logs
    # This is more complex - for now, log that we couldn't backfill
    logger.warning(
        f"Feedback bridge: Could not backfill '{topic}' - "
        "content not in observation narrative and log search not implemented"
    )
    return None


def _looks_like_actionable_content(text: str) -> bool:
    """Check if text contains actual actionable content (recipe, code, etc.)."""
    text_lower = text.lower()

    # Recipe indicators
    recipe_patterns = ["ingredients", "preheat", "minutes", "tablespoon", "teaspoon", "bake"]
    recipe_matches = sum(1 for p in recipe_patterns if p in text_lower)

    # Code indicators
    code_patterns = ["```", "def ", "function ", "import ", "return "]
    code_matches = sum(1 for p in code_patterns if p in text_lower)

    # Instruction indicators
    instruction_patterns = ["step 1", "step 2", "first,", "then,", "finally,"]
    instruction_matches = sum(1 for p in instruction_patterns if p in text_lower)

    return recipe_matches >= 2 or code_matches >= 2 or instruction_matches >= 2


async def _save_content_to_second_brain(
    title: str,
    content: str,
    context: str,
) -> Optional[str]:
    """Save content to Second Brain with high priority.

    Args:
        title: Title for the item
        content: Full content text
        context: Context note

    Returns:
        New item ID if saved, None otherwise
    """
    try:
        from domains.second_brain.pipeline import process_capture
        from domains.second_brain.types import CaptureType

        item = await process_capture(
            source=content,
            capture_type=CaptureType.EXPLICIT,  # High priority since user validated
            user_note=context,
        )

        if item:
            logger.info(f"Feedback bridge: Backfilled content to Second Brain: {item.id}")
            return item.id
        return None

    except Exception as e:
        logger.error(f"Failed to backfill to Second Brain: {e}")
        return None


async def process_user_feedback(
    user_message: str,
    channel_id: int,
) -> Optional[dict]:
    """Process a user message that might contain feedback.

    Called from the router when a message is detected as potential feedback.
    Triggers the feedback bridge if positive feedback is detected.

    Args:
        user_message: The user's message
        channel_id: Discord channel ID (for context)

    Returns:
        Result dict if feedback was processed, None otherwise
    """
    if not detect_positive_feedback(user_message):
        return None

    logger.info(f"Feedback bridge: Detected positive feedback in message")

    # Search peterbot-mem for recent observations about content Peter provided
    # Then cross-reference with Second Brain
    try:
        # Use MCP tools to search recent observations
        # For now, do a simple Second Brain search based on the feedback message
        from domains.second_brain.db import semantic_search

        # Extract what they might be referring to
        # Simple approach: search Second Brain for recent Peter responses
        results = await semantic_search(
            query=user_message,
            min_similarity=0.5,
            limit=3,
        )

        if results:
            # Found something - promote it
            best = results[0]
            validation_context = f"User feedback: {user_message[:100]}"

            success = await promote_second_brain_item(
                str(best.item.id),
                validation_context,
            )

            if success:
                return {
                    "action": "promoted",
                    "item_id": str(best.item.id),
                    "title": best.item.title,
                    "feedback": user_message[:100],
                }

        return {"action": "no_match", "feedback": user_message[:100]}

    except Exception as e:
        logger.warning(f"Feedback processing failed: {e}")
        return None

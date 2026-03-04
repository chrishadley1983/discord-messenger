"""Structured extraction for Second Brain using Claude API.

Extracts facts (factual statements) and concepts (insights with types)
from conversation content. Used for conversation_extract items to replicate
the structured observation format from peterbot-mem.
"""

import json
import re

from logger import logger
from .config import (
    call_claude,
    STRUCTURED_EXTRACTION_TIMEOUT,
    MAX_FACTS_PER_ITEM,
    MAX_CONCEPTS_PER_ITEM,
)


EXTRACT_PROMPT = """Analyse this conversation and extract structured knowledge.

Return a JSON object with two arrays:

1. "facts" — Concrete factual statements (dates, numbers, decisions, names).
   Each fact should be a standalone sentence that makes sense without context.
   Max 8 facts.

2. "concepts" — Conceptual insights or patterns discovered.
   Each concept is an object with:
   - "label": Short name (2-5 words)
   - "type": One of: how-it-works, why-it-exists, gotcha, pattern, trade-off
   - "detail": One sentence explanation
   Max 5 concepts.

If the conversation is trivial (greetings, simple commands), return empty arrays.

Title: {title}

Content:
{text}

Return ONLY the JSON object, no other text:
{{"facts": [...], "concepts": [...]}}"""


CONCEPT_TYPES = {"how-it-works", "why-it-exists", "gotcha", "pattern", "trade-off"}


async def extract_structured(text: str, title: str | None = None) -> dict:
    """Extract facts and concepts from content.

    Args:
        text: Full content text (typically a conversation)
        title: Optional title for context

    Returns:
        Dict with 'facts' (list[str]) and 'concepts' (list[dict])
    """
    truncated_text = text[:6000] if len(text) > 6000 else text
    prompt = EXTRACT_PROMPT.format(
        title=title or "Untitled conversation",
        text=truncated_text,
    )

    result = await call_claude(prompt, max_tokens=500, timeout=STRUCTURED_EXTRACTION_TIMEOUT)
    if result:
        return _parse_structured_response(result)

    logger.warning("Structured extraction failed, returning empty")
    return {"facts": [], "concepts": []}


def _parse_structured_response(response: str) -> dict:
    """Parse the JSON response from Claude."""
    try:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            facts = _validate_facts(parsed.get("facts", []))
            concepts = _validate_concepts(parsed.get("concepts", []))
            return {"facts": facts, "concepts": concepts}
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse structured extraction JSON: {response[:200]}")

    return {"facts": [], "concepts": []}


def _validate_facts(facts: list) -> list[str]:
    """Validate and clean facts array."""
    if not isinstance(facts, list):
        return []
    validated = []
    for fact in facts:
        if isinstance(fact, str) and len(fact.strip()) > 5:
            validated.append(fact.strip())
    return validated[:MAX_FACTS_PER_ITEM]


def _validate_concepts(concepts: list) -> list[dict]:
    """Validate and clean concepts array."""
    if not isinstance(concepts, list):
        return []
    validated = []
    for concept in concepts:
        if not isinstance(concept, dict):
            continue
        label = concept.get("label", "").strip()
        ctype = concept.get("type", "").strip()
        detail = concept.get("detail", "").strip()
        if not label or not detail:
            continue
        if ctype not in CONCEPT_TYPES:
            ctype = "pattern"
        validated.append({"label": label, "type": ctype, "detail": detail})
    return validated[:MAX_CONCEPTS_PER_ITEM]

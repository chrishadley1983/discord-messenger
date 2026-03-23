"""Structured extraction for Second Brain using Claude API.

Extracts facts (factual statements) and concepts (insights with types)
from content. Uses content-type-aware prompts for better extraction.
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


# Content-type-specific extraction prompts
_EXTRACT_PROMPTS: dict[str, str] = {
    "email": """Extract structured knowledge from this email.

Focus on:
- Decisions made or confirmed
- Action items and deadlines
- Monetary amounts, prices, quantities
- People mentioned and their roles
- Key dates and commitments

Title: {title}
Content:
{text}

Return ONLY the JSON object:
{{"facts": ["fact1", ...], "concepts": [{{"label": "...", "type": "...", "detail": "..."}}]}}""",

    "health_activity": """Extract structured knowledge from this fitness/health data.

Focus on:
- Personal records or milestones (e.g. fastest 5K, new weight low)
- Performance trends (improving/declining metrics)
- Notable achievements or benchmarks
- Health metrics that stand out (abnormal HR, poor sleep, etc.)

Title: {title}
Content:
{text}

Return ONLY the JSON object:
{{"facts": ["fact1", ...], "concepts": [{{"label": "...", "type": "...", "detail": "..."}}]}}""",

    "financial_report": """Extract structured knowledge from this financial data.

Focus on:
- Key financial figures (income, expenses, net worth, savings rate)
- Month-on-month or year-on-year changes
- Anomalies or unusual transactions
- Budget adherence or deviation
- Investment performance

Title: {title}
Content:
{text}

Return ONLY the JSON object:
{{"facts": ["fact1", ...], "concepts": [{{"label": "...", "type": "...", "detail": "..."}}]}}""",

    "calendar_event": """Extract structured knowledge from this calendar event.

Focus on:
- Who is involved and their roles
- What is happening and where
- Any preparation needed or follow-ups
- Recurring patterns or scheduling context

Title: {title}
Content:
{text}

Return ONLY the JSON object:
{{"facts": ["fact1", ...], "concepts": [{{"label": "...", "type": "...", "detail": "..."}}]}}""",

    "travel_booking": """Extract structured knowledge from this travel booking.

Focus on:
- Dates, times, confirmation references
- Costs and payment details
- Logistics (check-in times, addresses, transport)
- Important policies (cancellation, luggage, etc.)

Title: {title}
Content:
{text}

Return ONLY the JSON object:
{{"facts": ["fact1", ...], "concepts": [{{"label": "...", "type": "...", "detail": "..."}}]}}""",

    "conversation_extract": """Analyse this conversation and extract structured knowledge.

Focus on:
- Concrete factual statements (dates, numbers, decisions, names)
- Conceptual insights or patterns discovered
- Technical knowledge or how-things-work explanations

Title: {title}
Content:
{text}

Return ONLY the JSON object:
{{"facts": ["fact1", ...], "concepts": [{{"label": "...", "type": "...", "detail": "..."}}]}}""",

    "commit": """Extract structured knowledge from this code commit/PR.

Focus on:
- What was changed and why
- Technical decisions or architectural choices
- Bug fixes and their root causes
- New capabilities or features added

Title: {title}
Content:
{text}

Return ONLY the JSON object:
{{"facts": ["fact1", ...], "concepts": [{{"label": "...", "type": "...", "detail": "..."}}]}}""",

    "recipe": """Extract structured knowledge from this recipe.

Focus on:
- Key ingredients and quantities
- Cooking techniques or tips
- Dietary information (calories, protein, allergens)
- Family preferences or ratings

Title: {title}
Content:
{text}

Return ONLY the JSON object:
{{"facts": ["fact1", ...], "concepts": [{{"label": "...", "type": "...", "detail": "..."}}]}}""",
}

# Default prompt for content types without a specific template
_DEFAULT_EXTRACT_PROMPT = """Extract structured knowledge from this content.

Return a JSON object with:
1. "facts" — Concrete factual statements (dates, numbers, decisions, names, amounts).
   Each fact should be a standalone sentence. Max {max_facts} facts.
2. "concepts" — Conceptual insights or patterns.
   Each concept: {{"label": "Short name", "type": "one-of-types", "detail": "One sentence"}}
   Types: how-it-works, why-it-exists, gotcha, pattern, trade-off, decision, metric, event, preference, recommendation, milestone
   Max {max_concepts} concepts.

If the content is trivial, return empty arrays.

Title: {title}
Content:
{text}

Return ONLY the JSON object:
{{"facts": [...], "concepts": [...]}}"""


CONCEPT_TYPES = {
    "how-it-works", "why-it-exists", "gotcha", "pattern", "trade-off",
    "decision", "metric", "event", "preference", "recommendation", "milestone",
}


async def extract_structured(
    text: str,
    title: str | None = None,
    content_type: str | None = None,
) -> dict:
    """Extract facts and concepts from content.

    Args:
        text: Full content text
        title: Optional title for context
        content_type: Content type for prompt selection

    Returns:
        Dict with 'facts' (list[str]) and 'concepts' (list[dict])
    """
    truncated_text = text[:6000] if len(text) > 6000 else text

    # Select content-type-specific prompt or default
    prompt_template = _EXTRACT_PROMPTS.get(content_type or "", _DEFAULT_EXTRACT_PROMPT)
    prompt = prompt_template.format(
        title=title or "Untitled",
        text=truncated_text,
        max_facts=MAX_FACTS_PER_ITEM,
        max_concepts=MAX_CONCEPTS_PER_ITEM,
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

"""Single-call AI extraction for Second Brain captures.

Collapses what were up to four separate `claude -p` invocations per item
(extract_title / generate_summary / extract_topics / extract_structured)
into one JSON-returning call. Each subprocess spawn costs ~3-5s of OAuth
startup plus full system-prompt re-tokenisation, so one call instead of
four is a material saving per item in seed imports.

Falls back field-by-field to the existing keyword/snippet heuristics if
the combined response fails to parse.
"""

import json
import re
from typing import Optional

from logger import logger

from .config import (
    call_claude,
    MAX_FACTS_PER_ITEM,
    MAX_CONCEPTS_PER_ITEM,
)
from .extract_structured import (
    CONCEPT_TYPES,
    _validate_facts,
    _validate_concepts,
)
from .summarise import _fallback_summary
from .tag import (
    _fallback_topics,
    _filter_noise_tags,
    _format_tag_groups,
    _normalize_tag,
)


COMBINED_PROMPT = """You are preparing a knowledge item for a personal second brain. In one pass, produce a JSON object describing this content. Return ONLY the JSON object, no prose, no markdown fences.

Schema:
{{
  "title": "short descriptive title, 5-10 words{title_rule}",
  "summary": "2-3 sentence summary. Be specific — include numbers, names, dates where relevant.",
  "topics": ["3-8 lowercase hyphenated tags describing SUBJECT MATTER, not format. Never use: email, general, calendar, untagged, claude-history, note, conversation, document, bookmark, url. Prefer known domain tags below when they match."],
  "facts": ["up to {max_facts} concrete factual statements (dates, numbers, decisions, names, amounts). Each a standalone sentence. Empty array if content is trivial."],
  "concepts": [{{"label": "short name", "type": "one of: how-it-works | why-it-exists | gotcha | pattern | trade-off | decision | metric | event | preference | recommendation | milestone", "detail": "one sentence"}}]
}}

Content type: {content_type}

Known domain tags by category:
{tag_groups}

Title: {title}
Content:
{text}"""


async def extract_all_ai(
    text: str,
    title: Optional[str],
    content_type: str,
    needs_title: bool,
    needs_structured: bool = True,
) -> dict:
    """One Claude call that returns title/summary/topics/facts/concepts.

    Returns a dict with keys: summary, topics, facts, concepts, and optionally title.
    Always returns valid values — falls back to heuristics on parse failure.
    """
    truncated = text[:6000] if len(text) > 6000 else text
    title_rule = "" if needs_title else " (keep the given title, do not change it)"

    prompt = COMBINED_PROMPT.format(
        title=title or "Untitled",
        text=truncated,
        content_type=content_type or "unknown",
        tag_groups=_format_tag_groups(),
        max_facts=MAX_FACTS_PER_ITEM,
        title_rule=title_rule,
    )

    # 800 tokens comfortably covers title + summary + 8 tags + 12 facts + 5 concepts.
    result = await call_claude(prompt, max_tokens=800, timeout=45)
    if not result:
        return _fallback_all(text, title, content_type, needs_title, needs_structured)

    parsed = _parse_combined_response(result)
    if parsed is None:
        logger.warning("Combined AI response was not valid JSON, using fallbacks")
        return _fallback_all(text, title, content_type, needs_title, needs_structured)

    raw_topics = parsed.get("topics") or []
    topics = [
        _normalize_tag(t)
        for t in raw_topics
        if isinstance(t, str) and t.strip()
    ]
    topics = _filter_noise_tags(topics)[:8]
    if not topics:
        topics = _fallback_topics(text, title, content_type)

    summary = parsed.get("summary")
    if not isinstance(summary, str) or len(summary.strip()) < 5:
        summary = _fallback_summary(text)

    out = {
        "summary": summary.strip(),
        "topics": topics,
        "facts": _validate_facts(parsed.get("facts", [])) if needs_structured else [],
        "concepts": _validate_concepts(parsed.get("concepts", [])) if needs_structured else [],
    }

    if needs_title:
        raw_title = parsed.get("title") or ""
        if isinstance(raw_title, str) and 5 <= len(raw_title.strip()) <= 200:
            out["title"] = raw_title.strip().strip('"\'')
        else:
            out["title"] = _fallback_title(text, title)

    return out


def _parse_combined_response(response: str) -> Optional[dict]:
    """Extract the JSON object from a Claude response."""
    s = response.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)

    match = re.search(r"\{.*\}", s, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _fallback_title(text: str, title: Optional[str]) -> str:
    if title and len(title) >= 5:
        return title
    first_line = text.split("\n", 1)[0].strip()
    if 10 <= len(first_line) <= 100:
        return first_line
    words = text.split()[:10]
    return " ".join(words) + ("..." if len(text.split()) > 10 else "")


def _fallback_all(
    text: str,
    title: Optional[str],
    content_type: str,
    needs_title: bool,
    needs_structured: bool,
) -> dict:
    out = {
        "summary": _fallback_summary(text),
        "topics": _fallback_topics(text, title, content_type),
        "facts": [],
        "concepts": [],
    }
    if needs_title:
        out["title"] = _fallback_title(text, title)
    return out


def should_skip_ai(text: str) -> bool:
    """Return True for content too short/trivial to justify a Claude call.

    Threshold picked so that typical shipping notifications, booking stubs,
    and short calendar descriptions bypass the AI path — keyword fallbacks
    give us good-enough topics, and the text itself is already a summary.
    """
    stripped = text.strip()
    if len(stripped) < 300:
        return True
    if len(stripped.split()) < 40:
        return True
    return False

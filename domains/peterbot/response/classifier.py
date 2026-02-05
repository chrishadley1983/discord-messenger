"""Classifier - Stage 2 of the Response Processing Pipeline.

Examines sanitised output and assigns a response type that determines formatting.
Based on RESPONSE.md Section 4.
"""

import re
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ResponseType(Enum):
    """Response types for formatter routing (Section 4.1)."""
    # Primary types
    CONVERSATIONAL = 'conversational'      # Natural language chat
    DATA_TABLE = 'data_table'              # Tabular/structured data
    CODE = 'code'                          # Code snippets or technical output
    SEARCH_RESULTS = 'search_results'      # Web search results
    NEWS_RESULTS = 'news_results'          # News search results
    IMAGE_RESULTS = 'image_results'        # Image search results
    LOCAL_RESULTS = 'local_results'        # Local business/place search
    LIST = 'list'                          # Ordered or unordered lists
    SCHEDULE = 'schedule'                  # Calendar/reminder/schedule info
    ERROR = 'error'                        # Error messages
    MIXED = 'mixed'                        # Contains multiple types

    # Special types
    LONG_RUNNING_ACK = 'long_running_ack'  # Intermediate "working on it" messages
    PROACTIVE = 'proactive'                # Peter-initiated messages

    # Nutrition-specific (Peter's common use case)
    NUTRITION_SUMMARY = 'nutrition_summary'
    NUTRITION_LOG = 'nutrition_log'
    WATER_LOG = 'water_log'


@dataclass
class ClassificationSignals:
    """Signals extracted from text for classification (Section 4.2)."""
    # Structural signals
    has_markdown_table: bool = False
    has_code_block: bool = False
    has_json_block: bool = False
    has_url_list: bool = False
    has_bullet_list: bool = False
    has_numbered_list: bool = False

    # Content signals
    brave_search_detected: bool = False
    news_indicators: bool = False
    image_indicators: bool = False
    local_indicators: bool = False
    schedule_terms: bool = False
    error_patterns: bool = False
    nutrition_indicators: bool = False
    water_indicators: bool = False

    # Length signals
    char_count: int = 0
    line_count: int = 0
    code_to_prose_ratio: float = 0.0


def extract_signals(text: str) -> ClassificationSignals:
    """Analyse text to extract classification signals."""
    signals = ClassificationSignals()

    if not text:
        return signals

    signals.char_count = len(text)
    signals.line_count = text.count('\n') + 1

    # Markdown table detection (| col | col | pattern with header separator)
    signals.has_markdown_table = bool(re.search(
        r'\|[^|]+\|[^|]+\|.*\n\s*\|[-:]+\|[-:]+\|',
        text
    ))

    # Code block detection
    code_blocks = re.findall(r'```[\s\S]*?```', text)
    signals.has_code_block = len(code_blocks) > 0

    # Calculate code to prose ratio
    if signals.has_code_block:
        code_chars = sum(len(block) for block in code_blocks)
        signals.code_to_prose_ratio = code_chars / signals.char_count if signals.char_count > 0 else 0

    # JSON block detection
    signals.has_json_block = bool(re.search(r'```json|^\s*[\[{]', text, re.MULTILINE))

    # Check if text is pure JSON
    try:
        stripped = text.strip()
        if stripped.startswith(('{', '[')):
            json.loads(stripped)
            signals.has_json_block = True
    except (json.JSONDecodeError, ValueError):
        pass

    # URL list detection (multiple URLs in sequence)
    urls = re.findall(r'https?://[^\s<>\])"\']+', text)
    signals.has_url_list = len(urls) >= 3

    # Bullet list detection
    signals.has_bullet_list = bool(re.search(r'^[\s]*[-*•]\s+\S', text, re.MULTILINE))

    # Numbered list detection
    signals.has_numbered_list = bool(re.search(r'^\s*\d+\.\s+\S', text, re.MULTILINE))

    # Brave search detection (search result patterns)
    search_patterns = [
        r'\*\*\d+\.\s+\[',  # **1. [Title](url)
        r'🔍\s*(Web\s*)?Search',
        r'search results?',
        r'found \d+ results?',
    ]
    signals.brave_search_detected = any(
        re.search(p, text, re.IGNORECASE) for p in search_patterns
    )

    # News indicators
    news_patterns = [
        r'📰\s*News',
        r'news results?',
        r'hours?\s+ago|minutes?\s+ago|days?\s+ago',
        r'published|posted',
    ]
    signals.news_indicators = any(
        re.search(p, text, re.IGNORECASE) for p in news_patterns
    )

    # Image indicators
    image_patterns = [
        r'🖼️|📷|🎨',
        r'image results?',
        r'\.(jpg|jpeg|png|gif|webp)\b',
    ]
    signals.image_indicators = any(
        re.search(p, text, re.IGNORECASE) for p in image_patterns
    )

    # Local/place indicators
    local_patterns = [
        r'📍\s*Local',
        r'local results?',
        r'⭐+\s*\d',  # Star ratings
        r'(?:phone|address|rating|reviews?)',
    ]
    signals.local_indicators = any(
        re.search(p, text, re.IGNORECASE) for p in local_patterns
    )

    # Schedule/time indicators
    schedule_patterns = [
        r'📅|⏰|🗓️',
        r'calendar|schedule|meeting|appointment|reminder',
        r'\d{1,2}:\d{2}\s*(?:am|pm)?',
        r'tomorrow|today|next week|on \w+day',
        r'<t:\d+:[FfDdTtR]>',  # Discord timestamps
    ]
    signals.schedule_terms = any(
        re.search(p, text, re.IGNORECASE) for p in schedule_patterns
    )

    # Error patterns
    error_patterns = [
        r'(?:error|exception|failed|failure)',
        r'⚠️|❌|🚫',
        r'traceback|stack trace',
        r'could not|unable to|cannot',
    ]
    signals.error_patterns = any(
        re.search(p, text, re.IGNORECASE) for p in error_patterns
    )

    # Nutrition indicators
    nutrition_patterns = [
        r'🍎|🍽️|📊.*(?:Calories|Protein|Carbs|Fat)',
        r'(?:calories?|protein|carbs?|fat)\s*:?\s*\d+',
        r'nutrition|macros?',
        r'💪.*(?:protein|g\b)',
        r'🍞.*(?:carbs?|g\b)',
        r'🧈.*(?:fat|g\b)',
    ]
    signals.nutrition_indicators = any(
        re.search(p, text, re.IGNORECASE) for p in nutrition_patterns
    )

    # Water indicators
    water_patterns = [
        r'💧',
        r'\d+\s*ml\s*water',
        r'water.*progress|logged.*water|hydration',
    ]
    signals.water_indicators = any(
        re.search(p, text, re.IGNORECASE) for p in water_patterns
    )

    return signals


def classify(text: str, context: Optional[dict] = None) -> ResponseType:
    """Classify response type using priority order from Section 4.3.

    Args:
        text: Sanitised response text
        context: Optional context (user_prompt, channel, etc.)

    Returns:
        ResponseType for formatter routing
    """
    if not text:
        return ResponseType.CONVERSATIONAL

    signals = extract_signals(text)
    context = context or {}

    # Check for proactive message markers
    if context.get('is_proactive'):
        return ResponseType.PROACTIVE

    # Check for long-running ack
    if context.get('is_ack'):
        return ResponseType.LONG_RUNNING_ACK

    # Priority 1: Nutrition-specific (Peter's common case)
    if signals.water_indicators and 'ml' in text.lower():
        return ResponseType.WATER_LOG

    if signals.nutrition_indicators:
        if re.search(r"today'?s\s+(?:nutrition|meals?)", text, re.IGNORECASE):
            return ResponseType.NUTRITION_SUMMARY
        if re.search(r'logged|☕|🥗|🍝|🥣', text):
            return ResponseType.NUTRITION_LOG

    # Priority 2: Search results (Brave API)
    if signals.brave_search_detected or signals.has_url_list:
        if signals.news_indicators:
            return ResponseType.NEWS_RESULTS
        if signals.image_indicators:
            return ResponseType.IMAGE_RESULTS
        if signals.local_indicators:
            return ResponseType.LOCAL_RESULTS
        return ResponseType.SEARCH_RESULTS

    # Priority 3: JSON/Code heavy content
    if signals.has_json_block and signals.code_to_prose_ratio > 0.7:
        return ResponseType.CODE

    # Priority 4: Markdown table
    if signals.has_markdown_table:
        # Check if there's substantial prose alongside the table
        # If mostly table content, it's DATA_TABLE
        # If table embedded in prose, it's MIXED
        table_lines = len(re.findall(r'^\|.*\|', text, re.MULTILINE))
        total_lines = signals.line_count
        table_ratio = table_lines / total_lines if total_lines > 0 else 0

        if table_ratio > 0.4:  # More than 40% is table
            return ResponseType.DATA_TABLE
        return ResponseType.MIXED

    # Priority 5: Code blocks
    if signals.has_code_block and signals.code_to_prose_ratio > 0.5:
        return ResponseType.CODE

    # Priority 6: Schedule/calendar
    if signals.schedule_terms:
        # Check if it's actually schedule data vs just mentioning time
        schedule_data_patterns = [
            r'📅|⏰|🗓️',
            r'(?:meeting|appointment|event)\s*(?:at|:)',
            r'<t:\d+:',
        ]
        if any(re.search(p, text) for p in schedule_data_patterns):
            return ResponseType.SCHEDULE

    # Priority 7: Error messages
    if signals.error_patterns:
        # Check it's actually an error, not just a warning emoji
        # ⚠️ alone is NOT enough - many valid responses use it (low balance, alerts)
        # Need actual error keywords paired with the emoji
        error_confirm_patterns = [
            r'error:',
            r'failed:',
            r'exception:',
            r'traceback',
            r'❌\s*(?:error|failed|could not)',
            r'⚠️\s*(?:error|failed|exception)',
        ]
        if any(re.search(p, text, re.IGNORECASE) for p in error_confirm_patterns):
            return ResponseType.ERROR

    # Priority 8: Lists (4+ items)
    if signals.has_bullet_list or signals.has_numbered_list:
        # Count list items
        bullet_items = len(re.findall(r'^[\s]*[-*•]\s+\S', text, re.MULTILINE))
        numbered_items = len(re.findall(r'^\s*\d+\.\s+\S', text, re.MULTILINE))
        if bullet_items >= 4 or numbered_items >= 4:
            return ResponseType.LIST

    # Priority 9: Multiple types detected
    type_indicators = sum([
        signals.has_code_block,
        signals.has_markdown_table,
        signals.has_bullet_list or signals.has_numbered_list,
        signals.has_url_list,
    ])
    if type_indicators >= 2:
        return ResponseType.MIXED

    # Default: Conversational
    return ResponseType.CONVERSATIONAL


def get_classification_confidence(text: str, assigned_type: ResponseType) -> float:
    """Calculate confidence score for classification.

    Returns value 0.0 to 1.0 indicating classification confidence.
    """
    signals = extract_signals(text)

    # High confidence indicators by type
    confidence_map = {
        ResponseType.WATER_LOG: signals.water_indicators,
        ResponseType.NUTRITION_SUMMARY: signals.nutrition_indicators,
        ResponseType.NUTRITION_LOG: signals.nutrition_indicators,
        ResponseType.SEARCH_RESULTS: signals.brave_search_detected,
        ResponseType.NEWS_RESULTS: signals.news_indicators,
        ResponseType.LOCAL_RESULTS: signals.local_indicators,
        ResponseType.CODE: signals.code_to_prose_ratio > 0.5,
        ResponseType.DATA_TABLE: signals.has_markdown_table,
        ResponseType.ERROR: signals.error_patterns,
        ResponseType.SCHEDULE: signals.schedule_terms,
        ResponseType.LIST: signals.has_bullet_list or signals.has_numbered_list,
    }

    if assigned_type in confidence_map:
        return 0.9 if confidence_map[assigned_type] else 0.5

    # Conversational is default - medium confidence
    if assigned_type == ResponseType.CONVERSATIONAL:
        # Higher confidence if no special patterns detected
        special_patterns = sum([
            signals.has_markdown_table,
            signals.has_code_block,
            signals.has_json_block,
            signals.brave_search_detected,
            signals.nutrition_indicators,
        ])
        return 0.9 if special_patterns == 0 else 0.6

    return 0.5


# =============================================================================
# TESTING
# =============================================================================

def test_classifier():
    """Run basic classifier tests."""
    test_cases = [
        # Conversational
        ("How's it going? Just wanted to check in.", ResponseType.CONVERSATIONAL),

        # Water log
        ("💧 Logged 500ml\n\n**Progress:** 2,250ml / 3,500ml (64%)", ResponseType.WATER_LOG),

        # Nutrition summary
        ("**Today's Nutrition** 🍎\n\n📊 **Calories:** 1,786 / 2,100", ResponseType.NUTRITION_SUMMARY),

        # Code
        ("```python\ndef hello():\n    print('world')\n```", ResponseType.CODE),

        # Search results
        ("🔍 Web Search\n\n**1. [Result](https://example.com)**\n**2. [Result2](https://example2.com)**", ResponseType.SEARCH_RESULTS),

        # Error
        ("⚠️ Error: Could not connect to database", ResponseType.ERROR),

        # List
        ("Here are the options:\n- Option 1\n- Option 2\n- Option 3\n- Option 4\n- Option 5", ResponseType.LIST),

        # Schedule
        ("📅 **Tomorrow's Schedule**\n\n⏰ 9:00am - Team standup\n⏰ 2:00pm - Client call", ResponseType.SCHEDULE),

        # Data table (with markdown table)
        ("| Name | Price |\n|------|-------|\n| Item1 | $10 |", ResponseType.DATA_TABLE),
    ]

    passed = 0
    failed = 0

    for text, expected_type in test_cases:
        result = classify(text)
        confidence = get_classification_confidence(text, result)

        if result == expected_type:
            passed += 1
            print(f"✓ PASS - {expected_type.value} (confidence: {confidence:.2f})")
        else:
            failed += 1
            print(f"✗ FAIL - Expected {expected_type.value}, got {result.value}")
            print(f"  Text: {text[:50]}...")

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == '__main__':
    test_classifier()

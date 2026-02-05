"""Response Processing Pipeline - Main orchestrator.

Transforms raw Claude Code output into clean Discord messages through 5 stages:
1. Sanitiser - Strip CC artifacts
2. Classifier - Detect response type
3. Formatter - Apply Discord-native formatting
4. Chunker - Split into Discord-safe segments
5. Renderer - Produce final Discord message objects

Based on RESPONSE.md Architecture (Section 2).
"""

import re
from dataclasses import dataclass, field
from typing import Optional, Any

from .sanitiser import sanitise, check_bypass_flag, SanitiserResult
from .classifier import classify, ResponseType, ClassificationSignals, extract_signals
from .chunker import chunk, ChunkerConfig
from .formatters.conversational import format_conversational, strip_trailing_meta
from .formatters.table import format_table
from .formatters.search import (
    format_search_results,
    format_news_results,
    format_image_results,
    format_local_results,
)
from .formatters.code import format_code
from .formatters.nutrition import (
    format_nutrition_summary,
    format_nutrition_log,
    format_water_log,
)
from .formatters.proactive import format_morning_briefing, format_reminder, format_alert
from .formatters.error import format_error
from .formatters.schedule import format_schedule
from .formatters.list_formatter import format_list


@dataclass
class ProcessedResponse:
    """Result of processing a response through the pipeline."""
    # Final output
    content: str
    chunks: list[str]

    # Embed data (if applicable)
    embed: Optional[dict] = None
    embeds: list[dict] = field(default_factory=list)

    # Reactions to add (for alerts)
    reactions: list[str] = field(default_factory=list)

    # Metadata
    response_type: ResponseType = ResponseType.CONVERSATIONAL
    sanitiser_log: list[str] = field(default_factory=list)
    signals: Optional[ClassificationSignals] = None

    # Debug info
    raw_length: int = 0
    final_length: int = 0
    was_bypassed: bool = False


@dataclass
class PipelineContext:
    """Context passed through pipeline stages."""
    user_prompt: str = ''
    channel: str = 'discord'
    is_proactive: bool = False
    is_ack: bool = False
    max_items: int = 10
    show_code: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> 'PipelineContext':
        return cls(
            user_prompt=data.get('user_prompt', data.get('userPrompt', '')),
            channel=data.get('channel', 'discord'),
            is_proactive=data.get('is_proactive', data.get('isProactive', False)),
            is_ack=data.get('is_ack', data.get('isAck', False)),
            max_items=data.get('max_items', data.get('maxItems', 10)),
            show_code=data.get('show_code', data.get('showCode', False)),
        )


# Formatter routing table
FORMATTERS = {
    ResponseType.CONVERSATIONAL: format_conversational,
    ResponseType.DATA_TABLE: format_table,
    ResponseType.CODE: format_code,
    ResponseType.SEARCH_RESULTS: format_search_results,
    ResponseType.NEWS_RESULTS: format_news_results,
    ResponseType.IMAGE_RESULTS: format_image_results,
    ResponseType.LOCAL_RESULTS: format_local_results,
    ResponseType.LIST: format_list,
    ResponseType.SCHEDULE: format_schedule,
    ResponseType.ERROR: format_error,
    ResponseType.NUTRITION_SUMMARY: format_nutrition_summary,
    ResponseType.NUTRITION_LOG: format_nutrition_log,
    ResponseType.WATER_LOG: format_water_log,
}


def process(
    raw_cc_output: str,
    context: Optional[dict] = None
) -> ProcessedResponse:
    """Process raw Claude Code output through the full pipeline.

    Args:
        raw_cc_output: Raw string output from Claude Code
        context: Optional context dict with user_prompt, channel, etc.

    Returns:
        ProcessedResponse with formatted content ready for Discord
    """
    if not raw_cc_output:
        return ProcessedResponse(
            content='',
            chunks=[],
            response_type=ResponseType.CONVERSATIONAL
        )

    ctx = PipelineContext.from_dict(context or {})
    raw_length = len(raw_cc_output)

    # Stage 0: Check for --raw bypass
    if check_bypass_flag(ctx.user_prompt):
        bypassed_content = f"```\n{raw_cc_output}\n```"
        return ProcessedResponse(
            content=bypassed_content,
            chunks=[bypassed_content],
            response_type=ResponseType.CONVERSATIONAL,
            raw_length=raw_length,
            final_length=len(bypassed_content),
            was_bypassed=True
        )

    # Stage 1: Sanitise
    sanitiser_result = sanitise(raw_cc_output, track_rules=True)
    if isinstance(sanitiser_result, SanitiserResult):
        sanitised = sanitiser_result.content
        sanitiser_log = sanitiser_result.rules_applied
    else:
        sanitised = sanitiser_result
        sanitiser_log = []

    # Stage 2: Classify
    signals = extract_signals(sanitised)
    response_type = classify(sanitised, {
        'is_proactive': ctx.is_proactive,
        'is_ack': ctx.is_ack,
    })

    # Stage 3: Format
    formatted = apply_formatter(sanitised, response_type, ctx)

    # Apply trailing meta stripping to all text responses
    if isinstance(formatted, str):
        formatted = strip_trailing_meta(formatted)

    # Handle formatter results that include embeds
    embed = None
    embeds = []
    reactions = []

    if isinstance(formatted, dict):
        if 'content' in formatted:
            content = formatted['content'] or ''
        else:
            content = sanitised

        if 'embed' in formatted:
            embed = formatted['embed']
        if 'embeds' in formatted:
            embeds = formatted['embeds']
        if 'reactions' in formatted:
            reactions = formatted['reactions']
    elif isinstance(formatted, list):
        # Multiple embeds (e.g., images)
        content = ''
        embeds = formatted
    else:
        content = formatted

    # Stage 4: Chunk
    if content:
        chunks = chunk(content)
    else:
        chunks = ['']

    # Stage 5: Render (produce final structure)
    final_content = chunks[0] if chunks else ''

    return ProcessedResponse(
        content=final_content,
        chunks=chunks,
        embed=embed,
        embeds=embeds,
        reactions=reactions,
        response_type=response_type,
        sanitiser_log=sanitiser_log,
        signals=signals,
        raw_length=raw_length,
        final_length=len(final_content),
    )


def apply_formatter(
    text: str,
    response_type: ResponseType,
    ctx: PipelineContext
) -> Any:
    """Apply the appropriate formatter based on response type."""
    formatter = FORMATTERS.get(response_type)

    if formatter:
        context_dict = {
            'user_prompt': ctx.user_prompt,
            'max_items': ctx.max_items,
            'show_code': ctx.show_code,
        }
        try:
            return formatter(text, context_dict)
        except Exception as e:
            # Fall back to conversational on formatter error
            return format_conversational(text, context_dict)

    # Handle special types
    if response_type == ResponseType.MIXED:
        return format_mixed(text, ctx)

    if response_type == ResponseType.PROACTIVE:
        return text  # Proactive messages are pre-formatted

    if response_type == ResponseType.LONG_RUNNING_ACK:
        return text  # Acks are pre-formatted

    # Default to conversational
    return format_conversational(text, {'user_prompt': ctx.user_prompt})


def format_mixed(text: str, ctx: PipelineContext) -> str:
    """Handle mixed content by formatting segments individually."""
    # Split into segments and format each
    segments = split_into_segments(text)
    formatted_segments = []

    for segment in segments:
        seg_type = classify(segment)
        formatter = FORMATTERS.get(seg_type, format_conversational)
        try:
            result = formatter(segment, {'user_prompt': ctx.user_prompt})
            if isinstance(result, dict):
                result = result.get('content', segment)
            formatted_segments.append(result)
        except Exception:
            formatted_segments.append(segment)

    return '\n\n'.join(formatted_segments)


def split_into_segments(text: str) -> list[str]:
    """Split mixed content into segments for individual formatting."""
    segments = []
    current = []

    lines = text.split('\n')

    for line in lines:
        # Detect segment boundaries
        is_code_fence = line.strip().startswith('```')
        is_table_start = bool(re.match(r'^\|[^|]+\|', line))
        is_list_item = bool(re.match(r'^[\s]*[-*]\s|^\s*\d+\.\s', line))
        is_blank = not line.strip()

        # Start new segment on significant boundary
        if is_code_fence or is_table_start:
            if current:
                segments.append('\n'.join(current))
                current = []

        current.append(line)

        # End segment after code block closes
        if is_code_fence and len(current) > 1 and current[0].strip().startswith('```'):
            segments.append('\n'.join(current))
            current = []

    if current:
        segments.append('\n'.join(current))

    # Filter empty segments
    return [s.strip() for s in segments if s.strip()]


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def process_simple(raw_text: str, user_prompt: str = '') -> str:
    """Simple interface - just get the formatted content string."""
    result = process(raw_text, {'user_prompt': user_prompt})
    return result.content


def process_for_discord(raw_text: str, user_prompt: str = '') -> dict:
    """Process and return Discord-ready dict with content and embeds."""
    result = process(raw_text, {'user_prompt': user_prompt})

    output = {
        'content': result.content,
        'chunks': result.chunks,
    }

    if result.embed:
        output['embed'] = result.embed
    if result.embeds:
        output['embeds'] = result.embeds
    if result.reactions:
        output['reactions'] = result.reactions

    return output


# =============================================================================
# TESTING
# =============================================================================

def test_pipeline():
    """Run comprehensive pipeline tests."""
    print("=" * 60)
    print("RESPONSE PIPELINE TEST SUITE")
    print("=" * 60)

    test_cases = [
        # Basic conversational
        {
            'name': 'Basic conversational',
            'input': 'Hello! How can I help you today?',
            'expected_type': ResponseType.CONVERSATIONAL,
            'checks': ['no_artifacts', 'no_embed'],
        },

        # CC artifact removal
        {
            'name': 'CC artifact removal',
            'input': '⏺ First point\n\nHere is the answer.\n\nTotal tokens: 1,247',
            'expected_type': ResponseType.CONVERSATIONAL,
            'checks': ['no_artifacts', 'has_content'],
        },

        # Water log
        {
            'name': 'Water log',
            'input': '💧 Logged 500ml\n\n**Progress:** 2,250ml / 3,500ml (64%)\n1,250ml to go!',
            'expected_type': ResponseType.WATER_LOG,
            'checks': ['has_emoji', 'has_progress'],
        },

        # Nutrition summary
        {
            'name': 'Nutrition summary',
            'input': "**Today's Nutrition** 🍎\n\n📊 **Calories:** 1,786 / 2,100 (85%)\n💪 **Protein:** 140g / 160g",
            'expected_type': ResponseType.NUTRITION_SUMMARY,
            'checks': ['has_emoji', 'has_numbers'],
        },

        # Code block (default: summarise)
        {
            'name': 'Code default (summarise)',
            'input': "Here's the solution:\n```python\ndef hello():\n    print('world')\n```\nThis should work.",
            'expected_type': ResponseType.CODE,
            'checks': ['has_content'],
        },

        # Search results
        {
            'name': 'Search results',
            'input': '🔍 Web Search\n\n**1. [Result](https://example.com)**\nSnippet here',
            'expected_type': ResponseType.SEARCH_RESULTS,
            'checks': ['has_embed_or_content'],
        },

        # Error message
        {
            'name': 'Error message',
            'input': '⚠️ Error: Could not connect to database\n\nTraceback:\n  File "app.py"',
            'expected_type': ResponseType.ERROR,
            'checks': ['has_warning'],
        },

        # List
        {
            'name': 'List formatting',
            'input': 'Here are the options:\n- Option 1\n- Option 2\n- Option 3\n- Option 4\n- Option 5',
            'expected_type': ResponseType.LIST,
            'checks': ['has_list'],
        },

        # --raw bypass
        {
            'name': '--raw bypass',
            'input': '⏺ Raw content with artifacts',
            'context': {'user_prompt': 'show me --raw'},
            'expected_type': ResponseType.CONVERSATIONAL,
            'checks': ['is_code_block', 'has_artifacts'],
        },

        # ANSI code removal
        {
            'name': 'ANSI code removal',
            'input': '\x1b[32mgreen text\x1b[0m normal text',
            'expected_type': ResponseType.CONVERSATIONAL,
            'checks': ['no_ansi'],
        },

        # Long response chunking
        {
            'name': 'Long response chunking',
            'input': 'A' * 2500,
            'expected_type': ResponseType.CONVERSATIONAL,
            'checks': ['multiple_chunks'],
        },

        # Markdown table conversion
        {
            'name': 'Markdown table conversion',
            'input': '| Name | Value |\n|------|-------|\n| Foo  | 10    |',
            'expected_type': ResponseType.DATA_TABLE,
            'checks': ['no_raw_table'],
        },
    ]

    passed = 0
    failed = 0

    for test in test_cases:
        name = test['name']
        input_text = test['input']
        expected_type = test['expected_type']
        context = test.get('context', {})
        checks = test.get('checks', [])

        try:
            result = process(input_text, context)

            # Check type
            type_match = result.response_type == expected_type

            # Run checks
            check_results = []
            for check in checks:
                check_results.append(run_check(check, result, input_text))

            all_passed = type_match and all(check_results)

            if all_passed:
                passed += 1
                print(f"[PASS] {name}")
            else:
                failed += 1
                print(f"[FAIL] {name}")
                if not type_match:
                    print(f"    Expected type: {expected_type.value}, got: {result.response_type.value}")
                for i, (check, check_passed) in enumerate(zip(checks, check_results)):
                    if not check_passed:
                        print(f"    Check failed: {check}")

        except Exception as e:
            failed += 1
            print(f"[ERROR] {name} - {str(e)}")

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


def run_check(check: str, result: ProcessedResponse, original: str) -> bool:
    """Run a specific check on the result."""
    content = result.content

    checks = {
        'no_artifacts': lambda: not any(c in content for c in ['⏺', '⎿', 'Total tokens']),
        'no_embed': lambda: result.embed is None and not result.embeds,
        'has_content': lambda: len(content) > 0,
        'has_emoji': lambda: any(ord(c) > 127 for c in content),
        'has_progress': lambda: '/' in content and '%' in content,
        'has_numbers': lambda: any(c.isdigit() for c in content),
        'has_embed_or_content': lambda: result.embed is not None or len(content) > 0,
        'has_warning': lambda: '⚠️' in content or 'error' in content.lower(),
        'has_list': lambda: '-' in content or any(f'{i}.' in content for i in range(1, 10)),
        'is_code_block': lambda: content.startswith('```') and content.endswith('```'),
        'has_artifacts': lambda: '⏺' in content,
        'no_ansi': lambda: '\x1b[' not in content,
        'multiple_chunks': lambda: len(result.chunks) > 1,
        'no_raw_table': lambda: '|---' not in content.replace('```', ''),
    }

    if check in checks:
        return checks[check]()
    return True


if __name__ == '__main__':
    test_pipeline()

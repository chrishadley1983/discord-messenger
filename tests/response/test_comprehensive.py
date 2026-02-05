"""Comprehensive test suite for the Response Processing Pipeline.

Tests real-world scenarios across all response types to ensure
consistent, high-quality Discord output.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from domains.peterbot.response.pipeline import process, ProcessedResponse
from domains.peterbot.response.classifier import ResponseType
from domains.peterbot.response.sanitiser import sanitise, contains_cc_artifacts


# =============================================================================
# TEST FIXTURES - Real-world Claude Code output samples
# =============================================================================

CC_ARTIFACTS_SAMPLES = [
    # Session header with box drawing
    """╭────────────────────────────────────────╮
│ Session: peter-main (claude-4-sonnet)  │
╰────────────────────────────────────────╯

Here is the actual response content.""",

    # Bullet markers and tool indicators
    """⏺ Let me check that for you.

  mcp__gcal__list_events

⏺ Your next meeting is at 2:00 PM today.""",

    # Token counts and costs
    """The weather in Tonbridge is 8°C and partly cloudy.

Total tokens: 1,247 | Cost: $0.003
Input: 892 | Output: 355""",

    # ANSI color codes
    """\x1b[32mSuccess!\x1b[0m The file has been updated.
\x1b[1mBold text\x1b[0m and normal text.""",

    # Thinking status messages
    """Thinking for 5 seconds...

Here is the answer to your question.""",

    # Mixed artifacts
    """⏺ Searching for LEGO prices...

  brave_web_search: "LEGO 42100 eBay UK price"

⏺ Based on the search, prices range from £380-£450.

Total tokens: 2,341 | Cost: $0.007"""
]

NUTRITION_SAMPLES = [
    # Water log
    """💧 Logged 500ml

**Progress:** 2,250ml / 3,500ml (64%)
1,250ml to go - keep sipping!""",

    # Nutrition summary
    """**Today's Nutrition** 🍎

📊 **Calories:** 1,786 / 2,100 (85%)
💪 **Protein:** 140g / 160g (87%)
🍞 **Carbs:** 153g / 263g (58%)
🧈 **Fat:** 68g / 70g (97%)
💧 **Water:** 2,250ml / 3,500ml (64%)

Room for ~300 more cals. Something with 20g protein would nail your target!""",

    # Meal log
    """**Today's Meals** 🍽️

☕ **Breakfast** (8:45am) - Protein bar - 194 cals, 8g protein
☕ **Breakfast** (9:05am) - Flat white - 44 cals
🥗 **Lunch** (12:57pm) - Chicken skewers & eggs - 734 cals, 67g protein
🍝 **Dinner** (6:20pm) - Gammon pasta - 507 cals, 32g protein
🥣 **Snack** (8:04pm) - Protein granola - 307 cals, 29g protein""",

    # Water with running total (from API)
    """Logged 500ml water.

Today's total: 2,750ml / 3,500ml (79%)
750ml remaining to hit your target.""",
]

SEARCH_SAMPLES = [
    # Web search results
    """Based on my search, LEGO 42100 is going for around £380-£450 on eBay UK.

🔍 Web Search

**1. [LEGO Technic 42100 Liebherr](https://ebay.co.uk/itm/123)**
New sealed, £399 with free postage

**2. [LEGO 42100 Excavator](https://ebay.co.uk/itm/456)**
Open box, £320 collection only

**3. [Liebherr R 9800 LEGO](https://amazon.co.uk/dp/789)**
£445 Prime delivery""",

    # News results
    """📰 News

**[LEGO announces 2026 Technic lineup](https://news.lego.com/2026)**
LEGO Group - 2 hours ago
New Technic sets revealed including updated Liebherr excavator

**[Brick prices surge amid collector demand](https://brickfanatics.com/prices)**
Brick Fanatics - 5 hours ago
Retired sets seeing 40% price increases""",

    # Local results
    """📍 Local Results

**LEGO Store Bluewater** ⭐⭐⭐⭐
Bluewater Shopping Centre, Dartford
📞 01234 567890

**Smyths Toys Tunbridge Wells** ⭐⭐⭐⭐⭐
Royal Victoria Place
📞 01234 567891""",
]

CONVERSATIONAL_SAMPLES = [
    # Simple greeting
    "Hey! How's it going?",

    # Short answer
    "The capital of Japan is Tokyo.",

    # Medium response
    """That's a good question. Based on what you've told me about your running goals,
I'd suggest starting with 3 runs per week - maybe Tuesday, Thursday, and Saturday.
Keep the Tuesday and Thursday runs shorter (5K) and use Saturday for your longer run.

Build up gradually - don't increase distance by more than 10% per week.""",

    # Response with helpful advice (should NOT have trailing "let me know")
    """The half marathon is in 12 weeks, which gives you plenty of time to train.

Here's a simple plan:
- Weeks 1-4: Build base with 3 runs/week
- Weeks 5-8: Add tempo runs
- Weeks 9-11: Peak training
- Week 12: Taper

Let me know if you need a more detailed schedule!""",  # This should be stripped
]

CODE_SAMPLES = [
    # Code with explanation
    """Here's the solution:

```python
def calculate_pace(distance_km, time_minutes):
    pace = time_minutes / distance_km
    return f"{int(pace)}:{int((pace % 1) * 60):02d} min/km"
```

This function takes distance in km and time in minutes, then returns the pace as a formatted string.""",

    # Multiple code blocks
    """I've updated two files:

```python
# config.py
API_KEY = "your-key-here"
```

```python
# main.py
from config import API_KEY
```

Both changes are complete.""",

    # Technical output (should be summarized by default)
    """```json
{
    "status": "success",
    "data": {
        "calories": 1786,
        "protein_g": 140,
        "carbs_g": 153
    }
}
```""",
]

TABLE_SAMPLES = [
    # Simple comparison table
    """| Set | Price | Condition |
|-----|-------|-----------|
| 42100 | £399 | New |
| 42115 | £280 | Open box |
| 42083 | £450 | Sealed |""",

    # Table with surrounding text
    """Here's a comparison of the sets you mentioned:

| Set Number | Name | Price Range |
|------------|------|-------------|
| 42100 | Liebherr | £380-£450 |
| 42115 | Lamborghini | £250-£300 |
| 42143 | Ferrari | £340-£380 |

The 42100 has the best resale value historically.""",
]

ERROR_SAMPLES = [
    # Simple error
    "⚠️ Could not connect to the calendar service. Please try again later.",

    # Error with trace
    """⚠️ Error: Failed to fetch weather data

```
Traceback (most recent call last):
  File "weather.py", line 42
    requests.get(url)
ConnectionError: Connection refused
```""",

    # API error
    "⚠️ The Garmin API returned an error (429 Rate Limited). Try again in a few minutes.",
]

SCHEDULE_SAMPLES = [
    # Calendar events
    """📅 **Tomorrow's Schedule**

⏰ 9:30am - Team standup @ Zoom
⏰ 11:00am - Code review
⏰ 2:00pm - 1:1 with Sarah @ Coffee shop
⏰ 4:30pm - Gym session""",

    # Simple reminder
    """⏰ **Reminder**
Put the bins out - collection tomorrow morning.

-# Scheduled reminder""",
]


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def has_no_cc_artifacts(result: ProcessedResponse) -> bool:
    """Check response has no Claude Code artifacts."""
    return not contains_cc_artifacts(result.content)


def has_no_ansi_codes(result: ProcessedResponse) -> bool:
    """Check response has no ANSI escape codes."""
    return '\x1b[' not in result.content


def has_no_raw_markdown_table(result: ProcessedResponse) -> bool:
    """Check response has no raw markdown table syntax."""
    # Exclude content inside code blocks
    content = result.content
    # Remove code blocks for checking
    import re
    content_without_code = re.sub(r'```[\s\S]*?```', '', content)
    return '|---' not in content_without_code


def has_no_trailing_meta(result: ProcessedResponse) -> bool:
    """Check response has no trailing 'let me know' type phrases."""
    trailing_phrases = [
        'let me know',
        'hope this helps',
        'feel free to ask',
        'is there anything else',
    ]
    content_lower = result.content.lower()
    # Check last 100 chars
    end = content_lower[-100:] if len(content_lower) > 100 else content_lower
    return not any(phrase in end for phrase in trailing_phrases)


def is_under_discord_limit(result: ProcessedResponse) -> bool:
    """Check all chunks are under Discord's 2000 char limit."""
    return all(len(chunk) <= 2000 for chunk in result.chunks)


def has_proper_formatting(result: ProcessedResponse) -> bool:
    """Check response has Discord-appropriate formatting."""
    content = result.content

    # Should not have markdown headers in conversational
    if result.response_type == ResponseType.CONVERSATIONAL:
        import re
        if re.match(r'^#{1,3}\s', content, re.MULTILINE):
            return False

    return True


# =============================================================================
# TEST RUNNER
# =============================================================================

def run_comprehensive_tests():
    """Run all comprehensive tests."""
    print("=" * 70)
    print("COMPREHENSIVE RESPONSE PIPELINE TEST SUITE")
    print("=" * 70)

    all_results = []

    # Test CC artifact removal
    print("\n--- CC Artifact Removal Tests ---")
    for i, sample in enumerate(CC_ARTIFACTS_SAMPLES):
        result = process(sample)
        passed = has_no_cc_artifacts(result) and has_no_ansi_codes(result)
        all_results.append(('CC Artifacts', i + 1, passed, result))
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} Sample {i + 1}: {len(sample)} chars -> {len(result.content)} chars")
        if not passed:
            print(f"    Content preview: {result.content[:100]}...")

    # Test nutrition formatting
    print("\n--- Nutrition Formatting Tests ---")
    for i, sample in enumerate(NUTRITION_SAMPLES):
        result = process(sample)
        # Check has nutrition emojis
        has_nutrition_emojis = any(e in result.content for e in ['💧', '🍎', '📊', '💪', '🍽️'])
        passed = has_nutrition_emojis and is_under_discord_limit(result)
        all_results.append(('Nutrition', i + 1, passed, result))
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} Sample {i + 1}: Type={result.response_type.value}")
        if not passed:
            print(f"    Missing emojis or over limit")

    # Test search result formatting
    print("\n--- Search Result Formatting Tests ---")
    for i, sample in enumerate(SEARCH_SAMPLES):
        result = process(sample)
        # Search results should have content and possibly embed
        passed = len(result.content) > 0 or result.embed is not None
        passed = passed and has_no_cc_artifacts(result)
        all_results.append(('Search', i + 1, passed, result))
        status = "[PASS]" if passed else "[FAIL]"
        has_embed = "Yes" if result.embed else "No"
        print(f"{status} Sample {i + 1}: Type={result.response_type.value}, Embed={has_embed}")

    # Test conversational formatting
    print("\n--- Conversational Formatting Tests ---")
    for i, sample in enumerate(CONVERSATIONAL_SAMPLES):
        result = process(sample)
        passed = (
            has_no_cc_artifacts(result) and
            has_proper_formatting(result) and
            is_under_discord_limit(result)
        )
        # Last sample has "let me know" - should be stripped
        if i == len(CONVERSATIONAL_SAMPLES) - 1:
            passed = passed and has_no_trailing_meta(result)
        all_results.append(('Conversational', i + 1, passed, result))
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} Sample {i + 1}: {len(result.content)} chars")
        if not passed and i == len(CONVERSATIONAL_SAMPLES) - 1:
            print(f"    May have trailing meta: {result.content[-50:]}")

    # Test code formatting
    print("\n--- Code Formatting Tests ---")
    for i, sample in enumerate(CODE_SAMPLES):
        result = process(sample)
        # Default should summarize (no code blocks unless explicitly requested)
        # or preserve code with explanation
        passed = has_no_cc_artifacts(result) and is_under_discord_limit(result)
        all_results.append(('Code', i + 1, passed, result))
        status = "[PASS]" if passed else "[FAIL]"
        has_code_block = '```' in result.content
        print(f"{status} Sample {i + 1}: Type={result.response_type.value}, HasCode={has_code_block}")

    # Test table formatting
    print("\n--- Table Formatting Tests ---")
    for i, sample in enumerate(TABLE_SAMPLES):
        result = process(sample)
        passed = has_no_raw_markdown_table(result) and is_under_discord_limit(result)
        all_results.append(('Table', i + 1, passed, result))
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} Sample {i + 1}: Type={result.response_type.value}")
        if not passed:
            print(f"    Still has raw table: |---| in output")

    # Test error formatting
    print("\n--- Error Formatting Tests ---")
    for i, sample in enumerate(ERROR_SAMPLES):
        result = process(sample)
        # Errors should have warning emoji
        has_warning = '⚠️' in result.content
        passed = has_warning and is_under_discord_limit(result)
        all_results.append(('Error', i + 1, passed, result))
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} Sample {i + 1}: Type={result.response_type.value}")

    # Test schedule formatting
    print("\n--- Schedule Formatting Tests ---")
    for i, sample in enumerate(SCHEDULE_SAMPLES):
        result = process(sample)
        # Schedule should have calendar/reminder emojis
        has_schedule_emojis = any(e in result.content for e in ['📅', '⏰', '🗓️'])
        passed = has_schedule_emojis and is_under_discord_limit(result)
        all_results.append(('Schedule', i + 1, passed, result))
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} Sample {i + 1}: Type={result.response_type.value}")

    # Summary
    print("\n" + "=" * 70)
    passed_count = sum(1 for r in all_results if r[2])
    total_count = len(all_results)
    print(f"TOTAL: {passed_count}/{total_count} tests passed ({100 * passed_count // total_count}%)")
    print("=" * 70)

    # Group by category
    categories = {}
    for category, num, passed, result in all_results:
        if category not in categories:
            categories[category] = {'passed': 0, 'total': 0}
        categories[category]['total'] += 1
        if passed:
            categories[category]['passed'] += 1

    print("\nBy Category:")
    for category, stats in categories.items():
        pct = 100 * stats['passed'] // stats['total'] if stats['total'] > 0 else 0
        print(f"  {category}: {stats['passed']}/{stats['total']} ({pct}%)")

    return passed_count == total_count


if __name__ == '__main__':
    success = run_comprehensive_tests()
    sys.exit(0 if success else 1)

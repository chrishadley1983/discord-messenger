"""Initialize parser fixtures database with seed data.

Run this once to set up the self-improving parser system.
"""

import sys
sys.path.insert(0, '.')

from domains.peterbot.capture_parser import get_parser_capture_store
from domains.peterbot.scheduled_output_scorer import create_format_spec

def seed_fixtures():
    """Create initial seed fixtures for testing."""
    store = get_parser_capture_store()

    print("Seeding parser fixtures...")

    # Category: simple_text (basic responses)
    store.add_fixture(
        raw_capture="Hello! How can I help you today?",
        expected_output="Hello! How can I help you today?",
        category="simple_text",
        source="seed",
        tags=["greeting", "simple"],
        difficulty="easy",
        notes="Basic greeting response - should pass through unchanged"
    )

    store.add_fixture(
        raw_capture="The weather in London is currently 12°C with cloudy skies.",
        expected_output="The weather in London is currently 12°C with cloudy skies.",
        category="simple_text",
        source="seed",
        tags=["weather", "simple"],
        difficulty="easy",
        notes="Simple weather response"
    )

    # Category: code_block (markdown code blocks)
    store.add_fixture(
        raw_capture="""Here's the code:
```python
def hello():
    print("Hello, World!")
```
This function prints a greeting.""",
        expected_output="""Here's the code:
```python
def hello():
    print("Hello, World!")
```
This function prints a greeting.""",
        category="code_block",
        source="seed",
        tags=["python", "code"],
        difficulty="normal",
        notes="Python code block should preserve formatting"
    )

    store.add_fixture(
        raw_capture="""Multiple code blocks:
```javascript
const x = 1;
```
And another:
```typescript
const y: number = 2;
```""",
        expected_output="""Multiple code blocks:
```javascript
const x = 1;
```
And another:
```typescript
const y: number = 2;
```""",
        category="code_block",
        source="seed",
        tags=["javascript", "typescript", "multiple"],
        difficulty="normal",
        notes="Multiple code blocks in one response"
    )

    # Category: markdown_formatting (tables, lists, bold, etc.)
    store.add_fixture(
        raw_capture="""**Health Summary**

| Metric | Value | Target |
|--------|-------|--------|
| Steps | 8,500 | 10,000 |
| Sleep | 7.2h | 8h |

Keep it up!""",
        expected_output="""**Health Summary**

| Metric | Value | Target |
|--------|-------|--------|
| Steps | 8,500 | 10,000 |
| Sleep | 7.2h | 8h |

Keep it up!""",
        category="markdown_formatting",
        source="seed",
        tags=["table", "health"],
        difficulty="normal",
        notes="Markdown table should be preserved"
    )

    store.add_fixture(
        raw_capture="""**To Do List:**

- [ ] Check emails
- [ ] Review calendar
- [x] Morning briefing

*Important items marked with checkbox*""",
        expected_output="""**To Do List:**

- [ ] Check emails
- [ ] Review calendar
- [x] Morning briefing

*Important items marked with checkbox*""",
        category="markdown_formatting",
        source="seed",
        tags=["list", "checkbox"],
        difficulty="normal",
        notes="Checkbox list formatting"
    )

    # Category: emoji_indicators (status emojis)
    store.add_fixture(
        raw_capture="""🌡️ Weather: 15°C, sunny
🚗 Traffic: Normal (25 mins)
📅 Events: 3 meetings
✅ All systems operational""",
        expected_output="""🌡️ Weather: 15°C, sunny
🚗 Traffic: Normal (25 mins)
📅 Events: 3 meetings
✅ All systems operational""",
        category="emoji_indicators",
        source="seed",
        tags=["emoji", "status"],
        difficulty="easy",
        notes="Emoji indicators should be preserved"
    )

    # Category: ansi_contaminated (should strip ANSI)
    store.add_fixture(
        raw_capture="\x1b[32mSuccess!\x1b[0m The operation completed.",
        expected_output="Success! The operation completed.",
        category="ansi_contaminated",
        source="seed",
        tags=["ansi", "cleanup"],
        difficulty="normal",
        notes="ANSI escape codes should be stripped"
    )

    store.add_fixture(
        raw_capture="\x1b[1;34mBlue bold text\x1b[0m and \x1b[31mred text\x1b[0m",
        expected_output="Blue bold text and red text",
        category="ansi_contaminated",
        source="seed",
        tags=["ansi", "multiple"],
        difficulty="hard",
        notes="Multiple ANSI sequences to strip"
    )

    # Category: spinner_noise (should remove spinners)
    store.add_fixture(
        raw_capture="⠋ Processing...\n⠙ Processing...\n⠹ Processing...\nDone! Here's your result.",
        expected_output="Done! Here's your result.",
        category="spinner_noise",
        source="seed",
        tags=["spinner", "cleanup"],
        difficulty="normal",
        notes="Spinner frames should be removed"
    )

    # Category: scheduled_output (briefings, reports)
    store.add_fixture(
        raw_capture="""**Morning Briefing**
📰 AI News | 4 Feb 2026

**Headlines:**
• Claude 4 released with enhanced reasoning
• Anthropic announces new safety features

**Summary:**
Major developments in AI safety this week...""",
        expected_output="""**Morning Briefing**
📰 AI News | 4 Feb 2026

**Headlines:**
• Claude 4 released with enhanced reasoning
• Anthropic announces new safety features

**Summary:**
Major developments in AI safety this week...""",
        category="scheduled_output",
        source="seed",
        tags=["briefing", "news"],
        difficulty="normal",
        notes="Morning briefing format"
    )

    stats = store.get_fixture_stats()
    print(f"\nSeeded {stats['total']} fixtures across {len(stats['by_category'])} categories:")
    for cat, data in stats['by_category'].items():
        print(f"  - {cat}: {data['total']} fixtures")

    return stats['total']


def seed_format_specs():
    """Create format specs for scheduled outputs."""
    print("\nSeeding scheduled output format specs...")

    # Morning Briefing spec
    create_format_spec(
        skill_name="morning-briefing",
        display_name="Morning Briefing",
        required_sections=["headlines", "summaries"],
        required_indicators=["📰", "**"],
        section_order=["headlines", "summaries"],
        min_length=200,
        max_length=2000,
        expected_patterns=[r"\*\*Headlines\*\*", r"•"],
    )

    # Health Digest spec
    create_format_spec(
        skill_name="health-digest",
        display_name="Health Digest",
        required_sections=["sleep", "steps", "weight", "heart_rate"],
        required_indicators=["😴", "🚶", "⚖️", "❤️"],
        min_length=300,
        max_length=1500,
    )

    # School Run spec
    create_format_spec(
        skill_name="school-run",
        display_name="School Run",
        required_sections=["weather", "traffic", "departure_time"],
        required_indicators=["🌡️", "🚗", "⏰"],
        min_length=150,
        max_length=800,
    )

    # Hydration spec
    create_format_spec(
        skill_name="hydration",
        display_name="Hydration Check",
        required_sections=["hydration", "steps"],
        required_indicators=["💧"],
        min_length=100,
        max_length=500,
    )

    # Nutrition Summary spec
    create_format_spec(
        skill_name="nutrition-summary",
        display_name="Nutrition Summary",
        required_sections=["nutrition", "goals_progress"],
        required_indicators=["🍽️", "✅", "❌"],
        min_length=200,
        max_length=1000,
    )

    print("Created 5 format specs")


def main():
    print("=" * 50)
    print("Self-Improving Parser - Database Initialization")
    print("=" * 50)

    # Seed fixtures
    count = seed_fixtures()

    # Seed format specs
    seed_format_specs()

    print("\n" + "=" * 50)
    print(f"Initialization complete!")
    print(f"Database: data/parser_fixtures.db")
    print(f"Fixtures: {count}")
    print("=" * 50)
    print("\nRun regression test with:")
    print("  python -m domains.peterbot.parser_regression run")


if __name__ == "__main__":
    main()

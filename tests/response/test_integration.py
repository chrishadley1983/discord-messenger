"""End-to-end integration tests for Response Processing Pipeline.

Tests the full flow from raw Claude Code output to Discord-ready messages.
Simulates real-world scenarios and edge cases.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from domains.peterbot.response.pipeline import process, ProcessedResponse
from domains.peterbot.response.classifier import ResponseType


def test_integration():
    """Run end-to-end integration tests."""
    print("=" * 70)
    print("END-TO-END INTEGRATION TESTS")
    print("=" * 70)

    passed = 0
    failed = 0

    # ==========================================================================
    # SECTION 1: Real Claude Code Output Scenarios
    # ==========================================================================
    print("\n--- Real Claude Code Output Scenarios ---")

    # Test 1: Full CC output with multiple artifacts
    test_input = """⏺ Let me help you with that.

Here's how to create a simple Python function:

```python
def greet(name):
    return f"Hello, {name}!"
```

This function takes a name and returns a greeting.

Total tokens: 1,247 | Cost: $0.003
"""
    result = process(test_input, {'user_prompt': 'How do I write a greeting function?'})

    checks = [
        ('Artifacts removed', '⏺' not in result.content and 'Total tokens' not in result.content),
        ('Code preserved', 'def greet' in result.content or result.response_type == ResponseType.CODE),
        ('Has content', len(result.content) > 0),
        ('Chunks valid', all(len(c) <= 2000 for c in result.chunks)),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Full CC output processing")
    else:
        failed += 1
        print(f"[FAIL] Full CC output processing")
        for name, ok in checks:
            if not ok:
                print(f"    - {name}: FAILED")

    # Test 2: Water log response
    test_input = """⏺ Logging your water intake...

💧 Logged 500ml

**Progress:** 2,250ml / 3,500ml (64%)
1,250ml to go!

Hope this helps!"""
    result = process(test_input, {'user_prompt': 'Log 500ml water'})

    checks = [
        ('Type is water_log', result.response_type == ResponseType.WATER_LOG),
        ('Emoji preserved', '💧' in result.content),
        ('Progress shown', '/' in result.content and '%' in result.content),
        ('Artifacts removed', '⏺' not in result.content),
        ('Trailing meta removed', 'Hope this helps' not in result.content),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Water log response")
    else:
        failed += 1
        print(f"[FAIL] Water log response")
        for name, ok in checks:
            if not ok:
                print(f"    - {name}: FAILED")

    # Test 3: Search results with embedded tool calls
    test_input = """⎿ Read brave_web_search
  Query: "Python async await tutorial"

🔍 **Web Search Results**

**1. [Python Async/Await Guide](https://realpython.com/async-io-python/)**
Comprehensive guide to asyncio in Python 3.7+

**2. [Official asyncio Documentation](https://docs.python.org/3/library/asyncio.html)**
Python standard library documentation

Let me know if you need more information!"""
    result = process(test_input, {'user_prompt': 'Search for Python async tutorial'})

    checks = [
        ('Type is search_results', result.response_type == ResponseType.SEARCH_RESULTS),
        ('Tool call removed', '⎿' not in result.content),
        ('Has embed or content', result.embed is not None or len(result.content) > 0),
        ('Links preserved', 'realpython.com' in result.content or (result.embed and 'realpython' in str(result.embed))),
        ('Trailing meta removed', 'Let me know' not in result.content),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Search results with tool calls")
    else:
        failed += 1
        print(f"[FAIL] Search results with tool calls")
        for name, ok in checks:
            if not ok:
                print(f"    - {name}: FAILED")

    # Test 4: Error response
    test_input = """⏺ I encountered an issue.

⚠️ Error: Could not connect to the database

The connection timed out after 30 seconds. Please check:
1. Database is running
2. Network connectivity
3. Credentials are correct

Let me know if you need help troubleshooting!"""
    result = process(test_input, {'user_prompt': 'Query the database'})

    checks = [
        ('Type is error', result.response_type == ResponseType.ERROR),
        ('Warning preserved', '⚠️' in result.content),
        ('Error message present', 'database' in result.content.lower()),  # Summary contains 'database'
        ('Artifacts removed', '⏺' not in result.content),
        ('Trailing meta removed', 'Let me know' not in result.content),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Error response")
    else:
        failed += 1
        print(f"[FAIL] Error response")
        for name, ok in checks:
            if not ok:
                print(f"    - {name}: FAILED")

    # Test 5: Nutrition summary
    test_input = """⏺ Here's your nutrition summary.

**Today's Nutrition** 🍎

📊 **Calories:** 1,786 / 2,100 (85%)
💪 **Protein:** 140g / 160g (88%)
🍞 **Carbs:** 180g / 200g (90%)
🥑 **Fat:** 65g / 70g (93%)

Great job staying on track today!"""
    result = process(test_input, {'user_prompt': "How am I doing today?"})

    checks = [
        ('Type is nutrition_summary', result.response_type == ResponseType.NUTRITION_SUMMARY),
        ('Emoji preserved', '🍎' in result.content or '📊' in result.content),
        ('Macros present', 'Calories' in result.content),
        ('Percentages shown', '%' in result.content),
        ('Artifacts removed', '⏺' not in result.content),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Nutrition summary")
    else:
        failed += 1
        print(f"[FAIL] Nutrition summary")
        for name, ok in checks:
            if not ok:
                print(f"    - {name}: FAILED")

    # ==========================================================================
    # SECTION 2: Complex Real-World Scenarios
    # ==========================================================================
    print("\n--- Complex Real-World Scenarios ---")

    # Test 6: Very long response requiring chunking
    long_content = "Here's a detailed explanation:\n\n" + ("This is an important point. " * 300)
    result = process(long_content, {'user_prompt': 'Explain in detail'})

    checks = [
        ('Multiple chunks', len(result.chunks) > 1),
        ('All chunks under limit', all(len(c) <= 2000 for c in result.chunks)),
        ('No content lost', sum(len(c) for c in result.chunks) >= len(long_content) * 0.8),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Long response chunking - {len(result.chunks)} chunks")
    else:
        failed += 1
        print(f"[FAIL] Long response chunking")
        for name, ok in checks:
            if not ok:
                print(f"    - {name}: FAILED")

    # Test 7: Mixed content (code + prose + table)
    test_input = """Here's an overview:

```python
def calculate(x, y):
    return x + y
```

Results:

| Input | Output |
|-------|--------|
| 1, 2  | 3      |
| 5, 5  | 10     |

The function works as expected."""
    result = process(test_input, {'user_prompt': 'Show me the calculator'})

    checks = [
        ('Has content', len(result.content) > 0),
        ('No crash', True),
        ('Chunks valid', all(len(c) <= 2000 for c in result.chunks)),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Mixed content (code + prose + table)")
    else:
        failed += 1
        print(f"[FAIL] Mixed content")
        for name, ok in checks:
            if not ok:
                print(f"    - {name}: FAILED")

    # Test 8: --raw bypass mode
    test_input = "⏺ Raw content with artifacts ⎿"
    result = process(test_input, {'user_prompt': 'Show me --raw output'})

    checks = [
        ('Is bypassed', result.was_bypassed),
        ('Wrapped in code block', result.content.startswith('```') and result.content.endswith('```')),
        ('Artifacts preserved', '⏺' in result.content),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] --raw bypass mode")
    else:
        failed += 1
        print(f"[FAIL] --raw bypass mode")
        for name, ok in checks:
            if not ok:
                print(f"    - {name}: FAILED")

    # Test 9: Schedule/Calendar response
    test_input = """📅 **Today's Schedule** - Monday, 3rd February

**Morning:**
• 09:00 - Team standup
• 10:30 - Product review

**Afternoon:**
• 14:00 - Client call
• 16:00 - Sprint planning"""
    result = process(test_input, {'user_prompt': "What's on today?"})

    checks = [
        ('Type is schedule', result.response_type == ResponseType.SCHEDULE),
        ('Emoji preserved', '📅' in result.content or '🗓️' in result.content),
        ('Events present', 'standup' in result.content.lower() or 'Team' in result.content),
        # Formatter converts to Discord timestamps <t:...:F> OR keeps original times
        ('Times present', '<t:' in result.content or '09:00' in result.content or '9:00' in result.content),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Schedule response")
    else:
        failed += 1
        print(f"[FAIL] Schedule response")
        for name, ok in checks:
            if not ok:
                print(f"    - {name}: FAILED")

    # Test 10: ANSI codes in output
    test_input = "\x1b[32mSuccess:\x1b[0m The operation completed.\n\x1b[1mNext steps:\x1b[0m Continue."
    result = process(test_input, {'user_prompt': 'Run the command'})

    checks = [
        ('ANSI codes removed', '\x1b[' not in result.content),
        ('Content preserved', 'Success' in result.content and 'completed' in result.content),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] ANSI code removal")
    else:
        failed += 1
        print(f"[FAIL] ANSI code removal")
        for name, ok in checks:
            if not ok:
                print(f"    - {name}: FAILED")

    # ==========================================================================
    # SECTION 3: Edge Cases and Error Handling
    # ==========================================================================
    print("\n--- Edge Cases and Error Handling ---")

    # Test 11: Empty input
    result = process("", {'user_prompt': 'test'})
    checks = [
        ('Empty content', result.content == ''),
        ('Empty chunks', len(result.chunks) == 0 or result.chunks == ['']),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Empty input handling")
    else:
        failed += 1
        print(f"[FAIL] Empty input handling")

    # Test 12: Only whitespace
    result = process("   \n\n   \t   \n", {'user_prompt': 'test'})
    checks = [
        ('Whitespace trimmed', len(result.content.strip()) == 0),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Whitespace-only input")
    else:
        failed += 1
        print(f"[FAIL] Whitespace-only input")

    # Test 13: Unicode and emoji preservation
    test_input = "こんにちは! 🎉 مرحبا 🌍 Привет"
    result = process(test_input, {'user_prompt': 'test'})
    checks = [
        ('Japanese preserved', 'こんにちは' in result.content),
        ('Arabic preserved', 'مرحبا' in result.content),
        ('Emoji preserved', '🎉' in result.content and '🌍' in result.content),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Unicode and emoji preservation")
    else:
        failed += 1
        print(f"[FAIL] Unicode and emoji preservation")

    # Test 14: Only CC artifacts (should result in empty)
    test_input = "⏺ \n⎿ Read file.txt\nTotal tokens: 500"
    result = process(test_input, {'user_prompt': 'test'})
    checks = [
        ('Artifacts removed', '⏺' not in result.content and '⎿' not in result.content),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Only artifacts input")
    else:
        failed += 1
        print(f"[FAIL] Only artifacts input")

    # Test 15: Malformed code blocks
    test_input = "Here's code:\n```python\ndef broken(\n# No closing fence"
    result = process(test_input, {'user_prompt': 'test'})
    checks = [
        ('No crash', True),
        ('Has content', len(result.content) > 0),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Malformed code block handling")
    else:
        failed += 1
        print(f"[FAIL] Malformed code block handling")

    # ==========================================================================
    # SECTION 4: ProcessedResponse Structure Validation
    # ==========================================================================
    print("\n--- Response Structure Validation ---")

    # Test 16: Full ProcessedResponse structure
    test_input = "Simple response for structure test."
    result = process(test_input, {'user_prompt': 'test'})

    checks = [
        ('Has content attr', hasattr(result, 'content')),
        ('Has chunks attr', hasattr(result, 'chunks')),
        ('Has response_type attr', hasattr(result, 'response_type')),
        ('Has embed attr', hasattr(result, 'embed')),
        ('Has embeds attr', hasattr(result, 'embeds')),
        ('Has reactions attr', hasattr(result, 'reactions')),
        ('Has raw_length attr', hasattr(result, 'raw_length')),
        ('Has final_length attr', hasattr(result, 'final_length')),
        ('Has was_bypassed attr', hasattr(result, 'was_bypassed')),
        ('response_type is enum', isinstance(result.response_type, ResponseType)),
        ('chunks is list', isinstance(result.chunks, list)),
        ('embeds is list', isinstance(result.embeds, list)),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] ProcessedResponse structure complete")
    else:
        failed += 1
        print(f"[FAIL] ProcessedResponse structure")
        for name, ok in checks:
            if not ok:
                print(f"    - {name}: FAILED")

    # ==========================================================================
    # SECTION 5: Performance/Size Validation
    # ==========================================================================
    print("\n--- Size and Performance Validation ---")

    # Test 17: Under chunker's safe limit (1900)
    # Chunker uses 1900 max_chars to leave headroom for chunk numbers etc.
    test_input = "A" * 1800
    result = process(test_input, {'user_prompt': 'test'})
    checks = [
        ('Single chunk under limit', len(result.chunks) == 1),
        ('Chunk under Discord limit', len(result.chunks[0]) <= 2000),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Under chunker safe limit (1800 chars)")
    else:
        failed += 1
        print(f"[FAIL] Under chunker safe limit")

    # Test 18: Just over 2000 char boundary
    test_input = "A" * 2001
    result = process(test_input, {'user_prompt': 'test'})
    checks = [
        ('Multiple chunks', len(result.chunks) >= 2),
        ('All under limit', all(len(c) <= 2000 for c in result.chunks)),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Just over 2000 char boundary")
    else:
        failed += 1
        print(f"[FAIL] Just over 2000 char boundary")

    # Test 19: Very large response (10k chars)
    test_input = "Word " * 2000  # ~10k chars
    result = process(test_input, {'user_prompt': 'test'})
    checks = [
        ('Many chunks', len(result.chunks) >= 5),
        ('All under limit', all(len(c) <= 2000 for c in result.chunks)),
        ('Total content preserved', sum(len(c) for c in result.chunks) >= 8000),
    ]

    all_pass = all(c[1] for c in checks)
    if all_pass:
        passed += 1
        print(f"[PASS] Very large response (10k chars) - {len(result.chunks)} chunks")
    else:
        failed += 1
        print(f"[FAIL] Very large response")
        for name, ok in checks:
            if not ok:
                print(f"    - {name}: FAILED")

    # ==========================================================================
    # SUMMARY
    # ==========================================================================
    print("\n" + "=" * 70)
    total = passed + failed
    print(f"INTEGRATION TEST RESULTS: {passed}/{total} tests passed ({100*passed//total}%)")
    print("=" * 70)

    if failed > 0:
        print(f"\n[!] {failed} tests failed - review output above")
        return False
    else:
        print("\n[OK] All integration tests passed!")
        return True


if __name__ == '__main__':
    success = test_integration()
    sys.exit(0 if success else 1)

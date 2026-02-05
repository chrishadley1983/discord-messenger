"""Edge case tests for the Response Processing Pipeline.

Tests unusual inputs, boundary conditions, and potential failure modes.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from domains.peterbot.response.pipeline import process, ProcessedResponse
from domains.peterbot.response.classifier import ResponseType
from domains.peterbot.response.sanitiser import sanitise


def run_edge_case_tests():
    """Run edge case tests."""
    print("=" * 70)
    print("EDGE CASE TESTS")
    print("=" * 70)

    passed = 0
    failed = 0

    # Test 1: Empty input
    print("\n--- Empty/Null Input Tests ---")
    tests = [
        ("Empty string", "", True),
        ("Whitespace only", "   \n\n   ", True),
        ("Just newlines", "\n\n\n", True),
    ]

    for name, input_text, should_be_empty in tests:
        result = process(input_text)
        is_empty = len(result.content.strip()) == 0
        if is_empty == should_be_empty:
            passed += 1
            print(f"[PASS] {name}")
        else:
            failed += 1
            print(f"[FAIL] {name} - expected {'empty' if should_be_empty else 'content'}")

    # Test 2: Very long inputs
    print("\n--- Long Input Tests ---")
    tests = [
        ("2000 char message", "A" * 2000, 1),  # Should fit in one chunk
        ("4000 char message", "A" * 4000, 3),  # Should split into 3 chunks
        ("8000 char message", "A " * 4000, 5),  # With spaces for better splitting
    ]

    for name, input_text, min_chunks in tests:
        result = process(input_text)
        # All chunks should be under 2000 chars
        all_under_limit = all(len(c) <= 2000 for c in result.chunks)
        has_enough_chunks = len(result.chunks) >= min_chunks

        if all_under_limit and has_enough_chunks:
            passed += 1
            print(f"[PASS] {name} - {len(result.chunks)} chunks, all under 2000")
        else:
            failed += 1
            print(f"[FAIL] {name} - {len(result.chunks)} chunks, max: {max(len(c) for c in result.chunks)}")

    # Test 3: Unicode and special characters
    print("\n--- Unicode/Special Character Tests ---")
    tests = [
        ("Emoji only", "🎉🚀💯", True),
        ("Japanese text", "こんにちは世界", True),
        ("Mixed script", "Hello 世界! مرحبا 🌍", True),
        ("Special Discord chars", "**bold** *italic* `code` ||spoiler||", True),
        ("Zero-width chars", "Test\u200bwith\u200binvisible", True),
    ]

    for name, input_text, should_preserve in tests:
        result = process(input_text)
        # For these tests, main content should be preserved
        has_content = len(result.content) > 0
        if has_content == should_preserve:
            passed += 1
            print(f"[PASS] {name}")
        else:
            failed += 1
            print(f"[FAIL] {name} - content: {repr(result.content[:50])}")

    # Test 4: Nested code blocks
    print("\n--- Code Block Edge Cases ---")
    tests = [
        ("Triple backtick in text", "Use ``` for code blocks", True),
        ("Code block with ``` inside", "```\nprint('```')\n```", True),
        ("Multiple nested languages", "```python\n# sql\nSELECT * FROM\n```", True),
        ("Unclosed code block", "```python\ncode here", True),  # Should handle gracefully
    ]

    for name, input_text, should_not_crash in tests:
        try:
            result = process(input_text)
            if should_not_crash:
                passed += 1
                print(f"[PASS] {name}")
            else:
                failed += 1
                print(f"[FAIL] {name} - should have handled error")
        except Exception as e:
            if not should_not_crash:
                passed += 1
                print(f"[PASS] {name} - correctly raised error")
            else:
                failed += 1
                print(f"[FAIL] {name} - unexpected error: {e}")

    # Test 5: Malformed markdown tables
    print("\n--- Malformed Table Tests ---")
    tests = [
        ("Incomplete table", "| Header\n|---\n| Cell", False),  # Should not crash
        ("Extra pipes", "||Header||Value||\n|---|---|\n||Cell||Data||", False),
        ("No separator row", "| A | B |\n| 1 | 2 |", False),  # Not a valid table
        ("Mismatched columns", "| A | B |\n|---|\n| 1 | 2 | 3 |", False),
    ]

    for name, input_text, should_format_as_table in tests:
        try:
            result = process(input_text)
            passed += 1
            print(f"[PASS] {name} - handled gracefully, type: {result.response_type.value}")
        except Exception as e:
            failed += 1
            print(f"[FAIL] {name} - error: {e}")

    # Test 6: CC artifact edge cases
    print("\n--- CC Artifact Edge Cases ---")
    tests = [
        ("Just tokens line", "Total tokens: 500", True),  # Should be stripped
        ("Cost in text", "The cost is $5", False),  # Should NOT be stripped (real content)
        ("Thinking with content", "Thinking about your question... The answer is 42.", True),
        ("Multiple bullet markers", "⏺ First\n⏺ Second\n⏺ Third", True),
        ("Nested tool calls", "⎿ Read file.txt\n  ⎿ Nested read\nActual content", True),
    ]

    for name, input_text, should_clean in tests:
        result = process(input_text)
        # Check if artifacts are removed
        has_artifacts = '⏺' in result.content or '⎿' in result.content or 'Total tokens' in result.content
        if should_clean:
            if not has_artifacts:
                passed += 1
                print(f"[PASS] {name} - artifacts removed")
            else:
                failed += 1
                print(f"[FAIL] {name} - artifacts remain in output")
        else:
            passed += 1  # Just checking it doesn't crash
            print(f"[PASS] {name}")

    # Test 7: Mixed content types
    print("\n--- Mixed Content Tests ---")
    tests = [
        (
            "Code and table",
            "```python\ncode\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |",
            True
        ),
        (
            "Search results and prose",
            "Based on my search:\n\n**1. [Link](url)**\n\nSummary here.",
            True
        ),
        (
            "Nutrition and text",
            "**Today's Nutrition** 🍎\n\nCalories: 500\n\nYou're doing great!",
            True
        ),
    ]

    for name, input_text, should_handle in tests:
        try:
            result = process(input_text)
            # Should produce valid output
            if len(result.content) > 0 or result.embed:
                passed += 1
                print(f"[PASS] {name} - type: {result.response_type.value}")
            else:
                failed += 1
                print(f"[FAIL] {name} - no output")
        except Exception as e:
            failed += 1
            print(f"[FAIL] {name} - error: {e}")

    # Test 8: --raw flag variations
    print("\n--- Raw Flag Tests ---")
    tests = [
        ("--raw at end", "Some text --raw", True),
        ("--debug flag", "Content --debug", True),
        ("-raw (no double dash)", "Content -raw", False),  # Should NOT trigger bypass
        ("--RAW uppercase", "Content --RAW", True),
        ("--raw in middle", "Hello --raw world", True),
    ]

    for name, user_prompt, should_bypass in tests:
        result = process("⏺ Some CC output with artifacts", {'user_prompt': user_prompt})
        is_bypassed = result.was_bypassed
        if is_bypassed == should_bypass:
            passed += 1
            print(f"[PASS] {name}")
        else:
            failed += 1
            print(f"[FAIL] {name} - bypass: {is_bypassed}, expected: {should_bypass}")

    # Test 9: ANSI code variations
    print("\n--- ANSI Code Tests ---")
    tests = [
        ("Basic color", "\x1b[31mRed\x1b[0m", False),
        ("Bold", "\x1b[1mBold\x1b[0m", False),
        ("Complex codes", "\x1b[38;5;196mCustom color\x1b[0m", False),
        ("Multiple codes", "\x1b[1m\x1b[31mBold red\x1b[0m", False),
    ]

    for name, input_text, should_have_ansi in tests:
        result = process(input_text)
        has_ansi = '\x1b[' in result.content
        if has_ansi == should_have_ansi:
            passed += 1
            print(f"[PASS] {name}")
        else:
            failed += 1
            print(f"[FAIL] {name} - has ANSI: {has_ansi}")

    # Test 10: Extreme cases
    print("\n--- Extreme Cases ---")

    # Very deeply nested structure
    nested = ">" * 100 + "Deep content"
    result = process(nested)
    passed += 1
    print(f"[PASS] Deep nesting - handled")

    # Many line breaks
    many_breaks = "Content\n" * 500
    result = process(many_breaks)
    if '\n\n\n' not in result.content:  # Should collapse
        passed += 1
        print(f"[PASS] Many line breaks - collapsed")
    else:
        failed += 1
        print(f"[FAIL] Many line breaks - not collapsed")

    # Binary-ish content
    binary_like = "".join(chr(i) for i in range(32, 127))
    result = process(binary_like)
    passed += 1
    print(f"[PASS] Binary-like content - handled")

    # Summary
    print("\n" + "=" * 70)
    print(f"EDGE CASE RESULTS: {passed}/{passed + failed} tests passed")
    print("=" * 70)

    return failed == 0


if __name__ == '__main__':
    success = run_edge_case_tests()
    sys.exit(0 if success else 1)

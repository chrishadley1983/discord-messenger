"""Discord flow simulation test.

Simulates the complete message flow from bot.py through the pipeline.
This is the final verification that the integration works correctly.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from domains.peterbot.response.pipeline import process as process_response


class MockEmbed:
    """Mock Discord embed for testing."""

    def __init__(self, data):
        self.data = data

    @classmethod
    def from_dict(cls, data):
        return cls(data)


def simulate_discord_send(chunk: str, embed=None):
    """Simulate sending a message to Discord."""
    # Discord limits
    if len(chunk) > 2000:
        raise ValueError(f"Message too long: {len(chunk)} > 2000")

    return {
        'content': chunk,
        'embed': embed.data if embed else None
    }


def simulate_bot_peterbot_handler(raw_response: str, user_message: str) -> list[dict]:
    """Simulate the bot.py Peterbot message handler."""
    # This mirrors the actual code in bot.py lines 257-290

    # Process through Response Pipeline (sanitise -> classify -> format -> chunk)
    processed = process_response(raw_response, {'user_prompt': user_message})

    sent_messages = []

    # Send chunks (pipeline handles Discord 2000 char limit)
    for i, chunk in enumerate(processed.chunks):
        if not chunk.strip():
            continue  # Skip empty chunks

        # First chunk can include embed
        if i == 0 and processed.embed:
            embed_obj = MockEmbed.from_dict(processed.embed)
            sent_messages.append(simulate_discord_send(chunk, embed_obj))
        else:
            sent_messages.append(simulate_discord_send(chunk))

    # Send additional embeds (e.g., image results)
    for embed_data in processed.embeds:
        embed_obj = MockEmbed.from_dict(embed_data)
        sent_messages.append(simulate_discord_send('', embed_obj))

    return sent_messages, processed


def test_discord_flow():
    """Run Discord flow simulation tests."""
    print("=" * 70)
    print("DISCORD FLOW SIMULATION TESTS")
    print("=" * 70)

    passed = 0
    failed = 0

    # ==========================================================================
    # Test 1: Simple conversational response
    # ==========================================================================
    print("\n--- Test 1: Simple Conversational ---")
    raw = "Hello! How can I help you today?"
    user = "Hi there"

    try:
        messages, processed = simulate_bot_peterbot_handler(raw, user)

        checks = [
            len(messages) == 1,
            len(messages[0]['content']) <= 2000,
            'Hello' in messages[0]['content'],
            messages[0]['embed'] is None,
        ]

        if all(checks):
            passed += 1
            print("[PASS] Simple conversational response")
        else:
            failed += 1
            print("[FAIL] Simple conversational response")
            print(f"    Messages: {len(messages)}, Content: {messages[0]['content'][:50]}")
    except Exception as e:
        failed += 1
        print(f"[FAIL] Exception: {e}")

    # ==========================================================================
    # Test 2: Response with CC artifacts
    # ==========================================================================
    print("\n--- Test 2: CC Artifact Removal ---")
    raw = """⏺ Processing your request...

Here's the answer you wanted.

Total tokens: 1,247 | Cost: $0.003
Let me know if you need anything else!"""
    user = "What's the answer?"

    try:
        messages, processed = simulate_bot_peterbot_handler(raw, user)

        checks = [
            len(messages) >= 1,
            '⏺' not in messages[0]['content'],
            'Total tokens' not in messages[0]['content'],
            'Let me know' not in messages[0]['content'],
            "answer" in messages[0]['content'].lower(),
        ]

        if all(checks):
            passed += 1
            print("[PASS] CC artifacts removed, content preserved")
        else:
            failed += 1
            print("[FAIL] CC artifact removal")
            print(f"    Content: {messages[0]['content'][:100]}")
    except Exception as e:
        failed += 1
        print(f"[FAIL] Exception: {e}")

    # ==========================================================================
    # Test 3: Long response requiring chunking
    # ==========================================================================
    print("\n--- Test 3: Long Response Chunking ---")
    raw = "Here's a detailed explanation. " + ("This is important information. " * 100)
    user = "Explain in detail"

    try:
        messages, processed = simulate_bot_peterbot_handler(raw, user)

        checks = [
            len(messages) >= 2,  # Should need multiple chunks
            all(len(m['content']) <= 2000 for m in messages),  # All under limit
        ]

        if all(checks):
            passed += 1
            print(f"[PASS] Long response split into {len(messages)} chunks, all under 2000 chars")
        else:
            failed += 1
            print(f"[FAIL] Long response chunking")
            print(f"    Chunks: {len(messages)}, Max length: {max(len(m['content']) for m in messages)}")
    except Exception as e:
        failed += 1
        print(f"[FAIL] Exception: {e}")

    # ==========================================================================
    # Test 4: Water log response
    # ==========================================================================
    print("\n--- Test 4: Water Log Response ---")
    raw = """⏺ Logging water...

💧 Logged 500ml

**Progress:** 2,250ml / 3,500ml (64%)
1,250ml to go!"""
    user = "Log 500ml water"

    try:
        messages, processed = simulate_bot_peterbot_handler(raw, user)

        checks = [
            len(messages) >= 1,
            '💧' in messages[0]['content'],
            '/' in messages[0]['content'],  # Progress indicator
            '%' in messages[0]['content'],  # Percentage
            '⏺' not in messages[0]['content'],
            processed.response_type.value == 'water_log',
        ]

        if all(checks):
            passed += 1
            print(f"[PASS] Water log formatted correctly (type={processed.response_type.value})")
        else:
            failed += 1
            print(f"[FAIL] Water log response")
            print(f"    Type: {processed.response_type.value}, Content: {messages[0]['content'][:100]}")
    except Exception as e:
        failed += 1
        print(f"[FAIL] Exception: {e}")

    # ==========================================================================
    # Test 5: Search results with embed
    # ==========================================================================
    print("\n--- Test 5: Search Results ---")
    raw = """🔍 **Web Search Results**

**1. [Python Tutorial](https://python.org/doc)**
Official Python documentation

**2. [Learn Python](https://learnpython.org)**
Interactive Python tutorial"""
    user = "Search for Python tutorials"

    try:
        messages, processed = simulate_bot_peterbot_handler(raw, user)

        # Search results should have embed or content
        has_output = (
            (len(messages) >= 1 and len(messages[0]['content']) > 0) or
            processed.embed is not None
        )

        checks = [
            has_output,
            processed.response_type.value == 'search_results',
        ]

        if all(checks):
            passed += 1
            print(f"[PASS] Search results (type={processed.response_type.value}, has_embed={processed.embed is not None})")
        else:
            failed += 1
            print(f"[FAIL] Search results")
    except Exception as e:
        failed += 1
        print(f"[FAIL] Exception: {e}")

    # ==========================================================================
    # Test 6: --raw bypass mode
    # ==========================================================================
    print("\n--- Test 6: --raw Bypass Mode ---")
    raw = "⏺ Raw content with artifacts ⎿"
    user = "Show me --raw output"

    try:
        messages, processed = simulate_bot_peterbot_handler(raw, user)

        checks = [
            processed.was_bypassed,
            messages[0]['content'].startswith('```'),
            messages[0]['content'].endswith('```'),
            '⏺' in messages[0]['content'],  # Artifacts preserved in raw mode
        ]

        if all(checks):
            passed += 1
            print("[PASS] --raw bypass mode preserves artifacts in code block")
        else:
            failed += 1
            print(f"[FAIL] --raw bypass mode")
            print(f"    Bypassed: {processed.was_bypassed}, Content starts with ```: {messages[0]['content'].startswith('```')}")
    except Exception as e:
        failed += 1
        print(f"[FAIL] Exception: {e}")

    # ==========================================================================
    # Test 7: Error response
    # ==========================================================================
    print("\n--- Test 7: Error Response ---")
    raw = """⏺ An error occurred.

⚠️ Error: Failed to connect to database

Connection refused on port 5432."""
    user = "Query the database"

    try:
        messages, processed = simulate_bot_peterbot_handler(raw, user)

        checks = [
            len(messages) >= 1,
            '⚠️' in messages[0]['content'],
            'database' in messages[0]['content'].lower(),
            '⏺' not in messages[0]['content'],
            processed.response_type.value == 'error',
        ]

        if all(checks):
            passed += 1
            print(f"[PASS] Error response (type={processed.response_type.value})")
        else:
            failed += 1
            print(f"[FAIL] Error response")
            print(f"    Type: {processed.response_type.value}, Content: {messages[0]['content'][:100]}")
    except Exception as e:
        failed += 1
        print(f"[FAIL] Exception: {e}")

    # ==========================================================================
    # Test 8: Empty response handling
    # ==========================================================================
    print("\n--- Test 8: Empty Response ---")
    raw = ""
    user = "test"

    try:
        messages, processed = simulate_bot_peterbot_handler(raw, user)

        # Should handle gracefully with no crash
        checks = [
            len(messages) == 0 or (len(messages) == 1 and messages[0]['content'] == ''),
        ]

        if all(checks):
            passed += 1
            print("[PASS] Empty response handled gracefully")
        else:
            failed += 1
            print(f"[FAIL] Empty response handling")
    except Exception as e:
        failed += 1
        print(f"[FAIL] Exception on empty response: {e}")

    # ==========================================================================
    # Test 9: Unicode preservation
    # ==========================================================================
    print("\n--- Test 9: Unicode Preservation ---")
    raw = "こんにちは! 🎉 Testing unicode: мир 世界"
    user = "Test unicode"

    try:
        messages, processed = simulate_bot_peterbot_handler(raw, user)

        checks = [
            'こんにちは' in messages[0]['content'],
            '🎉' in messages[0]['content'],
            'мир' in messages[0]['content'],
            '世界' in messages[0]['content'],
        ]

        if all(checks):
            passed += 1
            print("[PASS] Unicode preserved correctly")
        else:
            failed += 1
            print(f"[FAIL] Unicode preservation")
    except Exception as e:
        failed += 1
        print(f"[FAIL] Exception: {e}")

    # ==========================================================================
    # Test 10: Very large response (stress test)
    # ==========================================================================
    print("\n--- Test 10: Stress Test (10k chars) ---")
    raw = "Important information: " + ("Details about the topic. " * 500)  # ~12.5k chars
    user = "Give me all the details"

    try:
        messages, processed = simulate_bot_peterbot_handler(raw, user)

        checks = [
            len(messages) >= 5,  # Should need many chunks
            all(len(m['content']) <= 2000 for m in messages),  # All under limit
            sum(len(m['content']) for m in messages) >= 8000,  # Most content preserved
        ]

        if all(checks):
            passed += 1
            print(f"[PASS] Stress test: {len(messages)} chunks, all under 2000 chars")
        else:
            failed += 1
            print(f"[FAIL] Stress test")
            print(f"    Chunks: {len(messages)}")
            if messages:
                print(f"    Max length: {max(len(m['content']) for m in messages)}")
    except Exception as e:
        failed += 1
        print(f"[FAIL] Exception: {e}")

    # ==========================================================================
    # Summary
    # ==========================================================================
    print("\n" + "=" * 70)
    total = passed + failed
    print(f"DISCORD FLOW SIMULATION: {passed}/{total} tests passed ({100*passed//total}%)")
    print("=" * 70)

    if failed > 0:
        print(f"\n[!] {failed} tests failed")
        return False
    else:
        print("\n[OK] All Discord flow tests passed - Integration verified!")
        return True


if __name__ == '__main__':
    success = test_discord_flow()
    sys.exit(0 if success else 1)

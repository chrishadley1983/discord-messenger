"""Test that new leakage patterns catch the identified issues."""

import sys
sys.path.insert(0, '.')

from domains.peterbot.response.sanitiser import sanitise, SANITISER_RULES, AGGRESSIVE_PATTERNS
from domains.peterbot.capture_parser import ParserCaptureStore

# Real samples from today's analysis (24h captures)
REAL_LEAKAGE_SAMPLES = [
    # #1: Instruction echo (63 instances undetected)
    '''Current Message section.

Answer: Honestly, no — the Reddit/X searches didn't surface great results. I
searched "Reddit fitmeals high protein" but WebSearch mostly returned
mainstream recipe sites instead of actual Reddit threads.''',

    # #2: JSON key leakage (26 instances)
    '''Current Message section.

"message_id": "19c2a81a5952faa7",

✓ Resent to chrishadley1983@gmail.com

Noted for the future — saved to my memory.''',

    # #3: JSON with brackets (25 instances)
    '''{

"message_id": "19c2a800a31dc70f",

✓ Email sent to chris@hadley.net

Subject: Peter's Morning To-Do List''',

    # #4: Claude Code UI artifacts (spinners, thinking, tokens)
    '''|| echo "No g✽)

/home/chris_hadley/.claude/projects/-home-chris-hadley-peterbot/*.jsonl

✽ Sketching✽ (49s ✽ ↓ 1.7k tokens ✽ thinking)''',

    # #5: UUID path fragments
    '''}

7e5-f80cb411cefd" \\

pi/inventory/d035e1b3-a8c4-422d-a7e5-f80cb411cefd" \\

The item exists (SKU: N3170) but there's no update endpoint on the Hadley API yet.''',

    # #6: Python one-liner fragments
    '''"import sys,json; d=json.load(sys.stdin); print('\\n'.join(sorted([p for p
in d.get('path✽)

sys,json; d=json.load(sys.stdin); [print(p) for p in
sorted(d.get('paths',{}).keys()) if '/h✽)

asin=B08SJ8R7WB&refresh=true")''',

    # #7: Curl with Content-Type
    '''application/json" -d '{"set_number": "40448", "cost": 0, "source":
"Vinted", "seller": "✽)

}

"Vinted", "seller✽)

The /hb/purchases endpoint exists now.''',
]

# What clean output should look like (instruction echo removed, JSON removed, etc.)
EXPECTED_CLEAN = [
    # Sample 1 - instruction echo should be stripped
    "shouldn't contain 'Current Message section' or 'Answer:'",
    # Sample 2 - JSON should be stripped
    "shouldn't contain '\"message_id\"'",
    # Sample 3 - JSON brackets should be stripped
    "shouldn't contain standalone { or }",
    # Sample 4 - Claude Code artifacts should be stripped
    "shouldn't contain spinner chars, paths, or token counts",
    # Sample 5 - UUID paths should be stripped
    "shouldn't contain UUIDs or pi/inventory paths",
    # Sample 6 - Python commands should be stripped
    "shouldn't contain 'import sys,json'",
    # Sample 7 - Curl fragments should be stripped
    "shouldn't contain 'application/json' or curl commands",
]


def safe_print(s):
    """Print with ASCII fallback for Windows console."""
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode('ascii', 'replace').decode())


def test_sanitiser():
    """Test that sanitiser removes the identified leakage."""
    safe_print("=" * 60)
    safe_print("TESTING SANITISER PATTERNS")
    safe_print("=" * 60)

    passed = 0
    failed = 0

    bad_patterns = [
        'Current Message section',
        'Message section.',
        'Answer:',
        '"message_id"',
        '"event_id"',
        '"session_id"',
        'import sys,json',
        'json.load(sys.stdin)',
        'Sketching',  # Without spinner char for matching
        'tokens',     # Token counts
        'pi/inventory/',
        '.claude/projects/',
        '/home/chris_hadley/',
        '*.jsonl',
        'application/json" -d',
        '-H "Content-Type:',
    ]

    for i, sample in enumerate(REAL_LEAKAGE_SAMPLES, 1):
        safe_print(f"\n--- Sample {i} ---")
        safe_print(f"Input ({len(sample)} chars): {sample[:80].encode('ascii', 'replace').decode()}...")

        cleaned = sanitise(sample, aggressive=True)
        safe_print(f"Output ({len(cleaned)} chars): {cleaned[:80].encode('ascii', 'replace').decode()}...")

        # Check for bad patterns still present
        issues = []
        for pattern in bad_patterns:
            if pattern in cleaned:
                issues.append(pattern)

        if issues:
            failed += 1
            safe_print(f"FAIL - Still contains: {issues}")
        else:
            passed += 1
            safe_print("PASS - All leak patterns removed")

    safe_print(f"\n{'=' * 60}")
    safe_print(f"Results: {passed}/{len(REAL_LEAKAGE_SAMPLES)} passed ({100*passed/len(REAL_LEAKAGE_SAMPLES):.0f}%)")
    safe_print(f"{'=' * 60}")
    return failed == 0


def test_echo_detection():
    """Test that capture_parser._detect_echo catches these patterns."""
    safe_print("\n" + "=" * 60)
    safe_print("TESTING ECHO DETECTION")
    safe_print("=" * 60)

    store = ParserCaptureStore()

    # Simulate screen_before (what CC showed before user input)
    screen_before = """> test message

> /nutrition log breakfast porridge
"""

    test_outputs = [
        ('Current Message section.\n\nLogged: porridge', True),
        ('|| echo "test"', True),
        ('Sketching (10s)', True),  # Simplified
        ('/home/chris_hadley/.claude/projects/foo', True),
        ('import sys,json; d=json.load(sys.stdin)', True),
        ('"message_id": "abc123"', True),
        ('Just a normal response with no leakage', False),
        ('Logged: porridge - 350 cal', False),
    ]

    passed = 0
    for output, should_detect in test_outputs:
        detected = store._detect_echo(screen_before, output)
        if detected == should_detect:
            passed += 1
            status = "PASS"
        else:
            status = "FAIL"
        safe_print(f"{status}: '{output[:50]}' -> detected={detected} (expected={should_detect})")

    safe_print(f"\nEcho detection: {passed}/{len(test_outputs)} passed")
    return passed == len(test_outputs)


def main():
    safe_print("LEAKAGE PATTERN TEST SUITE")
    safe_print("Based on 24h analysis of 75 captures")
    safe_print("")

    san_ok = test_sanitiser()
    echo_ok = test_echo_detection()

    safe_print("\n" + "=" * 60)
    safe_print("FINAL SUMMARY")
    safe_print("=" * 60)
    safe_print(f"Sanitiser tests: {'PASS' if san_ok else 'FAIL'}")
    safe_print(f"Echo detection tests: {'PASS' if echo_ok else 'FAIL'}")

    if san_ok and echo_ok:
        safe_print("\nAll tests passed! Ready to deploy.")
        return 0
    else:
        safe_print("\nSome tests failed. Review before deploying.")
        return 1


if __name__ == '__main__':
    exit(main())

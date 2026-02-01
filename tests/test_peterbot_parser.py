"""Parser tests for peterbot domain.

Extracted from domains/peterbot/parser.py to keep production code clean.
Run with: python -m pytest tests/test_peterbot_parser.py -v
Or directly: python tests/test_peterbot_parser.py
"""

from domains.peterbot.parser import parse_response, ParseMode


# =============================================================================
# TESTING FRAMEWORK
# =============================================================================

def run_parser_tests() -> dict:
    """Run comprehensive parser tests.

    Returns:
        Dict with test results
    """
    results = {
        'passed': 0,
        'failed': 0,
        'failures': []
    }

    for name, test in TEST_CASES.items():
        raw_input = test['input']
        expected_contains = test.get('contains', [])
        expected_excludes = test.get('excludes', [])
        mode = test.get('mode', ParseMode.CONVERSATIONAL)

        result = parse_response(raw_input, mode=mode)
        output = result.content

        passed = True
        failure_reasons = []

        # Check expected content is present
        for expected in expected_contains:
            if expected not in output:
                passed = False
                failure_reasons.append(f"Missing: '{expected[:50]}...'")

        # Check excluded content is absent
        for excluded in expected_excludes:
            if excluded in output:
                passed = False
                failure_reasons.append(f"Should not contain: '{excluded[:50]}...'")

        if passed:
            results['passed'] += 1
        else:
            results['failed'] += 1
            results['failures'].append({
                'name': name,
                'reasons': failure_reasons,
                'output': output[:200]
            })

    return results


# =============================================================================
# TEST CASES - Basic examples (reduced set for maintainability)
# =============================================================================

TEST_CASES = {
    # Basic response
    'simple_greeting': {
        'input': '''
> hello
Hey there! How can I help you today?

>
''',
        'contains': ['Hey there!', 'How can I help you today?'],
        'excludes': ['>', 'hello']
    },

    # Multi-line response
    'multiline_response': {
        'input': '''
> what is python?
Python is a high-level programming language known for:
- Easy to learn syntax
- Strong community support
- Versatile applications

>
''',
        'contains': ['Python is a high-level', 'Easy to learn'],
        'excludes': ['what is python']
    },

    # Code block preservation
    'code_block': {
        'input': '''
> show me hello world
Here's a simple example:

```python
def hello():
    print("Hello, world!")
```

>
''',
        'contains': ['```python', 'def hello():', 'print("Hello, world!")', '```'],
        'excludes': ['show me hello world']
    },
}


# Pytest-compatible test functions
def test_parser_basic():
    """Test basic parser functionality."""
    results = run_parser_tests()
    assert results['failed'] == 0, f"Parser tests failed: {results['failures']}"


def test_parse_mode_conversational():
    """Test conversational mode extracts clean response."""
    raw = "> hello\nHi there!\n>"
    result = parse_response(raw, mode=ParseMode.CONVERSATIONAL)
    assert "Hi there" in result.content
    assert "hello" not in result.content


if __name__ == '__main__':
    # Run tests when executed directly
    print("Running parser tests...")
    print("=" * 60)

    results = run_parser_tests()

    print(f"\nResults: {results['passed']} passed, {results['failed']} failed")

    if results['failures']:
        print("\nFailures:")
        for failure in results['failures']:
            print(f"\n  {failure['name']}:")
            for reason in failure['reasons']:
                print(f"    - {reason}")
            print(f"    Output: {failure['output'][:100]}...")

    print("\n" + "=" * 60)
    print("Test complete!")

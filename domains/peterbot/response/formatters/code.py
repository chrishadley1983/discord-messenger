"""Code Formatter - For code snippets and technical output.

Default behaviour: Summarise what was done (CC has direct file access).
Only show raw code if explicitly requested.
Based on RESPONSE.md Section 5.8.
"""

import re
from typing import Optional


def format_code(text: str, context: Optional[dict] = None) -> str:
    """Format code response for Discord.

    Rules (Section 5.8):
    - Default: Summarise the work, don't dump code
    - Only show code if user explicitly asked
    - Cap code blocks at 30 lines
    - Include language hints for syntax highlighting

    Args:
        text: Text containing code blocks
        context: Optional context with user_prompt

    Returns:
        Formatted text for Discord
    """
    context = context or {}
    user_prompt = context.get('user_prompt', '')

    # Check if user explicitly asked for code
    show_raw = bool(re.search(
        r'show me|see the|raw|output|dump|paste|print|the code|code itself',
        user_prompt,
        re.IGNORECASE
    ))

    if not show_raw:
        # Extract prose/summary, strip code blocks
        prose = extract_prose(text)
        if prose:
            return prose

        # If no prose, generate brief summary
        return summarise_code_actions(text)

    # User wants to see code - format it properly
    return format_code_for_display(text)


def extract_prose(text: str) -> str:
    """Extract non-code content from text."""
    # Remove code blocks
    without_code = re.sub(r'```[\s\S]*?```', '', text)

    # Clean up
    without_code = re.sub(r'\n{3,}', '\n\n', without_code)
    without_code = without_code.strip()

    return without_code


def summarise_code_actions(text: str) -> str:
    """Generate a brief summary of code actions."""
    # Look for common action patterns
    actions = []

    # File operations
    file_patterns = [
        (r'(?:created?|wrote?|writing)\s+(?:file\s+)?[`"\']?([^`"\']+\.(?:py|ts|js|json|md))', 'Created'),
        (r'(?:updated?|modified?|editing?)\s+(?:file\s+)?[`"\']?([^`"\']+\.(?:py|ts|js|json|md))', 'Updated'),
        (r'(?:deleted?|removed?)\s+(?:file\s+)?[`"\']?([^`"\']+\.(?:py|ts|js|json|md))', 'Deleted'),
    ]

    for pattern, action in file_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches[:3]:  # Limit to 3 per action
            actions.append(f"{action} `{match}`")

    # Function/class definitions
    if re.search(r'def\s+\w+|class\s+\w+|function\s+\w+', text):
        actions.append("Added code definitions")

    # If we found actions, summarise them
    if actions:
        return "Done. " + ", ".join(actions[:5]) + "."

    # Fallback
    return "Code updated successfully."


def format_code_for_display(text: str) -> str:
    """Format code blocks for Discord display.

    - Extract code blocks
    - Cap at 30 lines per block
    - Preserve language hints
    - Include surrounding prose
    """
    parts = []
    last_end = 0

    # Find all code blocks
    for match in re.finditer(r'```(\w*)\n([\s\S]*?)```', text):
        # Add prose before this block
        prose = text[last_end:match.start()].strip()
        if prose:
            parts.append(prose)

        lang = match.group(1) or ''
        code = match.group(2)

        # Cap at 30 lines
        lines = code.split('\n')
        if len(lines) > 30:
            code = '\n'.join(lines[:30]) + '\n// ... truncated'

        parts.append(f"```{lang}\n{code}\n```")
        last_end = match.end()

    # Add remaining prose
    remaining = text[last_end:].strip()
    if remaining:
        parts.append(remaining)

    result = '\n\n'.join(parts)

    # Add note if truncated
    if '// ... truncated' in result:
        result += '\n\n-# Full output available in the file'

    return result


def detect_language(code: str) -> str:
    """Attempt to detect code language for syntax highlighting."""
    indicators = {
        'python': [r'^import\s', r'^from\s+\w+\s+import', r'def\s+\w+\(', r'class\s+\w+:'],
        'javascript': [r'^const\s', r'^let\s', r'^var\s', r'=>\s*{', r'function\s+\w+\('],
        'typescript': [r'^interface\s', r'^type\s+\w+\s*=', r':\s*(?:string|number|boolean)'],
        'json': [r'^\s*{', r'^\s*\[', r'"[^"]+"\s*:'],
        'bash': [r'^#!/bin/', r'^\s*\$\s', r'^curl\s', r'^npm\s', r'^pip\s'],
        'sql': [r'^SELECT\s', r'^INSERT\s', r'^UPDATE\s', r'^CREATE\s'],
    }

    for lang, patterns in indicators.items():
        for pattern in patterns:
            if re.search(pattern, code, re.MULTILINE | re.IGNORECASE):
                return lang

    return ''


# =============================================================================
# TESTING
# =============================================================================

def test_code_formatter():
    """Run basic code formatter tests."""
    # Test prose extraction
    text_with_code = """Here's the solution:

```python
def hello():
    print('world')
```

This should fix the issue."""

    prose = extract_prose(text_with_code)
    if 'solution' in prose and '```' not in prose:
        print("✓ PASS - Prose extraction")
    else:
        print("✗ FAIL - Prose extraction")

    # Test code display formatting
    formatted = format_code_for_display(text_with_code)
    if '```python' in formatted:
        print("✓ PASS - Code display formatting")
    else:
        print("✗ FAIL - Code display formatting")

    # Test language detection
    python_code = "import os\ndef main():\n    pass"
    if detect_language(python_code) == 'python':
        print("✓ PASS - Language detection")
    else:
        print("✗ FAIL - Language detection")

    # Test default behaviour (summarise)
    result = format_code(text_with_code, {})
    if '```' not in result or 'solution' in result:
        print("✓ PASS - Default summarise behaviour")
    else:
        print("✗ FAIL - Default summarise behaviour")

    # Test explicit code request
    result = format_code(text_with_code, {'user_prompt': 'show me the code'})
    if '```python' in result:
        print("✓ PASS - Explicit code request")
    else:
        print("✗ FAIL - Explicit code request")

    print("\nCode formatter tests complete")


if __name__ == '__main__':
    test_code_formatter()

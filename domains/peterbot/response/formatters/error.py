"""Error Formatter - For error messages and exceptions.

Shows human-readable summary with optional raw trace for debugging.
Based on RESPONSE.md Section 5.10.
"""

import re
from typing import Optional


def format_error(text: str, context: Optional[dict] = None) -> str:
    """Format error message for Discord.

    Shows both:
    1. Human-readable summary
    2. Raw trace in code block (truncated if long)

    Args:
        text: Error text from CC
        context: Optional context

    Returns:
        Formatted error for Discord
    """
    # Extract user-friendly summary
    summary = extract_error_summary(text)

    # Extract raw trace if present
    trace = extract_error_trace(text)

    # Build result
    result = f"⚠️ {summary}"

    if trace:
        # Truncate long traces
        if len(trace) > 800:
            trace = trace[:800] + '\n... (truncated)'
        result += f"\n\n```\n{trace}\n```"

    return result


def extract_error_summary(text: str) -> str:
    """Extract human-readable error summary."""
    # Look for common error message patterns
    patterns = [
        # "Error: message"
        r'(?:error|exception|failed|failure):\s*(.+?)(?:\n|$)',
        # "Could not / Unable to message"
        r'(?:could not|unable to|cannot|can\'t)\s+(.+?)(?:\n|$)',
        # "X failed: reason"
        r'(\w+)\s+failed:?\s*(.+?)(?:\n|$)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if len(match.groups()) == 1:
                return match.group(1).strip()
            else:
                return f"{match.group(1)} failed: {match.group(2)}".strip()

    # If no pattern matches, use first line
    first_line = text.split('\n')[0].strip()
    if first_line:
        return first_line[:200]  # Cap at 200 chars

    return "An error occurred"


def extract_error_trace(text: str) -> str:
    """Extract stack trace or technical details."""
    # Look for traceback
    traceback_match = re.search(
        r'(?:Traceback|Stack trace|at\s+\S+\s*\()[\s\S]*?(?=\n\n|\Z)',
        text,
        re.IGNORECASE
    )
    if traceback_match:
        return traceback_match.group(0).strip()

    # Look for code block with error details
    code_match = re.search(r'```[\s\S]*?```', text)
    if code_match:
        return code_match.group(0).strip('`').strip()

    # Look for indented error details
    indent_match = re.search(r'(?:^[ \t]+.+\n)+', text, re.MULTILINE)
    if indent_match:
        return indent_match.group(0).strip()

    return ''


def format_api_error(status_code: int, message: str, endpoint: str = '') -> str:
    """Format API error response."""
    status_texts = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        429: "Rate Limited",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
    }

    status_text = status_texts.get(status_code, "Error")
    endpoint_text = f" ({endpoint})" if endpoint else ""

    return f"⚠️ {status_text}{endpoint_text}: {message}"


def format_timeout_error(operation: str, duration_seconds: int) -> str:
    """Format timeout error."""
    return f"⚠️ {operation} timed out after {duration_seconds} seconds"


def format_connection_error(service: str) -> str:
    """Format connection error."""
    return f"⚠️ Could not connect to {service}. The service may be temporarily unavailable."


# =============================================================================
# TESTING
# =============================================================================

def test_error_formatter():
    """Run basic error formatter tests."""
    # Test error with traceback
    error_text = """Error: Database connection failed

Traceback (most recent call last):
  File "app.py", line 42, in connect
    db.connect()
  File "db.py", line 15, in connect
    raise ConnectionError("timeout")
ConnectionError: timeout"""

    result = format_error(error_text)

    if '⚠️' in result and 'Database' in result and '```' in result:
        print("✓ PASS - Error with traceback")
    else:
        print("✗ FAIL - Error with traceback")
        print(f"  Result: {result[:100]}")

    # Test simple error
    simple_error = "Could not fetch weather data"
    result = format_error(simple_error)

    if '⚠️' in result and 'weather' in result:
        print("✓ PASS - Simple error")
    else:
        print("✗ FAIL - Simple error")

    # Test API error
    result = format_api_error(404, "User not found", "/api/users/123")

    if '404' not in result and 'Not Found' in result:
        print("✓ PASS - API error format")
    else:
        print("✗ FAIL - API error format")

    print("\nError formatter tests complete")


if __name__ == '__main__':
    test_error_formatter()

"""Log sanitizer - removes sensitive data from log messages.

Prevents PII and credentials from being written to log files.
"""

import re
from typing import Union

# Patterns to detect and redact sensitive data
SENSITIVE_PATTERNS = [
    # Email addresses
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),

    # UK phone numbers (various formats)
    (r'\b(?:\+44|0)[\s.-]?\d{2,4}[\s.-]?\d{3,4}[\s.-]?\d{3,4}\b', '[PHONE]'),

    # US phone numbers
    (r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE]'),

    # Credit card numbers (basic pattern)
    (r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '[CARD]'),

    # API keys, tokens, secrets in key=value format
    (r'(password|secret|token|api_key|apikey|auth|bearer|credential)["\s:=]+[^\s,}"\']{8,}',
     r'\1=[REDACTED]'),

    # Bearer tokens
    (r'(Bearer|Basic)\s+[A-Za-z0-9\-_\.]+', r'\1 [REDACTED]'),

    # JWT tokens (three base64 segments separated by dots)
    (r'eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+', '[JWT_TOKEN]'),

    # AWS-style keys
    (r'AKIA[0-9A-Z]{16}', '[AWS_KEY]'),

    # Generic long alphanumeric strings that look like keys (40+ chars)
    (r'\b[A-Za-z0-9]{40,}\b', '[LONG_TOKEN]'),

    # UK National Insurance numbers
    (r'\b[A-Z]{2}\d{6}[A-Z]\b', '[NI_NUMBER]'),

    # UK postcodes (be careful not to over-match)
    (r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b', '[POSTCODE]'),
]

# Compiled patterns for efficiency
_COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE), r) for p, r in SENSITIVE_PATTERNS]


def sanitize_log(text: str) -> str:
    """Remove sensitive data from text for safe logging.

    Args:
        text: The text to sanitize

    Returns:
        Sanitized text with sensitive data replaced by placeholders
    """
    if not text:
        return text

    result = text
    for pattern, replacement in _COMPILED_PATTERNS:
        result = pattern.sub(replacement, result)

    return result


def sanitize_for_log(value: Union[str, bytes, None], max_length: int = 200) -> str:
    """Sanitize and truncate a value for logging.

    Args:
        value: The value to sanitize (string or bytes)
        max_length: Maximum length of returned string

    Returns:
        Sanitized, truncated string safe for logging
    """
    if value is None:
        return "<None>"

    if isinstance(value, bytes):
        try:
            text = value.decode('utf-8', errors='replace')
        except Exception:
            return f"<{len(value)} bytes>"
    else:
        text = str(value)

    # Sanitize first
    sanitized = sanitize_log(text)

    # Truncate if needed
    if len(sanitized) > max_length:
        return sanitized[:max_length] + f"... [{len(text)} chars total]"

    return sanitized

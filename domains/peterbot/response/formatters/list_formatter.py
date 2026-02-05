"""List Formatter - For ordered and unordered lists.

Ensures lists are properly formatted for Discord.
Based on RESPONSE.md Section 5.2 and 9.1.
"""

import re
from typing import Optional


def format_list(text: str, context: Optional[dict] = None) -> str:
    """Format list content for Discord.

    Rules:
    - Use Discord list format: `- item` or `1. item`
    - Keep list items to one line where possible
    - Limit to 10 items unless more are specifically requested
    - Clean up inconsistent list formatting

    Args:
        text: Text containing lists
        context: Optional context

    Returns:
        Cleaned list for Discord
    """
    # Normalize list markers
    text = normalize_list_markers(text)

    # Optionally limit items
    max_items = context.get('max_items', 10) if context else 10
    if max_items:
        text = limit_list_items(text, max_items)

    # Clean up spacing
    text = clean_list_spacing(text)

    return text


def normalize_list_markers(text: str) -> str:
    """Normalize inconsistent list markers to standard format."""
    # Replace various bullet characters with standard dash
    text = re.sub(r'^[\s]*[•●○◦▪▸►]\s*', '- ', text, flags=re.MULTILINE)

    # Normalize numbered lists (1), 1:, 1 - to 1.
    text = re.sub(r'^[\s]*(\d+)[):\-]\s*', r'\1. ', text, flags=re.MULTILINE)

    return text


def limit_list_items(text: str, max_items: int) -> str:
    """Limit the number of list items shown."""
    lines = text.split('\n')
    result_lines = []
    item_count = 0
    in_list = False

    for line in lines:
        is_list_item = bool(re.match(r'^[\s]*[-*]\s|^[\s]*\d+\.\s', line))

        if is_list_item:
            in_list = True
            item_count += 1

            if item_count <= max_items:
                result_lines.append(line)
            elif item_count == max_items + 1:
                # Add "and X more" indicator
                remaining = count_remaining_items(lines[lines.index(line):])
                if remaining > 0:
                    result_lines.append(f"  ... and {remaining} more")
        else:
            if not in_list or line.strip():
                result_lines.append(line)
            if not is_list_item and line.strip():
                in_list = False
                item_count = 0

    return '\n'.join(result_lines)


def count_remaining_items(lines: list[str]) -> int:
    """Count remaining list items."""
    count = 0
    for line in lines:
        if re.match(r'^[\s]*[-*]\s|^[\s]*\d+\.\s', line):
            count += 1
    return count


def clean_list_spacing(text: str) -> str:
    """Clean up list spacing for Discord readability."""
    # Remove excessive indentation
    text = re.sub(r'^[ \t]{4,}([-*])', r'  \1', text, flags=re.MULTILINE)

    # Ensure single newline between list items
    text = re.sub(r'(^[-*]\s.+)\n\n([-*]\s)', r'\1\n\2', text, flags=re.MULTILINE)

    # Ensure blank line before list starts
    text = re.sub(r'([^\n])\n([-*]\s)', r'\1\n\n\2', text)

    return text


def extract_list_items(text: str) -> list[str]:
    """Extract list items from text."""
    items = []

    # Find bullet items
    bullet_matches = re.findall(r'^[\s]*[-*•]\s*(.+)$', text, re.MULTILINE)
    items.extend(bullet_matches)

    # Find numbered items
    numbered_matches = re.findall(r'^[\s]*\d+[.)]\s*(.+)$', text, re.MULTILINE)
    items.extend(numbered_matches)

    return items


def is_list_heavy(text: str) -> bool:
    """Check if text is primarily a list."""
    items = extract_list_items(text)
    lines = [l for l in text.split('\n') if l.strip()]

    if not lines:
        return False

    return len(items) / len(lines) > 0.5


def format_as_bullet_list(items: list[str]) -> str:
    """Format items as a bullet list."""
    return '\n'.join(f'- {item}' for item in items)


def format_as_numbered_list(items: list[str]) -> str:
    """Format items as a numbered list."""
    return '\n'.join(f'{i + 1}. {item}' for i, item in enumerate(items))


# =============================================================================
# TESTING
# =============================================================================

def test_list_formatter():
    """Run basic list formatter tests."""
    # Test marker normalization
    text = """Things to do:
• First item
• Second item
• Third item"""

    result = normalize_list_markers(text)
    if '- First item' in result and '•' not in result:
        print("✓ PASS - Marker normalization")
    else:
        print("✗ FAIL - Marker normalization")

    # Test numbered list normalization
    text = """Steps:
1) First step
2) Second step
3: Third step"""

    result = normalize_list_markers(text)
    if '1. First step' in result:
        print("✓ PASS - Numbered list normalization")
    else:
        print("✗ FAIL - Numbered list normalization")

    # Test item limiting
    text = '\n'.join([f'- Item {i}' for i in range(15)])
    result = limit_list_items(text, 10)

    if '- Item 9' in result and '- Item 14' not in result:
        print("✓ PASS - Item limiting")
    else:
        print("✗ FAIL - Item limiting")

    # Test item extraction
    text = """Here's a list:
- Apple
- Banana
- Cherry"""

    items = extract_list_items(text)
    if len(items) == 3 and 'Apple' in items:
        print("✓ PASS - Item extraction")
    else:
        print("✗ FAIL - Item extraction")

    print("\nList formatter tests complete")


if __name__ == '__main__':
    test_list_formatter()

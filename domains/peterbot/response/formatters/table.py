"""Table Formatter - Converts markdown tables to Discord-friendly formats.

Discord cannot render markdown tables, so we convert them to:
- Code blocks (for data tables)
- Prose (for comparison tables)
- Embed fields (for small tables, when embeds used)

Based on RESPONSE.md Section 5.3.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedTable:
    """Parsed markdown table structure."""
    headers: list[str]
    rows: list[list[str]]
    raw_text: str

    @property
    def col_count(self) -> int:
        return len(self.headers)

    @property
    def row_count(self) -> int:
        return len(self.rows)


def parse_markdown_table(text: str) -> Optional[ParsedTable]:
    """Parse a markdown table from text.

    Expects format:
    | Header1 | Header2 |
    |---------|---------|
    | Cell1   | Cell2   |

    Returns ParsedTable or None if no valid table found.
    """
    # Find table pattern
    table_pattern = re.compile(
        r'(\|[^\n]+\|\n)'           # Header row
        r'(\|[-:\s|]+\|\n)'          # Separator row
        r'((?:\|[^\n]+\|\n?)+)',     # Data rows
        re.MULTILINE
    )

    match = table_pattern.search(text)
    if not match:
        return None

    header_line = match.group(1).strip()
    # separator_line = match.group(2).strip()  # Not needed
    data_lines = match.group(3).strip()

    # Parse headers
    headers = [
        cell.strip()
        for cell in header_line.strip('|').split('|')
    ]

    # Parse rows
    rows = []
    for line in data_lines.split('\n'):
        if line.strip():
            cells = [
                cell.strip()
                for cell in line.strip('|').split('|')
            ]
            # Pad or trim to match header count
            while len(cells) < len(headers):
                cells.append('')
            cells = cells[:len(headers)]
            rows.append(cells)

    return ParsedTable(
        headers=headers,
        rows=rows,
        raw_text=match.group(0)
    )


def format_table(text: str, context: Optional[dict] = None) -> str:
    """Format text containing markdown tables for Discord.

    Strategy selection (Section 5.3):
    - Small tables (≤4 cols, ≤6 rows): Code block
    - Large tables (>4 cols or >6 rows): Code block
    - 2-3 col comparison: Prose conversion

    Args:
        text: Text potentially containing markdown tables
        context: Optional context

    Returns:
        Text with tables converted to Discord-friendly format
    """
    result = text

    # Find and replace all markdown tables
    while True:
        table = parse_markdown_table(result)
        if not table:
            break

        # Choose rendering strategy
        if table.col_count <= 3 and is_comparison_table(table):
            replacement = table_to_prose(table)
        else:
            replacement = table_to_code_block(table)

        result = result.replace(table.raw_text, replacement)

    return result


def table_to_code_block(table: ParsedTable) -> str:
    """Render table as fixed-width code block.

    Uses box-drawing characters for clean display.
    Based on Section 5.3 Strategy B.
    """
    # Calculate column widths
    col_widths = []
    for i, header in enumerate(table.headers):
        max_width = len(header)
        for row in table.rows:
            if i < len(row):
                max_width = max(max_width, len(row[i]))
        col_widths.append(max(max_width, 3))  # Minimum 3 chars

    # Build the table
    lines = []

    # Header
    header_cells = [
        table.headers[i].ljust(col_widths[i])
        for i in range(len(table.headers))
    ]
    lines.append(' │ '.join(header_cells))

    # Separator
    separator = '─┼─'.join('─' * w for w in col_widths)
    lines.append(separator)

    # Rows
    for row in table.rows:
        cells = [
            (row[i] if i < len(row) else '').ljust(col_widths[i])
            for i in range(len(table.headers))
        ]
        lines.append(' │ '.join(cells))

    return '```\n' + '\n'.join(lines) + '\n```'


def table_to_prose(table: ParsedTable) -> str:
    """Convert comparison table to readable prose.

    For 2-3 column tables comparing options.
    Based on Section 5.3 Strategy C.
    """
    lines = []

    for row in table.rows:
        if len(row) >= 2:
            # First column is typically the item name
            name = row[0]
            details = ', '.join(row[1:])
            lines.append(f"**{name}**: {details}")

    return '\n'.join(lines)


def is_comparison_table(table: ParsedTable) -> bool:
    """Check if table is a comparison-style table.

    Comparison tables typically have:
    - 2-3 columns
    - First column is item names
    - Other columns are attributes
    """
    if table.col_count < 2 or table.col_count > 3:
        return False

    # Check if first column looks like item names
    first_col = [row[0] for row in table.rows if row]

    # Item names are typically short and don't look like data
    short_names = all(len(name) < 30 for name in first_col)
    not_numeric = all(not name.replace('.', '').isdigit() for name in first_col)

    return short_names and not_numeric


def table_to_embed_fields(table: ParsedTable) -> list[dict]:
    """Convert table to Discord embed field format.

    For use when response uses embeds.
    Returns list of field dicts with name, value, inline.
    """
    fields = []

    for row in table.rows:
        for i, cell in enumerate(row):
            if i < len(table.headers):
                fields.append({
                    'name': table.headers[i],
                    'value': cell or '\u200b',  # Zero-width space if empty
                    'inline': True
                })

    return fields


# =============================================================================
# TESTING
# =============================================================================

def test_table_formatter():
    """Run basic table formatter tests."""
    test_cases = [
        # Simple table
        (
            "| Name | Value |\n|------|-------|\n| Foo  | 10    |\n| Bar  | 20    |",
            True,  # Should contain code block
        ),

        # Text with embedded table
        (
            "Here are the results:\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nEnd.",
            True,
        ),
    ]

    passed = 0
    failed = 0

    for input_text, should_have_code_block in test_cases:
        result = format_table(input_text)

        # Should not have raw markdown table
        has_raw_table = '|---' in result or '|--' in result
        has_code_block = '```' in result

        if not has_raw_table and (has_code_block == should_have_code_block):
            passed += 1
            print(f"✓ PASS")
        else:
            failed += 1
            print(f"✗ FAIL")
            print(f"  Has raw table: {has_raw_table}")
            print(f"  Has code block: {has_code_block}")
            print(f"  Result: {result[:100]}")

    # Test table parsing
    table_text = "| Col1 | Col2 |\n|------|------|\n| A | B |\n| C | D |"
    table = parse_markdown_table(table_text)

    if table and table.headers == ['Col1', 'Col2'] and table.row_count == 2:
        passed += 1
        print("✓ PASS - Table parsing")
    else:
        failed += 1
        print("✗ FAIL - Table parsing")

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == '__main__':
    test_table_formatter()

"""Robust Claude Code response parser for Peterbot.

Designed for extensibility and comprehensive pattern handling.
Processes Claude Code tmux screen captures to extract clean responses.

Architecture:
    1. PATTERNS - Organized by category for maintainability
    2. PHASES - Multi-stage processing pipeline
    3. MODES - Different extraction modes (conversational, technical, raw)
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ParseMode(Enum):
    """Response extraction modes."""
    CONVERSATIONAL = "conversational"  # Clean response for Discord users
    TECHNICAL = "technical"           # Include more detail (API responses, JSON)
    RAW = "raw"                       # Minimal filtering, debug mode


@dataclass
class ParseResult:
    """Parsed response with metadata."""
    content: str
    mode: ParseMode
    lines_processed: int
    lines_kept: int
    patterns_matched: dict[str, int]  # Pattern category -> match count


# =============================================================================
# PATTERN DEFINITIONS - Organized by category
# =============================================================================

# UI Elements - Claude Code interface artifacts
UI_PATTERNS = {
    # Prompt markers (start of user input)
    'prompt_marker': re.compile(r'^[>❯]\s*'),

    # Status spinners and indicators
    'status_spinner': re.compile(r'^[✻✢✽✓✗⏵✶▘⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]'),

    # Nested output marker
    'nested_marker': re.compile(r'^⎿'),

    # Bullet point (Claude Code formatting) - used for CLEANING, not filtering
    # (moved to clean_line, kept here for reference)
    'bullet': re.compile(r'^●\s*'),

    # Standalone bullet with no content (filter these)
    'empty_bullet': re.compile(r'^●\s*$'),

    # Keyboard shortcuts and hints
    'keyboard_hint': re.compile(r'ctrl[+-]|shift[+-]tab|\? for shortcuts', re.I),

    # Token/cost status
    'token_status': re.compile(r'^\s*\d+[kK]?\s*(tokens?|input|output)', re.I),
    'cost_line': re.compile(r'(cost|tokens)\s*:\s*[\$\d]', re.I),
    'creating_tokens': re.compile(r'Creating.*\(\d+[kK]?\s*tokens?\)', re.I),

    # Claude Code header/version
    'version_header': re.compile(r'claude code v|claude\.ai|anthropic', re.I),
    'model_line': re.compile(r'\b(opus|sonnet|haiku)\b.*claude', re.I),
    'path_line': re.compile(r'^~/\w+\s*$'),

    # Thinking/processing indicators (with timing) - use word stems that work for both -ing and -ed
    'thinking_status': re.compile(
        r'(Churn|Work|Cogitat|Contemplat|Cerebrat|Levitat|Medit|Ponder|Idealiz|Ruminat)\w*\s+(for\s*)?\d+\s*(seconds?|s\b)', re.I
    ),
    'thinking_simple': re.compile(r'^\s*(thinking|Processing|Working|Creating)\.{0,3}\s*$', re.I),

    # Standalone thinking verbs (with or without ellipsis)
    'thinking_verbs': re.compile(
        r'^(Pondering|Ruminating|Meditating|Contemplating|Cerebrating|'
        r'Pondered|Ruminated|Meditated|Contemplated|Cerebrated|'
        r'Idealizing|Idealized|Levitating|Levitated)\.{0,3}\s*$', re.I
    ),

    # Hook messages
    'hook_message': re.compile(r'(Ran|Read)\s*\d+\s*(hook|file|tool)', re.I),
    'hook_count': re.compile(r'^\d+\s*(stop|start)?\s*hooks?', re.I),
    'hook_error': re.compile(r'hook error', re.I),

    # Feedback prompt
    'feedback_prompt': re.compile(r'how is claude doing|^\d:\s*(bad|fine|good|dismiss)', re.I),
    'feedback_options': re.compile(r'(1:\s*bad|2:\s*fine|3:\s*good|0:\s*dismiss)', re.I),

    # Session info
    'session_info': re.compile(r'\(optional\).*session|session\s*\(optional\)', re.I),

    # Search status
    'search_status': re.compile(r'Did\s*\d+\s*search', re.I),
}

# Tool Call Patterns - Claude Code tool invocations
TOOL_PATTERNS = {
    # Tool call headers (with parentheses)
    'tool_call': re.compile(
        r'^(Web\s*Search|Web\s*Fetch|Fetch|Bash|Read|Write|Edit|Update|Grep|Glob|Skill|Task|'
        r'MultiTool|NotebookEdit|ListFiles|AskUser|TodoRead|TodoWrite)\s*\(', re.I
    ),

    # MCP tool invocations (mcp__provider__method format)
    'mcp_tool_call': re.compile(r'mcp__[a-z0-9_-]+__[a-z0-9_-]+', re.I),

    # MCP tool provider labels ("brave-search - Brave Web Search (MCP)" format)
    'mcp_provider': re.compile(r'^[\w-]+\s+-\s+[\w\s]+\(MCP\)', re.I),

    # Tool loading messages
    'tool_loaded': re.compile(r'loaded skill|skill loaded', re.I),

    # Curl commands (often from Bash tool output)
    'curl_command': re.compile(r'curl\s+-?s?\s+', re.I),

    # Tool call continuation fragments
    'tool_fragment': re.compile(r'^[a-z_]+\s*=\s*["\']'),  # param="value" fragments

    # URL-encoded API fragments (from MCP tool parameters)
    'url_encoded_fragment': re.compile(r'%[0-9A-F]{2}.*%[0-9A-F]{2}', re.I),
}

# JSON/API Noise - Partial API responses and JSON fragments
JSON_PATTERNS = {
    # JSON field patterns (query, count, id, url, etc.)
    'json_field': re.compile(r'^"(query|count|id|url|http|limit|offset|page|size|total)"?\s*:'),

    # JSON numeric fields
    'json_numeric': re.compile(r'^"[^"]+"\s*:\s*\d+,?\s*$'),

    # Quoted URLs
    'json_url': re.compile(r'^"https?://[^"]*"'),

    # JSON fragment lines (quoted string with comma)
    'json_fragment': re.compile(r'^"[^"]*",?\s*$'),

    # API error responses
    'api_error': re.compile(r'"(detail|error|message|status)"\s*:\s*"'),

    # API metadata fields
    'api_metadata': re.compile(r'(fetched_at|created_at|updated_at|_at"|_wh"|_kw"|_km"|timestamp)'),
}

# Bash/Shell Noise - Command fragments and redirections
BASH_PATTERNS = {
    # Redirections
    'redirect': re.compile(r'2>/dev/null|>/dev/null|2>&1'),

    # Command substitution fragments
    'cmd_subst': re.compile(r'\$\([^)]*$'),  # Unclosed $(

    # Pipe/chain fragments (but not markdown tables which have multiple |)
    'pipe_fragment': re.compile(r'^\s*\|\s*\w+[^|]*$'),  # Must not have another | (tables do)

    # URL-encoded fragments (often from API calls)
    'url_encoded': re.compile(r'^[a-z]+\+[a-z]+', re.I),  # "terham+CR3" style

    # Query parameter fragments
    'query_param': re.compile(r'^[a-z_]+=[A-Za-z0-9,+%]+$'),  # "destinations=London,Brighton"
}

# Code/Diff Patterns - Code editing artifacts
CODE_PATTERNS = {
    # Diff markers with line numbers
    'diff_line': re.compile(r'^\d+\s*[-+]\s*(from|import|def|class|if|for|while|return|#|\w+\s*=)'),

    # Pure diff markers (but not markdown lists)
    'diff_marker': re.compile(r'^[+-](?![- ])'),  # +/- not followed by space (not lists)

    # Line numbers with code
    'numbered_code': re.compile(r'^\d+\s+(from|import|def|class|async|@|if|for|while|return|#)'),

    # File paths in code context
    'code_path': re.compile(r'^(src|lib|app|tests?|components?|utils?)/'),

    # Edit tool output (unchanged lines)
    'unchanged_line': re.compile(r'^\d+\s+unchanged\s+line', re.I),
}

# Context Artifacts - From our context injection
CONTEXT_PATTERNS = {
    # Context file references
    'context_ref': re.compile(r'context\.md|Read context\.md', re.I),

    # Section markers from context (with or without colon)
    'section_marker': re.compile(r'^(Current Message|Memory Context|Recent Conversation):?\s*$', re.I),

    # Memory context content lines (bullet points with user info)
    'memory_content': re.compile(r'^-\s*(User|Last|Previously|They|He|She|Chris)\s+(likes?|talked|said|mentioned|prefers?|wants?)', re.I),

    # Section separators
    'section_separator': re.compile(r'^---+\s*$'),

    # Prompt instructions bleed-through
    'prompt_bleed': re.compile(r'respond to (the )?user|latest message', re.I),
}

# Search/Fetch Noise - Always filtered (even in TECHNICAL mode)
# These are orphaned fragments from tool blocks that escape _strip_tool_blocks
# when tmux line wrapping breaks the ● marker detection
SEARCH_NOISE_PATTERNS = {
    # Search API metadata fields (from SearXNG/Brave tool params)
    'search_metadata': re.compile(
        r'^\s*(safesearch|freshness|time_range|count|page_no|categories)\s*:', re.I
    ),

    # Bare URL path fragments - hyphenated slug with extension, no spaces
    # e.g., "ooked-chilli-pulled-pork", "spur-news-073000721.html"
    'url_path_fragment': re.compile(
        r'^[a-z0-9][a-z0-9-]{10,}(?:\.html?|\.php|\.aspx)?\s*$', re.I
    ),

    # URL with path but no protocol (truncated from wrapped line)
    # e.g., "www.bbc.co.uk/sport/football/..." or "example.com/path/to/page"
    'bare_url': re.compile(
        r'^(?:www\.)?[\w.-]+\.(?:com|co\.uk|org|net|io|gov|edu|ac\.uk)/\S+$', re.I
    ),

    # Search result numbering with URL (from result list output)
    # e.g., "1. https://example.com/page"
    'numbered_url': re.compile(r'^\d+\.\s*https?://\S+\s*$'),

    # Orphaned query parameters (from wrapped search calls)
    # e.g., 'query: "slow cooked...' or 'q=pulled+pork'
    'orphaned_query': re.compile(r'^(query|q)\s*[:=]\s*["\']', re.I),

    # Standalone quoted URL (from JSON result objects)
    'quoted_url_line': re.compile(r'^\s*"https?://[^"]+"\s*,?\s*$'),
}

# Compaction/Interview - Special Claude Code modes
SPECIAL_PATTERNS = {
    # Compaction notice
    'compaction': re.compile(r'conversation.*compacted|context.*compacted|summariz', re.I),

    # Interview question format (numbered options with brackets)
    'interview_option': re.compile(r'^\s*\d+\.\s+\[.*\]'),  # "1. [Option A]"

    # Interview header/prompts
    'interview_header': re.compile(r'(choose|select|pick)\s*(an?\s*)?(option|answer|one)', re.I),

    # Interview action prompts
    'interview_action': re.compile(r'^(Select|Choose|Pick)\s+one\s+to\s+continue', re.I),

    # Please choose prompts
    'please_choose': re.compile(r'^Please\s+(choose|select|pick)', re.I),
}


# =============================================================================
# PARSER IMPLEMENTATION
# =============================================================================

def should_skip_line(line: str, stripped: str, mode: ParseMode, stats: dict) -> bool:
    """Determine if a line should be filtered out.

    Args:
        line: Original line with whitespace
        stripped: Line with whitespace stripped
        mode: Parsing mode (affects filtering strictness)
        stats: Dict to track pattern match statistics

    Returns:
        True if line should be skipped
    """
    if not stripped:
        return False  # Keep blank lines for formatting (will be handled later)

    # Pre-clean: Remove bullet prefix for pattern matching
    clean_stripped = UI_PATTERNS['bullet'].sub('', stripped).strip()

    # Always filter: UI elements (except bullet and prompt_marker which are cleaned, not filtered)
    for name, pattern in UI_PATTERNS.items():
        # Skip bullet pattern - we clean these, not filter them
        if name == 'bullet':
            continue
        # Skip prompt_marker - these are handled by boundary detection, not line filtering
        # (allows markdown blockquotes like "> quote" to pass through)
        if name == 'prompt_marker':
            continue
        if pattern.search(stripped) or pattern.search(line) or pattern.search(clean_stripped):
            stats[f'ui:{name}'] = stats.get(f'ui:{name}', 0) + 1
            return True

    # Always filter: Tool calls (check both original and bullet-cleaned)
    for name, pattern in TOOL_PATTERNS.items():
        if pattern.search(stripped) or pattern.search(clean_stripped):
            stats[f'tool:{name}'] = stats.get(f'tool:{name}', 0) + 1
            return True

    # Always filter: Bash noise
    for name, pattern in BASH_PATTERNS.items():
        if pattern.search(stripped):
            stats[f'bash:{name}'] = stats.get(f'bash:{name}', 0) + 1
            return True

    # Always filter: Context artifacts
    for name, pattern in CONTEXT_PATTERNS.items():
        if pattern.search(stripped):
            stats[f'context:{name}'] = stats.get(f'context:{name}', 0) + 1
            return True

    # Always filter: Search/fetch noise (orphaned fragments from tool blocks)
    for name, pattern in SEARCH_NOISE_PATTERNS.items():
        if pattern.search(stripped) or pattern.search(clean_stripped):
            stats[f'search:{name}'] = stats.get(f'search:{name}', 0) + 1
            return True

    # Mode-dependent: JSON noise
    if mode != ParseMode.TECHNICAL:
        for name, pattern in JSON_PATTERNS.items():
            if pattern.search(stripped):
                stats[f'json:{name}'] = stats.get(f'json:{name}', 0) + 1
                return True

    # Mode-dependent: Code/diff output
    if mode == ParseMode.CONVERSATIONAL:
        for name, pattern in CODE_PATTERNS.items():
            if pattern.match(stripped):
                stats[f'code:{name}'] = stats.get(f'code:{name}', 0) + 1
                return True

    # Special patterns (always filter in conversational)
    if mode == ParseMode.CONVERSATIONAL:
        for name, pattern in SPECIAL_PATTERNS.items():
            if pattern.search(stripped):
                stats[f'special:{name}'] = stats.get(f'special:{name}', 0) + 1
                return True

    return False


def clean_line(line: str) -> str:
    """Clean a single line of response content.

    Args:
        line: Line to clean

    Returns:
        Cleaned line
    """
    # Remove bullet points (Claude Code formatting)
    cleaned = UI_PATTERNS['bullet'].sub('', line.strip())

    # NOTE: Don't remove prompt markers (>) here - they might be markdown blockquotes
    # Actual prompts are filtered out by find_response_boundaries

    # Remove spinner characters
    cleaned = UI_PATTERNS['status_spinner'].sub('', cleaned)

    return cleaned.strip()


def find_response_boundaries(lines: list[str]) -> tuple[int, int]:
    """Find the start and end of Claude's actual response.

    Distinguishes between:
    - User prompts: `> user input` or standalone `>` / `❯`
    - Markdown blockquotes: `> quoted text` within a response

    Heuristics:
    - First `>` with content = user prompt (start of response after it)
    - Standalone `>` or `❯` with no/minimal content = end of response
    - `>` within response content = markdown blockquote (keep it)

    Args:
        lines: All screen lines

    Returns:
        (start_index, end_index) of response content
    """
    start_idx = 0
    end_idx = len(lines)

    # Find the FIRST prompt (user input) - this marks start of response
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Our specific context prompt takes priority (supports dynamic filenames)
        if 'Read context' in line and 'and respond' in line:
            start_idx = i + 1
            break
        # User prompt: > or ❯ with some content (not just the symbol)
        if (stripped.startswith('>') or stripped.startswith('❯')) and len(stripped) > 2:
            start_idx = i + 1
            break

    # Find the END prompt - standalone > or ❯ with no content
    # Search backwards from end to find the closing prompt
    for i in range(len(lines) - 1, start_idx, -1):
        stripped = lines[i].strip()
        # Standalone prompt marker (empty or just the symbol)
        if stripped in ('>', '❯', '> ', '❯ '):
            end_idx = i
            break
        # Also check for prompt with just whitespace after
        if stripped.startswith('>') or stripped.startswith('❯'):
            content_after_prompt = stripped.lstrip('>❯').strip()
            # If very short content after >, probably a closing prompt being typed
            if len(content_after_prompt) < 3:
                end_idx = i
                break

    return start_idx, end_idx


def dedupe_lines(lines: list[str]) -> list[str]:
    """Remove duplicate consecutive lines and paragraphs.

    Args:
        lines: Cleaned lines

    Returns:
        Deduplicated lines
    """
    if not lines:
        return lines

    result = []
    seen_content = set()

    for line in lines:
        stripped = line.strip()

        # Always allow blank lines (for paragraph breaks)
        if not stripped:
            # But don't allow multiple consecutive blanks
            if result and result[-1].strip():
                result.append('')
            continue

        # Skip exact duplicates
        if stripped in seen_content:
            continue

        # Skip if very similar to previous (fuzzy dedupe)
        if result:
            last = result[-1].strip()
            if last and stripped and _similarity(last, stripped) > 0.9:
                continue

        seen_content.add(stripped)
        result.append(line)

    return result


def _similarity(a: str, b: str) -> float:
    """Simple similarity ratio between two strings."""
    if not a or not b:
        return 0.0

    # Quick length check
    len_ratio = min(len(a), len(b)) / max(len(a), len(b))
    if len_ratio < 0.8:
        return len_ratio

    # Word overlap
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())

    if not words_a or not words_b:
        return len_ratio

    intersection = len(words_a & words_b)
    union = len(words_a | words_b)

    return intersection / union if union > 0 else 0.0


def collapse_blank_lines(text: str) -> str:
    """Collapse multiple blank lines into single blank lines."""
    return re.sub(r'\n{3,}', '\n\n', text)


def ensure_paragraph_spacing(text: str) -> str:
    """Ensure paragraphs have double line breaks for readability.

    Adds extra spacing between:
    - After headers (lines starting with #)
    - Between regular paragraphs (non-list, non-code content)
    - After code blocks
    """
    lines = text.split('\n')
    result = []
    prev_was_content = False
    in_code_block = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Track code blocks
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            result.append(line)
            prev_was_content = False
            continue

        # Inside code block - keep as is
        if in_code_block:
            result.append(line)
            continue

        # Empty line - keep one
        if not stripped:
            if result and result[-1].strip():  # Only if previous wasn't empty
                result.append('')
            prev_was_content = False
            continue

        # Check if this is a "paragraph start" (not a list item, not a header continuation)
        is_list_item = stripped.startswith(('-', '*', '•')) or re.match(r'^\d+\.', stripped)
        is_header = stripped.startswith('#')
        is_table = stripped.startswith('|')

        # If previous was content and this is new paragraph start, add extra spacing
        if prev_was_content and not is_list_item and not is_table:
            # Add blank line before new paragraphs
            if result and result[-1].strip():
                result.append('')

        result.append(line)
        prev_was_content = bool(stripped) and not is_header

    return '\n'.join(result)


def find_new_content_start(before_lines: list[str], after_lines: list[str]) -> int:
    """Find where new content starts by comparing screen states.

    Instead of set-based diff (which loses context), we find the divergence point
    between before and after screens, then look for the response after that.

    Args:
        before_lines: Lines from screen before sending prompt
        after_lines: Lines from screen after receiving response

    Returns:
        Index in after_lines where new content starts
    """
    # Strategy: Find where the "Read context*.md and respond" prompt appears in after
    # Everything after that is the new response
    # Note: Scheduler uses dynamic filenames like "context_5ee37dcd.md"
    for i, line in enumerate(after_lines):
        if 'Read context' in line and 'and respond' in line:
            return i + 1

    # Fallback: Find last prompt marker (> or ❯) that has content after it
    # This marks the user's input, response follows
    last_prompt_with_content = 0
    for i, line in enumerate(after_lines):
        stripped = line.strip()
        if (stripped.startswith('>') or stripped.startswith('❯')) and len(stripped) > 2:
            last_prompt_with_content = i + 1

    # If we found a prompt, start after it
    if last_prompt_with_content > 0:
        return last_prompt_with_content

    # Last resort: Find where after diverges from before (suffix matching)
    # Start from the end and work backwards to find common suffix
    min_len = min(len(before_lines), len(after_lines))
    common_suffix_len = 0
    for i in range(1, min_len + 1):
        if before_lines[-i] == after_lines[-i]:
            common_suffix_len += 1
        else:
            break

    # The new content is everything except the common suffix
    if common_suffix_len > 0:
        return max(0, len(after_lines) - common_suffix_len - 50)  # Include buffer

    return 0


# Tool block detection patterns (for multi-line block filtering)
_TOOL_BLOCK_STARTERS = re.compile(
    r'^●\s*('
    r'Read\s+\d+\s+file|'                    # ● Read 1 file (ctrl+o...)
    r'Bash\s*\(|'                              # ● Bash(command...)
    r'Fetch\s*\(|'                             # ● Fetch(https://...)
    r'Web\s*Search|Web\s*Fetch|'               # ● WebSearch(...) / WebFetch(...)
    r'Read\s*\(|Write\s*\(|Edit\s*\(|'         # ● Read/Write/Edit(...)
    r'Grep\s*\(|Glob\s*\(|'                    # ● Grep/Glob(...)
    r'[\w-]+\s+-\s+[\w\s_]+\(MCP\)|'           # ● searxng - web_search (MCP)
    r'mcp__'                                    # ● mcp__provider__method
    r')', re.I
)

_TOOL_RESULT_LINE = re.compile(r'^\s*⎿')
_INTERRUPTED_LINE = re.compile(r'Interrupted|What should Claude do', re.I)
_EXPAND_LINE = re.compile(r'ctrl\+o|lines?\s*\(ctrl', re.I)
_TIMING_LINE = re.compile(
    r'^(✻|✢|✽)\s*\w+.*\d+\s*(seconds?|s\b|ms\b|m\s+\d+s)',
    re.I
)
_RECEIVED_LINE = re.compile(r'Received\s+[\d.]+[KMG]?B', re.I)


def _strip_tool_blocks(lines: list[str]) -> list[str]:
    """Strip tool output blocks from response lines.

    Claude Code shows tool calls as multi-line blocks:
        ● searxng - web_search (MCP)(query: "long search
                                    query that wraps
                                    across lines")
          ⎿ Title: Result title
            Description: Long description that
            also wraps across lines
            … +182 lines (ctrl+o to expand)

    Per-line filtering can't handle the wrapped continuation lines because
    they look like ordinary text. This function identifies tool blocks by
    their structure and removes them entirely, preserving only actual
    response text (● blocks that don't match tool patterns).
    """
    result = []
    in_tool_block = False
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if this line starts a tool block
        if _TOOL_BLOCK_STARTERS.search(stripped):
            in_tool_block = True
            i += 1
            continue

        # Check for timing lines (✻ Brewed for 1m 35s)
        if _TIMING_LINE.search(stripped):
            in_tool_block = False  # Timing ends a block
            i += 1
            continue

        # Inside a tool block: skip tool results, continuations, and indented lines
        if in_tool_block:
            # Tool result lines (⎿)
            if _TOOL_RESULT_LINE.search(line):
                i += 1
                continue
            # Interrupted messages
            if _INTERRUPTED_LINE.search(stripped):
                i += 1
                continue
            # "ctrl+o to expand" lines
            if _EXPAND_LINE.search(stripped):
                i += 1
                continue
            # Received size lines
            if _RECEIVED_LINE.search(stripped):
                i += 1
                continue
            # Continuation: indented lines or lines ending with ") that are part of query
            if stripped.endswith('")') or stripped.endswith("')"):
                i += 1
                continue
            # Heavily indented continuation (4+ leading spaces beyond normal)
            if len(line) - len(line.lstrip()) >= 4 and not stripped.startswith('●'):
                i += 1
                continue
            # New ● block that IS a response (not a tool) — end the tool block
            if stripped.startswith('●'):
                if _TOOL_BLOCK_STARTERS.search(stripped):
                    i += 1
                    continue
                else:
                    in_tool_block = False
                    # Fall through to add this line
            # Blank line while in tool block
            elif not stripped:
                i += 1
                continue
            else:
                # Non-indented, non-blank line without ● — might be end of block
                in_tool_block = False
                # Fall through to add this line

        # Not in a tool block — keep the line
        result.append(line)
        i += 1

    return result


# Common emoji headers that mark the start of a formatted response
_EMOJI_HEADER = re.compile(
    r'^[\U0001f300-\U0001f9ff\u2600-\u27bf\u2700-\u27bf]'  # starts with emoji
)

# Reasoning/planning patterns that indicate preamble (not actual response)
_REASONING_PATTERNS = [
    re.compile(r'^The date is \d{4}', re.I),
    re.compile(r'^(Evening|Morning|Afternoon) message:', re.I),
    re.compile(r'^(Relaxed|Casual|Firm|Gentle|Urgent) tone', re.I),
    re.compile(r"^(Now )?(Let me|I need to|I should|I'll|Looking at) ", re.I),
    re.compile(r'^(Both|All \w+) context files? (are|is) (identical|the same|duplicate)', re.I),
    re.compile(r'^(Now let me handle|Already responded|No additional output)', re.I),
    re.compile(r'^This is the same .* request I just responded to', re.I),
    re.compile(r'^-?\s*(Calories|Protein|Carbs|Fat|Water|Steps):\s*[\d,.]+ / [\d,.]+ = \d+%\s*→', re.I),
    re.compile(r'^All checks pass', re.I),
    re.compile(r'^[}\]]\s*$'),  # lone closing braces from tool blocks
]


def _strip_reasoning_preamble(text: str) -> str:
    """Strip Claude's reasoning/planning text that appears before the formatted response.

    Claude sometimes "thinks out loud" before producing the actual output:
    - Raw data echo: "Calories: 1,787 / 2,100 = 85% → ⚠️"
    - Planning notes: "The date is 2026-02-05. Evening message: water low..."
    - Meta comments: "Both context files are identical. Let me run the check."

    We detect the first emoji-headed line as the response start and strip
    everything before it IF there are reasoning patterns in the preamble.
    """
    lines = text.split('\n')

    # Find the first emoji-header line (actual response start)
    emoji_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and _EMOJI_HEADER.match(stripped):
            emoji_start = i
            break

    if emoji_start is None or emoji_start == 0:
        return text  # No emoji header or already at start

    # Check if the preamble contains reasoning patterns
    preamble = '\n'.join(lines[:emoji_start])
    has_reasoning = any(p.search(preamble) for p in _REASONING_PATTERNS)

    if has_reasoning:
        return '\n'.join(lines[emoji_start:])

    return text


def parse_response(
    raw_screen: str,
    mode: ParseMode = ParseMode.CONVERSATIONAL,
    screen_before: Optional[str] = None
) -> ParseResult:
    """Parse Claude Code screen output to extract clean response.

    Main entry point for response parsing.

    Args:
        raw_screen: Raw captured screen content
        mode: Parsing mode (conversational, technical, raw)
        screen_before: Optional screen before sending message (for diff)

    Returns:
        ParseResult with cleaned content and metadata
    """
    stats: dict[str, int] = {}

    # Split into lines
    all_lines = raw_screen.split('\n')
    total_lines = len(all_lines)

    # If we have before screen, find where new content starts
    if screen_before:
        before_lines = screen_before.split('\n')
        new_start = find_new_content_start(before_lines, all_lines)
        work_lines = all_lines[new_start:]
    else:
        work_lines = all_lines

    # Find response boundaries within the working lines
    start_idx, end_idx = find_response_boundaries(work_lines)
    response_lines = work_lines[start_idx:end_idx]

    # Pre-filter: Strip tool output blocks (● tool calls + ⎿ results + continuations)
    # Claude Code shows tool calls as multi-line blocks that wrap in tmux.
    # Per-line filtering misses the wrapped continuation lines.
    response_lines = _strip_tool_blocks(response_lines)

    # Filter lines based on mode
    kept_lines = []
    for line in response_lines:
        stripped = line.strip()

        if should_skip_line(line, stripped, mode, stats):
            continue

        # Clean the line
        cleaned = clean_line(line)
        if cleaned:
            kept_lines.append(cleaned)

    # Deduplicate
    deduped = dedupe_lines(kept_lines)

    # Join and final cleanup
    content = '\n'.join(deduped).strip()
    content = collapse_blank_lines(content)
    content = _strip_reasoning_preamble(content)

    return ParseResult(
        content=content,
        mode=mode,
        lines_processed=total_lines,
        lines_kept=len(deduped),
        patterns_matched=stats
    )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def extract_response(raw_screen: str, technical: bool = False) -> str:
    """Simple extraction function matching old API.

    Args:
        raw_screen: Raw captured screen content
        technical: If True, include more detail (API responses)

    Returns:
        Cleaned response text
    """
    mode = ParseMode.TECHNICAL if technical else ParseMode.CONVERSATIONAL
    result = parse_response(raw_screen, mode=mode)
    return result.content


def extract_new_response(
    screen_before: str,
    screen_after: str,
    technical: bool = False
) -> str:
    """Extract only new content from screen diff.

    Args:
        screen_before: Screen content before sending message
        screen_after: Screen content after response
        technical: If True, include more detail

    Returns:
        Cleaned new response text
    """
    mode = ParseMode.TECHNICAL if technical else ParseMode.CONVERSATIONAL
    result = parse_response(screen_after, mode=mode, screen_before=screen_before)
    return result.content


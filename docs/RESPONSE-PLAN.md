# RESPONSE-PLAN.md — Implementation Plan for Response Processing Pipeline

> **Version:** 1.0
> **Created:** 2026-02-01
> **Based on:** RESPONSE.md v1.0
> **Status:** Planning

---

## Executive Summary

This plan implements the Response Processing Pipeline specified in RESPONSE.md. The pipeline transforms raw Claude Code output into clean Discord messages through 5 stages: Sanitiser → Classifier → Formatter → Chunker → Renderer.

**Current State Analysis:**
- `domains/peterbot/parser.py` has partial sanitiser functionality (pattern matching, line filtering)
- `domains/peterbot/wsl_config/CLAUDE.md` lines 26-60 contain formatting rules that should migrate to pipeline
- `domains/peterbot/wsl_config/PETERBOT_SOUL.md` lines 82-134 contain formatting rules that should migrate to pipeline
- No classifier, formatter, chunker, or renderer implementations exist
- No long-running command handling exists

**Implementation Language:** Python (matches existing codebase)

---

## Prerequisites & Installation

Before implementing the pipeline, ensure the following dependencies are installed and configured in Claude Code.

### Brave Search MCP Server

The pipeline's search formatters (P4) expect Brave Search results. Install the Brave MCP server:

**Installation:**
```bash
# In Claude Code settings or via CLI
claude mcp add brave-search
# Or manually add to ~/.claude/settings.json
```

**Configuration (`~/.claude/settings.json`):**
```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@anthropics/mcp-server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "<your-api-key>"
      }
    }
  }
}
```

### Brave API Key

| Tier | Queries/Month | Cost | Recommendation |
|------|---------------|------|----------------|
| Free | 2,000 | $0 | Fine for development/testing |
| Base | 20,000 | $5/mo | Recommended for light production |
| Pro | 100,000 | $15/mo | Heavy usage |

**Get API key:** https://brave.com/search/api/

**Note:** Free tier may be sufficient if Peter's daily search volume is low. Monitor usage via Brave dashboard.

### Required Brave Tools

The pipeline expects these MCP tools to exist (all provided by `@anthropics/mcp-server-brave-search`):

| Tool | Used By | Purpose |
|------|---------|---------|
| `brave_web_search` | P4.1, P6 | General web search results |
| `brave_news_search` | P4.2, P6 | News articles with timestamps |
| `brave_image_search` | P4.4, P6 | Image results |
| `brave_local_search` | P4.3, P6 | Local business/place results |
| `brave_video_search` | P4 (future) | Video results (optional) |

**Verification:**
```bash
# In Claude Code, verify tools are available
> /mcp
# Should list brave_web_search, brave_news_search, etc.
```

### Other MCP Servers (Optional but Recommended)

The spec references these for specific formatters:

| MCP Server | Used By | Purpose | Required? |
|------------|---------|---------|-----------|
| **Google Calendar** | P7.1 (Morning Briefing), Schedule Formatter | Calendar events for briefings | Yes for P7 |
| **Memory (claude-mem)** | Context injection | Already installed | Yes |
| **Filesystem** | Built-in | File operations | Built-in |

**Google Calendar MCP** (if not already configured):
```json
{
  "mcpServers": {
    "google-calendar": {
      "command": "npx",
      "args": ["-y", "@anthropics/mcp-server-google-calendar"],
      "env": {
        "GOOGLE_CREDENTIALS_PATH": "~/.config/google/credentials.json"
      }
    }
  }
}
```

**Note:** Peter already uses Hadley API for calendar (`/calendar/today`), so Google Calendar MCP is optional if you prefer the API approach.

### Hadley API Dependencies

The pipeline assumes Hadley API is running at `http://172.19.64.1:8100` (or `localhost:8100` from Windows) with these endpoints for proactive formatters:

| Endpoint | Used By | Purpose |
|----------|---------|---------|
| `/nutrition/today` | P7.1 | Nutrition data for briefings |
| `/calendar/today` | P7.1 | Calendar events for briefings |
| `/weather/current` | P7.1 | Weather for briefings |
| `/nutrition/log-water` | Nutrition formatter | Water logging with totals |
| `/nutrition/today/meals` | Nutrition formatter | Meal list formatting |

**Verification:**
```bash
curl -s http://localhost:8100/health
# Should return {"status": "ok"}
```

### Pre-Implementation Checklist

- [ ] Brave Search MCP server installed
- [ ] Brave API key configured (free tier minimum)
- [ ] `brave_web_search` tool available in Claude Code
- [ ] `brave_news_search` tool available
- [ ] Hadley API running and accessible
- [ ] Memory MCP (claude-mem) running at port 37777
- [ ] WSL network bridge working (172.19.64.1 reachable from WSL)

---

## Phase Overview

| Phase | Scope | Tasks | Complexity | Dependencies |
|-------|-------|-------|------------|--------------|
| **P0** | Sanitiser | 4 tasks | Small | None |
| **P1** | Chunker | 3 tasks | Small | None |
| **P2** | Conversational Formatter | 3 tasks | Medium | P0 |
| **P3** | Table Formatter | 3 tasks | Medium | P0, P2 |
| **P4** | Search Result Formatter | 4 tasks | Medium | P0, P2 |
| **P5** | Long-Running Feedback | 4 tasks | Medium | P0 |
| **P6** | Full Classifier | 4 tasks | Medium | P0, P2, P3, P4 |
| **P7** | Proactive Message Formatting | 3 tasks | Small | P2 |
| **P8** | Migration | 4 tasks | Medium | P0-P7 |
| **P9** | Test Bank | 5 tasks | Large | P0-P8 |
| **P10** | Visual Preview Tool | 2 tasks | Small | P0-P6 |

---

## P0: Sanitiser (Highest Priority)

The Sanitiser strips Claude Code terminal artifacts. This is the biggest immediate win.

### P0.1: Consolidate Sanitiser Rules

**Description:** Merge existing parser.py patterns with RESPONSE.md sanitiser rules into a unified rule set.

**Files:**
- Create: `domains/peterbot/response/sanitiser.py`
- Read: `domains/peterbot/parser.py` (existing patterns)

**Implementation:**
```python
# Migrate from parser.py:
# - UI_PATTERNS → cc_session_header, cc_bullet_markers, cc_status_lines
# - TOOL_PATTERNS → cc_tool_indicators
# - JSON_PATTERNS → (partial, for stripping not classification)
# - CONTEXT_PATTERNS → (keep for context bleed-through)

# Add from RESPONSE.md Section 3.1:
# - cc_token_summary (new)
# - cc_permission_prompts (new)
# - ansi_codes (new - \x1b\[[0-9;]*m)
# - excess_blank_lines (exists but needs alignment)
# - trim_whitespace (exists)
```

**Dependencies:** None

**Acceptance Criteria:**
- [ ] All 9 RESPONSE.md sanitiser rules implemented (Section 3.1)
- [ ] Processing order matches Section 3.2 (ANSI first, trim last)
- [ ] No regressions on existing parser.py test cases
- [ ] Sanitiser can be called independently: `sanitise(raw_text) → clean_text`

**Test Cases (from Section 12.2):**
- `artifact-015`: CC session headers, bullets, tool indicators, token summary all stripped
- Category: `cc_artifact_contamination` (50 test cases)

**Complexity:** Small

---

### P0.2: Implement --raw Flag Bypass

**Description:** Add `--raw` / `--debug` flag support to bypass sanitiser for debugging.

**Files:**
- Modify: `domains/peterbot/response/sanitiser.py`
- Modify: `domains/peterbot/router.py` (detect flag in user message)

**Implementation:**
```python
def sanitise(raw_text: str, bypass: bool = False) -> str:
    if bypass:
        return f"```\n{raw_text}\n```"  # Wrap in code block
    # ... normal sanitisation
```

**Dependencies:** P0.1

**Acceptance Criteria:**
- [ ] Message containing `--raw` returns unprocessed CC output in code block
- [ ] Message containing `--debug` has same effect
- [ ] Flag is case-insensitive

**Test Cases:**
- User sends "What's the weather? --raw" → response wrapped in code block with CC artifacts visible

**Complexity:** Small

---

### P0.3: Add ANSI Code Stripping

**Description:** Add ANSI escape code removal as first sanitiser step.

**Files:**
- Modify: `domains/peterbot/response/sanitiser.py`

**Implementation:**
```python
ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*m')

def strip_ansi(text: str) -> str:
    return ANSI_PATTERN.sub('', text)
```

**Dependencies:** P0.1

**Acceptance Criteria:**
- [ ] All ANSI colour codes removed: `\x1b[32m`, `\x1b[0m`, `\x1b[1;34m`
- [ ] All ANSI style codes removed: `\x1b[1m` (bold), `\x1b[4m` (underline)
- [ ] Processing happens before all other patterns (Section 3.2)

**Test Cases:**
- Input with `\x1b[32mgreen text\x1b[0m` → output `green text`

**Complexity:** Small

---

### P0.4: Integrate Sanitiser into Response Flow

**Description:** Wire sanitiser into the message handling pipeline.

**Files:**
- Modify: `domains/peterbot/router.py`
- Create: `domains/peterbot/response/__init__.py`
- Create: `domains/peterbot/response/pipeline.py` (stub with sanitiser only)

**Implementation:**
```python
# pipeline.py
async def process(raw_cc_output: str, context: dict) -> ProcessedResponse:
    # Check for bypass
    if '--raw' in context.get('user_prompt', '') or '--debug' in context.get('user_prompt', ''):
        return ProcessedResponse(content=f"```\n{raw_cc_output}\n```", chunks=[])

    # Stage 1: Sanitise
    sanitised = sanitise(raw_cc_output)

    # Stages 2-5 to be implemented...
    return ProcessedResponse(content=sanitised, chunks=[sanitised])
```

**Dependencies:** P0.1, P0.2, P0.3

**Acceptance Criteria:**
- [ ] All Claude Code output passes through sanitiser before Discord delivery
- [ ] Existing conversational responses unchanged after sanitisation
- [ ] CC artifacts no longer appear in Discord messages

**Test Cases:**
- Send message in #peterbot, verify no `⏺`, `⎿`, token counts in response

**Complexity:** Small

---

## P1: Chunker

The Chunker splits formatted content into Discord-safe segments. Critical for long responses.

### P1.1: Implement Base Chunker

**Description:** Create chunker with configurable limits and split priorities.

**Files:**
- Create: `domains/peterbot/response/chunker.py`

**Implementation:**
```python
@dataclass
class ChunkerConfig:
    max_chars: int = 1900  # Buffer below 2000
    max_lines_per_message: int = 20
    min_chars: int = 200

class SplitPriority(Enum):
    PARAGRAPH = 1   # \n\n
    NEWLINE = 2     # \n
    SENTENCE = 3    # '. ' or '.\n'
    WHITESPACE = 4  # ' '
    HARD_BREAK = 5  # maxChars

def chunk(text: str, config: ChunkerConfig = None) -> list[str]:
    # Implementation per Section 6.2
```

**Dependencies:** None

**Acceptance Criteria:**
- [ ] Text over 1900 chars split into multiple chunks
- [ ] Each chunk under 2000 chars
- [ ] Split prefers paragraph boundaries over mid-sentence
- [ ] Minimum chunk size 200 chars (no tiny fragments)

**Test Cases:**
- `long_response-001`: 3000 char response → 2 chunks, split at paragraph
- Category: `long_responses` (40 test cases)

**Complexity:** Small

---

### P1.2: Code Fence Safety

**Description:** Ensure code blocks are never split mid-fence.

**Files:**
- Modify: `domains/peterbot/response/chunker.py`

**Implementation:**
```python
def split_preserving_code_fences(text: str, max_chars: int) -> list[str]:
    # Track in_code_block state
    # If split needed inside code block:
    #   1. Close fence: append ```
    #   2. Start new chunk with ```lang
    # Per Section 6.3
```

**Dependencies:** P1.1

**Acceptance Criteria:**
- [ ] Code block split → closing ``` added to first chunk
- [ ] Next chunk starts with ``` + original language hint
- [ ] Nested code blocks handled correctly

**Test Cases:**
- 2500 char code block → 2 chunks, each valid standalone with proper fencing

**Complexity:** Small

---

### P1.3: Chunk Numbering

**Description:** Add chunk indicators for multi-part responses.

**Files:**
- Modify: `domains/peterbot/response/chunker.py`

**Implementation:**
```python
def add_chunk_numbers(chunks: list[str]) -> list[str]:
    if len(chunks) < 3:
        return chunks
    return [f"{chunk}\n-# ({i+1}/{len(chunks)})" for i, chunk in enumerate(chunks)]
```

**Dependencies:** P1.1

**Acceptance Criteria:**
- [ ] 3+ chunks get `-# (1/3)` `-# (2/3)` `-# (3/3)` footer
- [ ] 1-2 chunks have no numbering
- [ ] Uses Discord subtext format (`-#`)

**Test Cases:**
- Validation rule: `chunks_numbered` for responses with 3+ chunks

**Complexity:** Small

---

## P2: Conversational Formatter

Handles ~80% of responses. Clean natural language for Discord.

### P2.1: Strip Markdown Headers

**Description:** Remove `#`, `##`, `###` headers from conversational responses.

**Files:**
- Create: `domains/peterbot/response/formatters/conversational.py`

**Implementation:**
```python
def format_conversational(text: str) -> str:
    # Strip headers - conversational responses shouldn't have them
    text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
    # ... more rules
```

**Dependencies:** P0

**Acceptance Criteria:**
- [ ] `# Header` → `Header` (no hash)
- [ ] `## Subheader` → `Subheader`
- [ ] Headers within code blocks preserved
- [ ] Horizontal rules (`---`) also stripped

**Test Cases:**
- Validation rule: `no_headers`
- Category: `casual_conversation` (150 test cases)

**Complexity:** Small

---

### P2.2: JSON Stripping Logic

**Description:** Strip or summarise JSON from conversational responses.

**Files:**
- Modify: `domains/peterbot/response/formatters/conversational.py`

**Implementation:**
```python
def strip_json_from_conversational(text: str) -> str:
    # If response is ONLY JSON, flag for summarisation
    trimmed = text.strip()
    if is_valid_json(trimmed):
        return '[JSON data detected — pipeline will extract natural language]'

    # If JSON embedded in prose, remove JSON blocks
    text = re.sub(r'```json\n[\s\S]*?\n```', '', text)
    text = re.sub(r'```\n\{[\s\S]*?\}\n```', '', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()
```

**Dependencies:** P2.1

**Acceptance Criteria:**
- [ ] Fenced JSON blocks removed from prose
- [ ] Unfenced JSON blocks removed
- [ ] Gaps collapsed to single blank line
- [ ] Pure-JSON response flagged for summarisation

**Test Cases:**
- Validation rules: `no_json`, `no_raw_json`
- Category: `json_leakage` (40 test cases)

**Complexity:** Medium

---

### P2.3: Trailing Meta-Commentary Removal

**Description:** Remove assistant sign-off phrases.

**Files:**
- Modify: `domains/peterbot/response/formatters/conversational.py`

**Implementation:**
```python
TRAILING_PHRASES = [
    r"let me know if you (?:need|want|have) (?:anything|any questions|more)",
    r"(?:hope|glad) (?:this|that) helps",
    r"feel free to ask",
    r"is there anything else",
]

def strip_trailing_meta(text: str) -> str:
    for pattern in TRAILING_PHRASES:
        text = re.sub(rf'\s*{pattern}[.!?]?\s*$', '', text, flags=re.I)
    return text
```

**Dependencies:** P2.1

**Acceptance Criteria:**
- [ ] "Let me know if you need anything else!" removed
- [ ] "Hope this helps!" removed
- [ ] Natural ending sentences preserved
- [ ] Questions followed by more content preserved

**Test Cases:**
- Input ending with "Hope this helps!" → output without that phrase

**Complexity:** Small

---

## P3: Table Formatter

Discord cannot render markdown tables. Convert to alternatives.

### P3.1: Table Detection and Parsing

**Description:** Detect and parse markdown tables from CC output.

**Files:**
- Create: `domains/peterbot/response/formatters/table.py`

**Implementation:**
```python
@dataclass
class ParsedTable:
    headers: list[str]
    rows: list[list[str]]
    col_count: int
    row_count: int

def detect_tables(text: str) -> list[tuple[str, ParsedTable]]:
    """Find all markdown tables in text, return (raw_match, parsed) tuples."""
    # Regex for markdown table: | header | header |
    #                          |--------|--------|
    #                          | cell   | cell   |
```

**Dependencies:** P0

**Acceptance Criteria:**
- [ ] Detects standard markdown tables
- [ ] Parses headers and rows correctly
- [ ] Returns raw match string for replacement
- [ ] Handles varying column counts gracefully

**Test Cases:**
- Category: `data_table_responses` (80 test cases)
- Validation rule: `no_markdown_table`

**Complexity:** Medium

---

### P3.2: Code Block Table Rendering

**Description:** Render tables as fixed-width code blocks (Strategy B from RESPONSE.md).

**Files:**
- Modify: `domains/peterbot/response/formatters/table.py`

**Implementation:**
```python
def table_to_code_block(table: ParsedTable) -> str:
    """Render table using fixed-width code block."""
    # Calculate column widths
    col_widths = [max(len(h), max(len(r[i]) for r in table.rows))
                  for i, h in enumerate(table.headers)]

    # Build fixed-width table with box characters
    header = ' │ '.join(h.ljust(w) for h, w in zip(table.headers, col_widths))
    separator = '─┼─'.join('─' * w for w in col_widths)
    rows = [' │ '.join(c.ljust(w) for c, w in zip(r, col_widths)) for r in table.rows]

    return f"```\n{header}\n{separator}\n" + '\n'.join(rows) + "\n```"
```

**Dependencies:** P3.1

**Acceptance Criteria:**
- [ ] Table renders with fixed-width columns
- [ ] Box-drawing characters for borders (│, ─, ┼)
- [ ] All cells aligned correctly
- [ ] Wrapped in ``` code block

**Test Cases:**
- 3-column table → proper alignment in Discord code block

**Complexity:** Medium

---

### P3.3: Table Selection Logic

**Description:** Choose rendering strategy based on table dimensions.

**Files:**
- Modify: `domains/peterbot/response/formatters/table.py`

**Implementation:**
```python
def format_table(table: ParsedTable, context: dict) -> str:
    """Select best rendering strategy per Section 5.3."""
    # Strategy A: Embed Fields (≤4 cols AND ≤6 rows) - defer to P4
    # Strategy B: Code Block (>4 cols OR >6 rows)
    # Strategy C: Prose (2-3 cols AND comparison-style)

    if table.col_count <= 3 and is_comparison_table(table):
        return table_to_prose(table)
    elif table.col_count > 4 or table.row_count > 6:
        return table_to_code_block(table)
    else:
        return table_to_code_block(table)  # Default to code block until embeds implemented
```

**Dependencies:** P3.1, P3.2

**Acceptance Criteria:**
- [ ] Small comparison tables → prose format
- [ ] Large tables → code block
- [ ] Medium tables → code block (embed strategy deferred)

**Test Cases:**
- 2-column comparison → prose: "**eBay UK**: £380-£450, rated 4.5★"
- 5-column data → code block

**Complexity:** Small

---

## P4: Search Result Formatter

Format Brave API results into Discord embeds.

### P4.1: Web Search Embed

**Description:** Format Brave web search results as Discord embed.

**Files:**
- Create: `domains/peterbot/response/formatters/search.py`

**Implementation:**
```python
def format_search_results(results: list[dict], summary: str) -> dict:
    """Return Discord embed dict for search results."""
    # Per Section 5.4
    embed = {
        'color': 0xFB542B,  # Brave orange
        'author': {'name': '🔍 Web Search'},
        'description': '\n\n'.join(
            f"**{i+1}. [{r['title']}]({r['url']})**\n{truncate(r['snippet'], 100)}"
            for i, r in enumerate(results[:10])
        ),
        'footer': {'text': f"{len(results)} results found"}
    }
    return {'content': summary, 'embed': embed}
```

**Dependencies:** P0, P2

**Acceptance Criteria:**
- [ ] Results formatted as numbered list with title links
- [ ] Snippets truncated to 100 chars
- [ ] Natural language summary precedes embed
- [ ] Embed colour is Brave orange (0xFB542B)

**Test Cases:**
- `search-042`: LEGO price search → summary + embed with links
- Category: `brave_web_search` (100 test cases)
- Validation rules: `has_natural_language_summary`, `has_embed`, `search_results_in_embed`

**Complexity:** Medium

---

### P4.2: News Search Embed

**Description:** Format Brave news results with source and timestamp.

**Files:**
- Modify: `domains/peterbot/response/formatters/search.py`

**Implementation:**
```python
def format_news_results(results: list[dict]) -> dict:
    """Per Section 5.5."""
    embed = {
        'color': 0x1DA1F2,  # Twitter blue
        'author': {'name': '📰 News'},
        'description': '\n\n'.join(
            f"**[{r['title']}]({r['url']})**\n"
            f"-# {r['source']} • {format_relative_time(r['published_at'])}\n"
            f"{truncate(r['snippet'], 80)}"
            for r in results[:10]
        )
    }
    return {'embed': embed}
```

**Dependencies:** P4.1

**Acceptance Criteria:**
- [ ] News source displayed
- [ ] Relative timestamp (e.g., "2 hours ago")
- [ ] Embed colour is Twitter blue (0x1DA1F2)

**Test Cases:**
- Category: `brave_news_search` (50 test cases)

**Complexity:** Small

---

### P4.3: Local Search Embed

**Description:** Format local business results.

**Files:**
- Modify: `domains/peterbot/response/formatters/search.py`

**Implementation:**
```python
def format_local_results(results: list[dict]) -> dict:
    """Per Section 5.7."""
    embed = {
        'color': 0x34A853,  # Google green
        'author': {'name': '📍 Local Results'},
        'description': '\n\n'.join(
            f"**{r['name']}** {'⭐' * round(r.get('rating', 0))}\n"
            f"{r['address']}\n"
            + (f"📞 {r['phone']}" if r.get('phone') else '')
            for r in results[:10]
        )
    }
    return {'embed': embed}
```

**Dependencies:** P4.1

**Acceptance Criteria:**
- [ ] Business name with star rating
- [ ] Address displayed
- [ ] Phone number if available
- [ ] Embed colour is Google green (0x34A853)

**Test Cases:**
- Category: `brave_local_search` (30 test cases)

**Complexity:** Small

---

### P4.4: Image Search Embed

**Description:** Format image results as image embeds.

**Files:**
- Modify: `domains/peterbot/response/formatters/search.py`

**Implementation:**
```python
def format_image_results(results: list[dict]) -> list[dict]:
    """Per Section 5.6 - returns multiple embeds."""
    return [
        {
            'color': 0x7C3AED,  # Purple
            'image': {'url': r['url']},
            'footer': {'text': truncate(r['title'], 50)}
        }
        for r in results[:3]  # Max 3 images
    ]
```

**Dependencies:** P4.1

**Acceptance Criteria:**
- [ ] Max 3 image embeds
- [ ] Image URL in embed image field
- [ ] Title in footer
- [ ] Embed colour is purple (0x7C3AED)

**Test Cases:**
- Category: `brave_image_search` (30 test cases)

**Complexity:** Small

---

## P5: Long-Running Feedback

Handle Claude Code tasks that take >3 seconds.

### P5.1: Task Type Detection

**Description:** Detect what type of long-running task is executing.

**Files:**
- Create: `domains/peterbot/response/feedback.py`

**Implementation:**
```python
ACK_TEMPLATES = {
    'brave_web_search':   '🔍 Searching the web...',
    'brave_news_search':  '📰 Checking the latest news...',
    'brave_image_search': '🖼️ Looking for images...',
    'brave_local_search': '📍 Finding local results...',
    'build_task':         '⚙️ Working on that...',
    'file_operation':     '📂 Updating files...',
    'multi_step':         '🧠 Thinking through this — might take a moment...',
    'default':            '💭 Working on it...',
}

def detect_task_type(user_message: str) -> str:
    """Detect task type from user message for appropriate ack."""
```

**Dependencies:** P0

**Acceptance Criteria:**
- [ ] Search queries → search-specific ack
- [ ] File operations → file ack
- [ ] Complex questions → thinking ack
- [ ] Unknown → default ack

**Test Cases:**
- "What's LEGO 42100 worth?" → `brave_web_search` type

**Complexity:** Small

---

### P5.2: Quick Acknowledgement (3s)

**Description:** Send "thinking" message after 3 seconds of silence.

**Files:**
- Modify: `domains/peterbot/response/feedback.py`
- Modify: `domains/peterbot/router.py`

**Implementation:**
```python
@dataclass
class LongRunningConfig:
    ack_delay_ms: int = 3000
    progress_interval_ms: int = 30000
    max_wait_ms: int = 600000  # 10 min

async def send_ack_if_needed(message, delay: int = 3000) -> Optional[Message]:
    """Send acknowledgement after delay if response not yet received."""
    await asyncio.sleep(delay / 1000)
    if not response_received:
        task_type = detect_task_type(message.content)
        return await message.reply(ACK_TEMPLATES[task_type])
    return None
```

**Dependencies:** P5.1

**Acceptance Criteria:**
- [ ] Ack sent after 3 seconds of no response
- [ ] Ack message matches task type
- [ ] Ack not sent if response arrives within 3 seconds

**Test Cases:**
- Category: `long_running` (edge cases)

**Complexity:** Medium

---

### P5.3: Progress Updates (every 30s)

**Description:** Update ack message with progress for very long tasks.

**Files:**
- Modify: `domains/peterbot/response/feedback.py`

**Implementation:**
```python
async def update_progress(ack_message: Message, elapsed_seconds: int):
    """Append progress indicator to ack message."""
    await ack_message.edit(content=ack_message.content + '\n-# Still working...')
```

**Dependencies:** P5.2

**Acceptance Criteria:**
- [ ] Progress update after 30 seconds
- [ ] Uses Discord subtext format
- [ ] Updates existing ack message (no new messages)

**Test Cases:**
- Task taking 45 seconds → ack at 3s, progress update at 33s

**Complexity:** Small

---

### P5.4: Timeout Handling

**Description:** Handle tasks exceeding max wait time.

**Files:**
- Modify: `domains/peterbot/response/feedback.py`

**Implementation:**
```python
async def handle_timeout(ack_message: Optional[Message], message: Message):
    """Handle task timeout - update ack or send timeout message."""
    timeout_msg = "⚠️ This is taking longer than expected. I'll send the result when it's ready."
    if ack_message:
        await ack_message.edit(content=timeout_msg)
    else:
        await message.reply(timeout_msg)
```

**Dependencies:** P5.2

**Acceptance Criteria:**
- [ ] Timeout at 10 minutes (configurable)
- [ ] Appropriate message to user
- [ ] Task continues in background

**Test Cases:**
- Category: `error_scenarios` (subset)

**Complexity:** Small

---

## P6: Full Classifier

Automatic response type detection for formatter routing.

### P6.1: Classification Signals

**Description:** Extract structural and content signals from sanitised output.

**Files:**
- Create: `domains/peterbot/response/classifier.py`

**Implementation:**
```python
@dataclass
class ClassificationSignals:
    has_markdown_table: bool
    has_code_block: bool
    has_json_block: bool
    has_url_list: bool
    has_bullet_list: bool
    has_numbered_list: bool
    brave_search_detected: bool
    schedule_terms: bool
    error_patterns: bool
    char_count: int
    line_count: int
    code_to_prose_ratio: float

def extract_signals(text: str) -> ClassificationSignals:
    """Analyse text for classification signals."""
```

**Dependencies:** P0

**Acceptance Criteria:**
- [ ] All 12 signal types detected correctly
- [ ] Code-to-prose ratio calculated
- [ ] No false positives on edge cases

**Test Cases:**
- 1000-prompt bank classification accuracy >95%

**Complexity:** Medium

---

### P6.2: Response Type Enum

**Description:** Define all response types with classification priority.

**Files:**
- Modify: `domains/peterbot/response/classifier.py`

**Implementation:**
```python
class ResponseType(Enum):
    CONVERSATIONAL = 'conversational'
    DATA_TABLE = 'data_table'
    CODE = 'code'
    SEARCH_RESULTS = 'search_results'
    NEWS_RESULTS = 'news_results'
    IMAGE_RESULTS = 'image_results'
    LOCAL_RESULTS = 'local_results'
    LIST = 'list'
    SCHEDULE = 'schedule'
    ERROR = 'error'
    MIXED = 'mixed'
    LONG_RUNNING_ACK = 'long_running_ack'
    PROACTIVE = 'proactive'
```

**Dependencies:** P6.1

**Acceptance Criteria:**
- [ ] All 13 response types defined
- [ ] Each type has clear classification criteria

**Test Cases:**
- Per Section 12.2.1 categories map to response types

**Complexity:** Small

---

### P6.3: Classification Logic

**Description:** Implement priority-based classification per Section 4.3.

**Files:**
- Modify: `domains/peterbot/response/classifier.py`

**Implementation:**
```python
def classify(text: str, context: dict = None) -> ResponseType:
    """Classify response type using priority order from Section 4.3."""
    signals = extract_signals(text)

    # Priority order (Section 4.3):
    # 1. Brave search detected → SEARCH_RESULTS (or NEWS/IMAGE/LOCAL)
    if signals.brave_search_detected:
        return detect_search_subtype(text)

    # 2. JSON block + high code ratio → CODE
    if signals.has_json_block and signals.code_to_prose_ratio > 0.7:
        return ResponseType.CODE

    # 3. Markdown table → DATA_TABLE (or MIXED)
    if signals.has_markdown_table:
        return ResponseType.DATA_TABLE if signals.code_to_prose_ratio > 0.5 else ResponseType.MIXED

    # ... remaining logic per Section 4.3

    # 9. Default
    return ResponseType.CONVERSATIONAL
```

**Dependencies:** P6.1, P6.2

**Acceptance Criteria:**
- [ ] Classification follows priority order exactly
- [ ] MIXED type used when multiple types detected
- [ ] Conversational is default
- [ ] Classification accuracy >95% on test bank

**Test Cases:**
- All 1000 prompts classified correctly per `expectedType` field

**Complexity:** Medium

---

### P6.4: Formatter Routing

**Description:** Route classified responses to appropriate formatters.

**Files:**
- Modify: `domains/peterbot/response/pipeline.py`

**Implementation:**
```python
FORMATTERS = {
    ResponseType.CONVERSATIONAL: format_conversational,
    ResponseType.DATA_TABLE: format_table,
    ResponseType.SEARCH_RESULTS: format_search_results,
    ResponseType.NEWS_RESULTS: format_news_results,
    ResponseType.CODE: format_code,
    # ...
}

def format(text: str, response_type: ResponseType, context: dict) -> FormattedResponse:
    formatter = FORMATTERS.get(response_type, format_conversational)
    return formatter(text, context)
```

**Dependencies:** P6.3, P2, P3, P4

**Acceptance Criteria:**
- [ ] Each response type routes to correct formatter
- [ ] Unknown types fall back to conversational
- [ ] MIXED type splits and formats segments individually

**Test Cases:**
- Integration test: raw CC output → correct formatter called

**Complexity:** Small

---

## P7: Proactive Message Formatting

Peter-initiated messages need distinct formatting.

### P7.1: Morning Briefing Template

**Description:** Format morning briefing with structured sections.

**Files:**
- Create: `domains/peterbot/response/formatters/proactive.py`

**Implementation:**
```python
def format_morning_briefing(data: dict) -> str:
    """Per Section 11.1."""
    return f"""☀️ **Morning, Chris**

**Weather** — {data['weather']['temp']}°C, {data['weather']['condition']}. {data['weather']['running_note']}
**Calendar** — {data['calendar']['summary']}
**eBay** — {data['ebay']['summary']}
**Reminders** — {data['reminders'][0] if data['reminders'] else 'None for today'}

-# {data['timestamp']} • Proactive briefing"""
```

**Dependencies:** P2

**Acceptance Criteria:**
- [ ] ☀️ header
- [ ] Structured sections (Weather, Calendar, eBay, Reminders)
- [ ] Proactive footer with timestamp
- [ ] Uses Discord subtext for footer

**Test Cases:**
- Morning briefing fixture renders correctly
- Validation: matches Section 11.1 format

**Complexity:** Small

---

### P7.2: Reminder Format

**Description:** Format reminder notifications.

**Files:**
- Modify: `domains/peterbot/response/formatters/proactive.py`

**Implementation:**
```python
def format_reminder(task: str) -> str:
    """Per Section 11.2."""
    return f"""⏰ **Reminder**
{task}

-# Scheduled reminder"""
```

**Dependencies:** P7.1

**Acceptance Criteria:**
- [ ] ⏰ header
- [ ] Task text on separate line
- [ ] Proactive footer

**Test Cases:**
- Reminder fixture renders with ⏰

**Complexity:** Small

---

### P7.3: Alert Format with Reactions

**Description:** Format alerts with reaction prompts.

**Files:**
- Modify: `domains/peterbot/response/formatters/proactive.py`

**Implementation:**
```python
def format_alert(alert_type: str, message: str, actions: list[str] = None) -> dict:
    """Per Section 11.3. Returns content + reactions to add."""
    emoji_map = {'ebay': '🔔', 'price': '💰', 'stock': '📦'}

    content = f"""{emoji_map.get(alert_type, '🔔')} **{alert_type.title()} Alert**
{message}

React ✅ to accept, ❌ to decline, or reply with a counter.

-# Automatic {alert_type} notification"""

    return {'content': content, 'reactions': ['✅', '❌']}
```

**Dependencies:** P7.1

**Acceptance Criteria:**
- [ ] Alert emoji header
- [ ] Action prompt for reactions
- [ ] Returns reactions to add to message
- [ ] Proactive footer

**Test Cases:**
- Alert fixture renders with ✅/❌ prompt

**Complexity:** Small

---

## P8: Migration

Strip formatting rules from CLAUDE.md and PETERBOT_SOUL.md.

### P8.1: Strip CLAUDE.md Formatting Rules

**Description:** Remove lines 26-60 (Discord Formatting section) from CLAUDE.md.

**Files:**
- Modify: `domains/peterbot/wsl_config/CLAUDE.md`

**Lines to Remove (26-60):**
```markdown
### Discord Formatting (CRITICAL)

**Discord does NOT render markdown tables.** Never use `|---|` table syntax.

For nutrition/health data, format like this:
```
**Today's Nutrition** 🍎
...
```

For meal logs:
```
**Today's Meals** 🍽️
...
```

For water logging:
```
💧 Logged 500ml
...
```
```

**Replace With:**
```markdown
## Response Formatting
@RESPONSE.md governs ALL response formatting for Discord delivery.
Every response passes through the Response Pipeline before reaching Discord.
Never bypass the pipeline. For debugging, use --raw flag.
```

**Dependencies:** P0-P7 complete

**Acceptance Criteria:**
- [ ] Lines 26-60 removed from CLAUDE.md
- [ ] Single RESPONSE.md reference added
- [ ] No other formatting guidance remains
- [ ] Migration regression tests pass (Section 13.7)

**Test Cases:**
- `migration.test.py`: CLAUDE.md contains no formatting rules
- CLAUDE.md references RESPONSE.md exactly once

**Complexity:** Small

---

### P8.2: Strip PETERBOT_SOUL.md Formatting Rules

**Description:** Remove lines 82-134 (Discord Formatting section) from PETERBOT_SOUL.md.

**Files:**
- Modify: `domains/peterbot/wsl_config/PETERBOT_SOUL.md`

**Lines to Remove (82-134):**
```markdown
## Discord Formatting

You are responding via Discord. Format accordingly:
- Keep responses punchy - aim for under 500 chars for casual chat
- Use **bold** for emphasis, not headers or complex formatting
...
**IMPORTANT: Discord does NOT render markdown tables.**
...
**For nutrition/health data, use this format:**
...
**For meal logs:**
...
**For water logging confirmations:**
...
**Sources/URLs:**
...
**Output Cleanliness:**
...
```

**Replace With:**
```markdown
## Formatting
All Discord formatting, message structure, embeds, chunking, and rendering
rules live in @RESPONSE.md. This file (PETERBOT_SOUL.md) only governs Peter's
personality, tone, and voice — not how messages are structured or displayed.
```

**Dependencies:** P0-P7 complete

**Acceptance Criteria:**
- [ ] Lines 82-134 removed from PETERBOT_SOUL.md
- [ ] Formatting boundary note added
- [ ] Personality/tone content preserved
- [ ] Migration regression tests pass

**Test Cases:**
- `migration.test.py`: PETERBOT_SOUL.md contains no formatting rules
- PETERBOT_SOUL.md still contains personality/tone content

**Complexity:** Small

---

### P8.3: Sync to WSL

**Description:** Run sync script to propagate changes to WSL Claude Code instance.

**Files:**
- Run: `python domains/peterbot/wsl_config/sync.py`

**Dependencies:** P8.1, P8.2

**Acceptance Criteria:**
- [ ] CLAUDE.md in WSL matches Windows version
- [ ] PETERBOT_SOUL.md in WSL matches Windows version
- [ ] Claude Code session recreated to pick up changes

**Test Cases:**
- Manual: Send message in #peterbot, verify no double formatting guidance

**Complexity:** Small

---

### P8.4: Migration Regression Tests

**Description:** Create migration-specific regression test suite.

**Files:**
- Create: `tests/response/migration_test.py`

**Implementation:**
```python
def test_claude_md_no_formatting_rules():
    claude = load_file('domains/peterbot/wsl_config/CLAUDE.md')
    assert 'discord.*format' not in claude.lower()
    assert 'embed.*colour' not in claude.lower()
    assert 'markdown.*table' not in claude.lower()
    assert claude.count('RESPONSE.md') == 1

def test_peterbot_soul_no_formatting_rules():
    soul = load_file('domains/peterbot/wsl_config/PETERBOT_SOUL.md')
    assert 'embed' not in soul.lower()
    assert 'code.?block' not in soul.lower()
    assert 'chunk' not in soul.lower()
    assert '2000.*char' not in soul.lower()
    # Personality content still present
    assert 'personality' in soul.lower() or 'tone' in soul.lower()

def test_response_md_complete():
    response = load_file('docs/RESPONSE.md')
    assert 'sanitiser' in response.lower()
    assert 'classifier' in response.lower()
    assert 'formatter' in response.lower()
    assert 'chunker' in response.lower()
    assert 'renderer' in response.lower()
```

**Dependencies:** P8.1, P8.2

**Acceptance Criteria:**
- [ ] All migration tests pass
- [ ] No conflicting rules across files
- [ ] Proactive messages render correctly post-migration

**Test Cases:**
- Per Section 13.7 regression test code

**Complexity:** Medium

---

## P9: Test Bank

Build comprehensive test suite per Section 12.

### P9.1: Test Fixtures Collection

**Description:** Capture real CC output samples for test fixtures.

**Files:**
- Create: `tests/response/__fixtures__/`
- Create: `tests/response/__fixtures__/conversational/`
- Create: `tests/response/__fixtures__/search/`
- Create: `tests/response/__fixtures__/tables/`
- Create: `tests/response/__fixtures__/artifacts/`

**Implementation:**
- Capture 50+ real CC outputs from each category
- Store as JSON with raw input and expected output

**Dependencies:** P0-P8

**Acceptance Criteria:**
- [ ] 50+ conversational fixtures
- [ ] 50+ search result fixtures
- [ ] 50+ table fixtures
- [ ] 50+ artifact-contaminated fixtures
- [ ] Each fixture has raw input and expected clean output

**Test Cases:**
- Fixtures cover all 16 categories from Section 12.2.1

**Complexity:** Large

---

### P9.2: Prompt Bank Structure

**Description:** Create the 1000-prompt test bank structure.

**Files:**
- Create: `tests/response/stubs/prompts.json`
- Create: `tests/response/stubs/expected-types.json`

**Implementation:**
```json
{
  "id": "conv-001",
  "category": "casual_conversation",
  "userPrompt": "how's it going Peter?",
  "ccRawOutput": "I'm doing well! Always ready to help...",
  "expectedType": "CONVERSATIONAL",
  "expectedSanitiserActions": [],
  "expectedFormat": "plain_text",
  "expectedChunks": 1,
  "validationRules": ["no_embed", "no_headers", "no_json", "under_500_chars", "no_cc_artifacts"]
}
```

**Dependencies:** P9.1

**Acceptance Criteria:**
- [ ] 1000 prompts across all 16 categories
- [ ] Each prompt has all required fields
- [ ] Category distribution matches Section 12.2.1

**Test Cases:**
- JSON schema validation passes for all prompts

**Complexity:** Large

---

### P9.3: Validation Rules Implementation

**Description:** Implement all validation rules from Section 12.2.3.

**Files:**
- Create: `tests/response/validators.py`

**Implementation:**
```python
VALIDATION_RULES = {
    'no_embed': lambda m: len(m.embeds) == 0,
    'has_embed': lambda m: len(m.embeds) > 0,
    'no_headers': lambda m: not re.search(r'^#{1,3}\s', m.content, re.M),
    'no_json': lambda m: not is_valid_json(m.content) and '```json' not in m.content.lower(),
    'no_cc_artifacts': lambda m: not contains_cc_artifacts(m.content),
    'no_markdown_table': lambda m: not re.search(r'\|.*\|.*\|', m.content),
    'under_300_chars': lambda m: len(m.content) < 300,
    'under_500_chars': lambda m: len(m.content) < 500,
    'under_2000_chars': lambda m: len(m.content) <= 2000,
    'has_natural_language': lambda m: len(m.content.split(' ')) > 5,
    'chunks_numbered': lambda m: bool(re.search(r'\(\d+/\d+\)', m.content)),
    # ... all 20 rules from Section 12.2.3
}
```

**Dependencies:** P0-P8

**Acceptance Criteria:**
- [ ] All 20 validation rules implemented
- [ ] Each rule has positive and negative test cases
- [ ] Rules composable for per-prompt validation

**Test Cases:**
- Each validation rule tested independently

**Complexity:** Medium

---

### P9.4: Test Runner

**Description:** Create test runner that validates all 1000 prompts.

**Files:**
- Create: `tests/response/test_pipeline.py`

**Implementation:**
```python
@pytest.mark.parametrize("prompt", load_test_prompts())
def test_prompt(prompt):
    result = pipeline.process(prompt['ccRawOutput'], {
        'userPrompt': prompt['userPrompt']
    })

    assert result.detected_type == prompt['expectedType']
    for action in prompt['expectedSanitiserActions']:
        assert action in result.sanitiser_log
    assert result.format == prompt['expectedFormat']
    assert len(result.chunks) == prompt['expectedChunks']
    for rule in prompt['validationRules']:
        assert VALIDATION_RULES[rule](result.rendered)
```

**Dependencies:** P9.1, P9.2, P9.3

**Acceptance Criteria:**
- [ ] All 1000 prompts tested
- [ ] Test output shows pass/fail per category
- [ ] Failure messages include prompt ID and rule violated
- [ ] Pipeline pass rate >98%

**Test Cases:**
- Self-referential: the test runner is the test

**Complexity:** Medium

---

### P9.5: Coverage Reporting

**Description:** Generate test coverage reports.

**Files:**
- Modify: `tests/response/test_pipeline.py`
- Create: `tests/response/coverage_report.py`

**Implementation:**
```python
def generate_coverage_report():
    """Generate coverage per Section 12.5 targets."""
    return {
        'sanitiser_rules': calculate_rule_coverage(),  # Target: 100%
        'classifier_accuracy': calculate_classifier_accuracy(),  # Target: >95%
        'formatter_coverage': calculate_formatter_coverage(),  # Target: 100%
        'chunker_edge_cases': calculate_chunker_coverage(),  # Target: 100%
        'pipeline_integration': calculate_pipeline_pass_rate(),  # Target: >98%
    }
```

**Dependencies:** P9.4

**Acceptance Criteria:**
- [ ] Coverage report generated after test run
- [ ] Sanitiser rules: 100% coverage
- [ ] Classifier accuracy: >95%
- [ ] Formatter coverage: 100%
- [ ] Pipeline pass rate: >98%

**Test Cases:**
- Coverage targets met per Section 12.5

**Complexity:** Small

---

## P10: Visual Preview Tool

HTML preview for rapid iteration.

### P10.1: Discord Style CSS

**Description:** Create CSS mimicking Discord's message styling.

**Files:**
- Create: `tools/preview/discord.css`
- Create: `tools/preview/index.html`

**Implementation:**
```css
/* Discord dark theme approximation */
.discord-message {
    background: #36393f;
    color: #dcddde;
    font-family: Whitney, Helvetica Neue, Helvetica, Arial, sans-serif;
    padding: 16px;
    border-radius: 8px;
}
.discord-embed {
    border-left: 4px solid var(--embed-color);
    background: #2f3136;
    padding: 12px;
    margin: 8px 0;
}
```

**Dependencies:** P0-P6

**Acceptance Criteria:**
- [ ] Preview looks like Discord messages
- [ ] Embeds render with coloured border
- [ ] Code blocks formatted with monospace
- [ ] Dark theme matching Discord

**Test Cases:**
- Visual comparison with real Discord messages

**Complexity:** Small

---

### P10.2: Preview CLI

**Description:** CLI tool to preview pipeline output.

**Files:**
- Create: `tools/preview/preview.py`

**Implementation:**
```python
@click.command()
@click.option('--prompt', help='User prompt to simulate')
@click.option('--input', help='CC output file to process')
def preview(prompt, input):
    """Generate Discord-style HTML preview."""
    raw = Path(input).read_text() if input else get_sample_output(prompt)
    result = pipeline.process(raw, {'userPrompt': prompt})
    html = render_to_html(result)

    preview_path = Path('tools/preview/output.html')
    preview_path.write_text(html)
    webbrowser.open(f'file://{preview_path.absolute()}')

# Usage: python tools/preview/preview.py --prompt "What's LEGO 42100 worth?"
```

**Dependencies:** P10.1

**Acceptance Criteria:**
- [ ] CLI accepts prompt or input file
- [ ] Generates HTML preview
- [ ] Opens in default browser
- [ ] Shows all message parts (content, embeds, chunks)

**Test Cases:**
- Manual: run preview, verify output looks correct

**Complexity:** Small

---

## Summary: Files to Create/Modify

### New Files (18)

| File | Phase | Purpose |
|------|-------|---------|
| `domains/peterbot/response/__init__.py` | P0 | Package init |
| `domains/peterbot/response/sanitiser.py` | P0 | Sanitiser implementation |
| `domains/peterbot/response/pipeline.py` | P0 | Main pipeline orchestration |
| `domains/peterbot/response/chunker.py` | P1 | Message chunking |
| `domains/peterbot/response/classifier.py` | P6 | Response type classification |
| `domains/peterbot/response/formatters/__init__.py` | P2 | Formatters package |
| `domains/peterbot/response/formatters/conversational.py` | P2 | Conversational formatter |
| `domains/peterbot/response/formatters/table.py` | P3 | Table formatter |
| `domains/peterbot/response/formatters/search.py` | P4 | Search result formatters |
| `domains/peterbot/response/formatters/proactive.py` | P7 | Proactive message formatters |
| `domains/peterbot/response/feedback.py` | P5 | Long-running feedback |
| `tests/response/__init__.py` | P9 | Tests package |
| `tests/response/validators.py` | P9 | Validation rules |
| `tests/response/test_pipeline.py` | P9 | Pipeline tests |
| `tests/response/migration_test.py` | P8 | Migration regression tests |
| `tools/preview/discord.css` | P10 | Preview styling |
| `tools/preview/index.html` | P10 | Preview template |
| `tools/preview/preview.py` | P10 | Preview CLI |

### Modified Files (4)

| File | Phase | Changes |
|------|-------|---------|
| `domains/peterbot/router.py` | P0, P5 | Integrate pipeline, add feedback |
| `domains/peterbot/wsl_config/CLAUDE.md` | P8 | Remove lines 26-60, add RESPONSE.md reference |
| `domains/peterbot/wsl_config/PETERBOT_SOUL.md` | P8 | Remove lines 82-134, add boundary note |
| `domains/peterbot/parser.py` | P0 | Deprecate in favour of sanitiser |

### Test Fixtures (5 directories)

| Directory | Purpose |
|-----------|---------|
| `tests/response/__fixtures__/` | Root fixtures |
| `tests/response/__fixtures__/conversational/` | Chat fixtures |
| `tests/response/__fixtures__/search/` | Search fixtures |
| `tests/response/__fixtures__/tables/` | Table fixtures |
| `tests/response/__fixtures__/artifacts/` | CC artifact fixtures |
| `tests/response/stubs/` | 1000-prompt bank |

---

## Appendix A: CLAUDE.md Lines to Remove (26-60)

```markdown
### Discord Formatting (CRITICAL)

**Discord does NOT render markdown tables.** Never use `|---|` table syntax.

For nutrition/health data, format like this:
```
**Today's Nutrition** 🍎

📊 **Calories:** 1,786 / 2,100 (85%)
💪 **Protein:** 140g / 160g (87%)
🍞 **Carbs:** 153g / 263g (58%)
🧈 **Fat:** 68g / 70g (97%)
💧 **Water:** 2,250ml / 3,500ml (64%)

Room for ~300 more cals. Something with 20g protein would nail your target!
```

For meal logs:
```
**Today's Meals** 🍽️

☕ **Breakfast** (8:45am) - Protein bar - 194 cals, 8g protein
☕ **Breakfast** (9:05am) - Flat white - 44 cals
🥗 **Lunch** (12:57pm) - Chicken skewers & eggs - 734 cals, 67g protein
🍝 **Dinner** (6:20pm) - Gammon pasta - 507 cals, 32g protein
🥣 **Snack** (8:04pm) - Protein granola - 307 cals, 29g protein
```

For water logging:
```
💧 Logged 500ml

**Progress:** 2,250ml / 3,500ml (64%)
1,250ml to go!
```
```

---

## Appendix B: PETERBOT_SOUL.md Lines to Remove (82-134)

```markdown
## Discord Formatting

You are responding via Discord. Format accordingly:
- Keep responses punchy - aim for under 500 chars for casual chat
- Use **bold** for emphasis, not headers or complex formatting
- For news/research: bullet points work great
- No code blocks unless sharing actual code
- Emojis help scanability for data displays

**IMPORTANT: Discord does NOT render markdown tables.** Never use `|---|` table syntax.

**For nutrition/health data, use this format:**
```
**Today's Nutrition** 🍎

📊 **Calories:** 2,031 / 2,100 (97%) ✅
💪 **Protein:** 162g / 160g (101%) ✅
🍞 **Carbs:** 178g / 263g (68%)
🧈 **Fat:** 73g / 70g (104%) ⚠️
💧 **Water:** 2,250ml / 3,500ml (64%)

Protein smashed. Carbs low but fine. Push the water!
```

**For meal logs:**
```
**Today's Meals** 🍽️

☕ **Breakfast** (9:05am) - Flat white - 44 cals
🥗 **Lunch** (12:57pm) - Chicken skewers, eggs, veg - 734 cals, 67g protein
🍝 **Dinner** (6:20pm) - Gammon pasta - 507 cals
🥣 **Snack** (8:04pm) - Protein granola & yoghurt - 245 cals
```

**For water logging confirmations:**
```
💧 Logged 500ml

**Progress:** 2,250ml / 3,500ml (64%)
1,250ml to go - keep sipping!
```

**Sources/URLs:**
- ALWAYS use markdown links: `**[Name](url)**` or `[Name](url)`
- NEVER raw URLs - they break on line wrap and look ugly
- Keep to 2-3 key sources, not every page you searched
- Skip URLs entirely for casual answers that didn't need research

**Output Cleanliness:**
- Your response IS what gets posted to Discord
- Do NOT include tool diffs, edit previews, or internal output
- Do NOT include "I'll search for..." narration - just give results
- If you edit a file, just confirm "Updated ✓" - don't show the diff
```

---

## Appendix C: Implementation Priority Order

For quickest value delivery, implement in this order:

1. **P0.1-P0.4** (Sanitiser) — Immediate improvement for all responses
2. **P1.1-P1.3** (Chunker) — Fixes long response truncation
3. **P2.1-P2.3** (Conversational) — Cleans 80% of responses
4. **P5.1-P5.2** (Long-Running Ack) — Better UX for slow tasks
5. **P3.1-P3.3** (Tables) — Fixes table rendering
6. **P6.1-P6.4** (Classifier) — Enables automatic formatting
7. **P4.1-P4.4** (Search) — Better search result presentation
8. **P7.1-P7.3** (Proactive) — Consistent scheduled message format
9. **P8.1-P8.4** (Migration) — Clean up duplicate guidance
10. **P9.1-P9.5** (Test Bank) — Long-term quality assurance
11. **P10.1-P10.2** (Preview) — Developer tooling

---

## Appendix D: Test Case Mapping

| Task | Primary Test Category | Validation Rules |
|------|----------------------|------------------|
| P0.1 | `cc_artifact_contamination` | `no_cc_artifacts` |
| P0.2 | Manual | N/A |
| P0.3 | `cc_artifact_contamination` | `no_cc_artifacts` |
| P1.1 | `long_responses` | `under_2000_chars` |
| P1.2 | `code_requests` | `code_block_properly_fenced` |
| P1.3 | `long_responses` | `chunks_numbered` |
| P2.1 | `casual_conversation` | `no_headers` |
| P2.2 | `json_leakage` | `no_json`, `no_raw_json` |
| P3.1 | `data_table_responses` | `no_markdown_table` |
| P4.1 | `brave_web_search` | `has_embed`, `search_results_in_embed` |
| P4.2 | `brave_news_search` | `has_embed` |
| P5.1 | `long_running` | Manual |
| P6.1 | All categories | Classification accuracy >95% |
| P7.1 | `proactive_messages` | Custom validation |
| P8.1 | Migration tests | File content assertions |

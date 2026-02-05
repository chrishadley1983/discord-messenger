# RESPONSE.md — PeterBot Response Formatting & Rendering Specification

> **Version:** 1.0  
> **Status:** Draft  
> **Referenced by:** CLAUDE.md  
> **Scope:** All PeterBot → Discord message rendering  

---

## 1. Purpose & Problem Statement

PeterBot relays Claude Code responses to Discord. Claude Code was designed for terminal output — not messaging apps. This creates a systematic mismatch between what CC produces and what Discord can render cleanly. This spec defines a **Response Processing Pipeline** that sits between Claude Code output and Discord delivery, ensuring every response looks like it came from an intelligent assistant — not a terminal dump.

### 1.1 Problems This Spec Solves

| # | Problem | Root Cause | Impact |
|---|---------|-----------|--------|
| 1 | **CC Headers & Footers** | Claude Code wraps responses with session info, token counts, tool-use markers, `⏺` bullets, status lines | User sees technical noise before/after the actual answer |
| 2 | **Long-Running Commands** | CC tasks (builds, searches, multi-step reasoning) produce no output for 30-60+ seconds | User thinks Peter is dead; no feedback loop |
| 3 | **Spacing Issues** | CC uses terminal-width formatting (80 cols), excessive blank lines, inconsistent paragraph breaks | Messages look ragged in Discord's variable-width renderer |
| 4 | **Table Formatting** | CC produces markdown tables; Discord has **zero** native table support | Tables render as garbled pipe characters `| col | col |` |
| 5 | **JSON/Technical Leakage** | CC returns raw JSON, XML, API payloads, code blocks when natural language was expected | User asks "what's the weather?" and gets `{"location":"Tonbridge","temp":12}` |
| 6 | **Brave API Output** | Search results arrive as structured data with URLs, snippets, metadata | Need clean rendering of web results, news, images, local search |
| 7 | **Message Length** | CC responses often exceed Discord's 2000 char limit | Messages get truncated or fail to send |
| 8 | **Embed Abuse** | Overuse of embeds for simple responses; underuse for structured content | Inconsistent visual experience |

---

## 2. Architecture

### 2.1 Response Processing Pipeline

```
Claude Code Raw Output (string)
        │
        ▼
  ┌─────────────────────┐
  │ 1. SANITISER         │  Strip CC artifacts (headers, footers, tool markers)
  └──────────┬──────────┘
             │
  ┌──────────▼──────────┐
  │ 2. CLASSIFIER        │  Detect response type (conversational, data, search, etc.)
  └──────────┬──────────┘
             │
  ┌──────────▼──────────┐
  │ 3. FORMATTER         │  Apply Discord-native formatting per type
  └──────────┬──────────┘
             │
  ┌──────────▼──────────┐
  │ 4. CHUNKER           │  Split into Discord-safe message segments
  └──────────┬──────────┘
             │
  ┌──────────▼──────────┐
  │ 5. RENDERER          │  Produce final Discord message objects (text + embeds)
  └──────────┬──────────┘
             │
             ▼
  Discord Message(s)
```

### 2.2 Pipeline Placement in Peter Architecture

```
Discord Message → PeterBot → Claude Code (with MCP servers)
                                    │
                                    ▼
                            Raw CC Response
                                    │
                            ┌───────▼────────┐
                            │ Response        │
                            │ Pipeline        │  ← THIS SPEC
                            │ (response.ts)   │
                            └───────┬────────┘
                                    │
                                    ▼
                            Discord Delivery
```

### 2.3 Reference in CLAUDE.md

Add to CLAUDE.md:

```markdown
## Response Formatting
All responses to Discord MUST pass through the Response Pipeline defined in RESPONSE.md.
Never send raw Claude Code output directly to Discord.
Import: ./src/response/pipeline.ts
```

---

## 3. Stage 1: Sanitiser

The Sanitiser strips Claude Code terminal artifacts that should never reach the user.

### 3.1 CC Artifacts to Strip

```typescript
interface SanitiserRule {
  name: string;
  pattern: RegExp;
  replacement: string;
  description: string;
}

const SANITISER_RULES: SanitiserRule[] = [
  // CC Session Headers
  {
    name: 'cc_session_header',
    pattern: /^╭─.*?─╮\n.*?╰─.*?─╯\n?/gms,
    replacement: '',
    description: 'CC box-drawing session headers'
  },
  // CC Bullet Markers
  {
    name: 'cc_bullet_markers',
    pattern: /^⏺\s*/gm,
    replacement: '',
    description: 'CC bullet point markers (⏺)'
  },
  // CC Tool Use Indicators
  {
    name: 'cc_tool_indicators',
    pattern: /^(?:⎿|├|└)\s*(Read|Write|Edit|Bash|Search|Fetch|Glob|Grep|WebSearch|WebFetch|TodoRead|TodoWrite|mcp__[^\s]+).*$/gm,
    replacement: '',
    description: 'CC tool invocation lines'
  },
  // CC Token/Cost Summaries
  {
    name: 'cc_token_summary',
    pattern: /^(?:Total tokens|Cost|Input|Output|Cache)[\s:].*/gm,
    replacement: '',
    description: 'CC token usage and cost lines'
  },
  // CC Status Lines
  {
    name: 'cc_status_lines',
    pattern: /^(?:Compacting conversation|Continuing|Session resumed).*$/gm,
    replacement: '',
    description: 'CC session status messages'
  },
  // CC Permission Prompts (already handled)
  {
    name: 'cc_permission_prompts',
    pattern: /^(?:Allow|Approve|Press Y).*(?:y\/n|\[Y\/n\]).*$/gmi,
    replacement: '',
    description: 'CC permission/approval prompts'
  },
  // ANSI Escape Codes
  {
    name: 'ansi_codes',
    pattern: /\x1b\[[0-9;]*m/g,
    replacement: '',
    description: 'Terminal colour/style escape codes'
  },
  // Excessive Blank Lines (normalise to max 1)
  {
    name: 'excess_blank_lines',
    pattern: /\n{3,}/g,
    replacement: '\n\n',
    description: 'More than 2 consecutive newlines'
  },
  // Leading/Trailing Whitespace
  {
    name: 'trim_whitespace',
    pattern: /^\s+|\s+$/g,
    replacement: '',
    description: 'Leading and trailing whitespace on full response'
  }
];
```

### 3.2 Sanitiser Processing Order

1. ANSI codes (must be first — they interfere with other pattern matching)
2. CC session headers
3. CC tool indicators  
4. CC bullet markers
5. CC token summaries
6. CC status lines
7. CC permission prompts
8. Excess blank lines
9. Trim

### 3.3 Opt-Out: `--raw` Flag

If Chris sends a message containing `--raw` or `--debug`, bypass the Sanitiser entirely and deliver the unprocessed CC output wrapped in a code block. This is essential for debugging.

---

## 4. Stage 2: Classifier

The Classifier examines sanitised output and assigns a **response type** that determines how the Formatter processes it.

### 4.1 Response Types

```typescript
enum ResponseType {
  // Primary types
  CONVERSATIONAL = 'conversational',     // Natural language chat
  DATA_TABLE = 'data_table',             // Tabular/structured data
  CODE = 'code',                         // Code snippets or technical output
  SEARCH_RESULTS = 'search_results',     // Brave web search results
  NEWS_RESULTS = 'news_results',         // Brave news search results
  IMAGE_RESULTS = 'image_results',       // Brave image search results
  LOCAL_RESULTS = 'local_results',       // Brave local/business search
  LIST = 'list',                         // Ordered or unordered lists
  SCHEDULE = 'schedule',                 // Calendar/reminder/schedule info
  ERROR = 'error',                       // Error messages
  MIXED = 'mixed',                       // Contains multiple types (split and process each)
  
  // Special types
  LONG_RUNNING_ACK = 'long_running_ack', // Intermediate "working on it" messages
  PROACTIVE = 'proactive',               // Peter-initiated messages (reminders, alerts)
}
```

### 4.2 Classification Signals

```typescript
interface ClassificationSignals {
  // Structural signals
  hasMarkdownTable: boolean;        // Contains | pipe | delimited | rows
  hasCodeBlock: boolean;            // Contains ``` fenced blocks
  hasJsonBlock: boolean;            // Contains valid JSON (object or array)
  hasUrlList: boolean;              // Contains multiple URLs in sequence
  hasBulletList: boolean;           // Contains - or * list items
  hasNumberedList: boolean;         // Contains 1. 2. 3. list items
  
  // Content signals
  braveSearchDetected: boolean;     // Response contains Brave search result patterns
  scheduleTerms: boolean;           // Contains time/date/reminder keywords
  errorPatterns: boolean;           // Contains error/exception/failed patterns
  
  // Length signals
  charCount: number;
  lineCount: number;
  codeToProseRatio: number;         // Proportion of content in code blocks
}
```

### 4.3 Classification Logic (priority order)

1. If `braveSearchDetected` → `SEARCH_RESULTS` (or `NEWS_RESULTS` / `IMAGE_RESULTS` / `LOCAL_RESULTS` based on content)
2. If `hasJsonBlock` AND `codeToProseRatio > 0.7` → `CODE`
3. If `hasMarkdownTable` → `DATA_TABLE` (or `MIXED` if also has prose)
4. If `hasCodeBlock` AND `codeToProseRatio > 0.5` → `CODE`
5. If `scheduleTerms` AND structured time data → `SCHEDULE`
6. If `errorPatterns` → `ERROR`
7. If `hasBulletList` OR `hasNumberedList` with 4+ items → `LIST`
8. If multiple types detected → `MIXED`
9. Default → `CONVERSATIONAL`

---

## 5. Stage 3: Formatter

### 5.1 Discord Markdown Reality Check

**Discord supports:**
- Bold: `**text**`
- Italic: `*text*`
- Underline: `__text__`
- Strikethrough: `~~text~~`
- Code inline: `` `code` ``
- Code blocks: ` ```lang\ncode\n``` `
- Block quotes: `> text`
- Spoilers: `||text||`
- Headers: `# H1` `## H2` `### H3`
- Subtext: `-# small text`
- Lists: `- item` or `1. item`
- Masked links: `[text](url)` (in embeds only, not plain messages)

**Discord does NOT support:**
- Tables (markdown tables render as raw pipe characters)
- Images in plain text (only as embeds or URL auto-preview)
- Horizontal rules
- Nested formatting in all contexts
- HTML of any kind

### 5.2 Formatter: CONVERSATIONAL

The most common type. Goal: natural, clean prose that reads like a human assistant.

**Rules:**
1. Strip any remaining markdown headers (`#`, `##`, `###`) — conversational responses should not have headers
2. Convert markdown bold/italic to Discord equivalents (they're the same, but verify no edge cases)
3. For simple Q&A / casual chat: keep to 1-3 paragraphs
4. For substantive requests (summarising documents, detailed nutrition breakdowns, research, trip planning, etc.): **let the response be as long as it needs to be** — the Chunker (Section 6) handles splitting across multiple Discord messages
5. No trailing meta-commentary ("Let me know if you need anything else!")
6. Preserve inline code for technical terms: `LEGO 42100`, `npm install`
7. Strip JSON blocks entirely — extract the natural language summary instead
8. If response contains ONLY JSON with no prose, generate a natural language summary from the JSON data

**JSON Stripping Logic:**
```typescript
function stripJsonFromConversational(text: string): string {
  // If the response is ONLY JSON (no surrounding prose), summarise it
  const trimmed = text.trim();
  if (isValidJson(trimmed)) {
    return '[JSON data detected — should be summarised by CC prompt instructions]';
  }
  
  // If JSON is embedded in prose, remove the JSON blocks and keep the prose
  return text
    .replace(/```json\n[\s\S]*?\n```/g, '')  // Remove fenced JSON
    .replace(/```\n\{[\s\S]*?\}\n```/g, '')   // Remove unfenced JSON in code blocks
    .replace(/\n{3,}/g, '\n\n')               // Clean up gaps
    .trim();
}
```

### 5.3 Formatter: DATA_TABLE

Discord cannot render markdown tables. Three strategies in priority order:

**Strategy A: Embed Fields (preferred for small tables, ≤6 rows × 4 cols)**
```typescript
// Convert markdown table to Discord embed with fields
function tableToEmbedFields(table: ParsedTable): EmbedBuilder {
  const embed = new EmbedBuilder()
    .setColor(0x5865F2); // Discord blurple
  
  // Use inline fields to simulate columns
  for (const row of table.rows) {
    for (let i = 0; i < row.cells.length; i++) {
      embed.addFields({
        name: table.headers[i] || '\u200b',
        value: row.cells[i] || '\u200b',
        inline: true
      });
    }
    // Add spacer between rows if needed
  }
  return embed;
}
```

**Strategy B: Code Block (for wider tables or data-heavy content)**
```typescript
// Render table using fixed-width code block
function tableToCodeBlock(table: ParsedTable): string {
  // Calculate column widths
  const colWidths = table.headers.map((h, i) => {
    const maxData = Math.max(...table.rows.map(r => (r.cells[i] || '').length));
    return Math.max(h.length, maxData, 3);
  });
  
  // Build fixed-width table
  const header = table.headers.map((h, i) => h.padEnd(colWidths[i])).join(' │ ');
  const separator = colWidths.map(w => '─'.repeat(w)).join('─┼─');
  const rows = table.rows.map(r =>
    r.cells.map((c, i) => (c || '').padEnd(colWidths[i])).join(' │ ')
  );
  
  return '```\n' + header + '\n' + separator + '\n' + rows.join('\n') + '\n```';
}
```

**Strategy C: Prose Conversion (for 2-3 column comparison tables)**
```typescript
// Convert simple comparison table to readable prose
// e.g., "Platform | Price | Rating" →
// "**eBay UK**: £380-£450, rated 4.5★
//  **Amazon**: £410, rated 4.2★"
```

**Selection Logic:**
- ≤4 columns AND ≤6 rows → Strategy A (Embed Fields)
- >4 columns OR >6 rows → Strategy B (Code Block)
- 2-3 columns AND comparison-style → Strategy C (Prose)
- Honour user preference if they say "show as table" or "give me a list"

### 5.4 Formatter: SEARCH_RESULTS (Brave Web Search)

Render as a clean Discord embed:

```typescript
function formatSearchResults(results: BraveSearchResult[]): EmbedBuilder[] {
  const embed = new EmbedBuilder()
    .setColor(0xFB542B) // Brave orange
    .setAuthor({ name: '🔍 Web Search' })
    .setDescription(results.slice(0, 10).map((r, i) =>
      `**${i + 1}. [${r.title}](${r.url})**\n${truncate(r.snippet, 100)}`
    ).join('\n\n'));
  
  // Add footer with result count
  embed.setFooter({ text: `${results.length} results found` });
  
  return [embed];
}
```

**Natural Language Wrapper:**
Before the embed, include a 1-2 sentence natural language summary of the findings. Never dump raw search results without context.

```
Based on current listings, LEGO 42100 is going for around £380-£450 new/sealed on eBay UK.

[Embed: Search Results]
```

### 5.5 Formatter: NEWS_RESULTS

```typescript
function formatNewsResults(results: BraveNewsResult[]): EmbedBuilder {
  return new EmbedBuilder()
    .setColor(0x1DA1F2) // News blue
    .setAuthor({ name: '📰 News' })
    .setDescription(results.slice(0, 10).map(r =>
      `**[${r.title}](${r.url})**\n` +
      `-# ${r.source} • ${formatRelativeTime(r.publishedAt)}\n` +
      `${truncate(r.snippet, 80)}`
    ).join('\n\n'));
}
```

### 5.6 Formatter: IMAGE_RESULTS

Discord auto-renders image URLs when they're the sole content of a message or in an embed.

```typescript
function formatImageResults(results: BraveImageResult[]): EmbedBuilder[] {
  return results.slice(0, 3).map(r =>
    new EmbedBuilder()
      .setImage(r.url)
      .setFooter({ text: truncate(r.title, 50) })
  );
}
```

### 5.7 Formatter: LOCAL_RESULTS

```typescript
function formatLocalResults(results: BraveLocalResult[]): EmbedBuilder {
  return new EmbedBuilder()
    .setColor(0x34A853) // Google Maps green
    .setAuthor({ name: '📍 Local Results' })
    .setDescription(results.slice(0, 10).map(r =>
      `**${r.name}** ${r.rating ? '⭐'.repeat(Math.round(r.rating)) : ''}\n` +
      `${r.address}\n` +
      (r.phone ? `📞 ${r.phone}` : '')
    ).join('\n\n'));
}
```

### 5.8 Formatter: CODE

CC has direct file access, so Peter rarely needs to see raw code in Discord. Default to **summarising what was done** unless explicitly asked to show code.

```typescript
function formatCode(content: string): string {
  // Default: summarise the work, don't dump code
  // Only show code if user explicitly asked ("show me the code", "show me the API output", etc.)
  const showRaw = context.userPrompt && 
    /show me|see the|raw|output|dump|paste|print/i.test(context.userPrompt);
  
  if (!showRaw) {
    // Extract prose/summary from CC output, strip code blocks
    const prose = extractProse(content);
    if (prose.length > 0) return prose;
    // If no prose, generate a brief summary of what the code does
    return summariseCodeActions(content);
  }
  
  // Explicit request: show code properly formatted
  const langMatch = content.match(/```(\w+)/);
  const lang = langMatch?.[1] || '';
  const codeBlocks = extractCodeBlocks(content);
  const prose = extractProse(content);
  
  // Cap at 30 lines per block — offer file save for longer
  const cappedBlocks = codeBlocks.map(b => {
    const lines = b.code.split('\n');
    if (lines.length > 30) {
      return {
        ...b,
        code: lines.slice(0, 30).join('\n') + '\n// ... truncated',
        truncated: true
      };
    }
    return { ...b, truncated: false };
  });
  
  let result = prose + '\n' + cappedBlocks.map(b =>
    '```' + (b.lang || lang) + '\n' + b.code + '\n```'
  ).join('\n');
  
  if (cappedBlocks.some(b => b.truncated)) {
    result += '\n-# Full output saved to file — ask if you want the path';
  }
  
  return result;
}
```

### 5.9 Formatter: SCHEDULE

For reminders, calendar data, and time-based content:

```typescript
function formatSchedule(content: string, events: ScheduleEvent[]): string {
  if (events.length === 0) return content;
  
  return events.map(e => {
    const emoji = getScheduleEmoji(e.type); // 📅 📌 ⏰ 🏃
    const time = formatDiscordTimestamp(e.datetime); // Discord <t:unix:R> format
    return `${emoji} **${e.title}**\n${time}${e.location ? ' • ' + e.location : ''}`;
  }).join('\n\n');
}

// Use Discord's native timestamp formatting for times
// <t:1738368000:R> → "in 3 hours"
// <t:1738368000:F> → "Sunday, 2 February 2026 10:00"
function formatDiscordTimestamp(date: Date): string {
  const unix = Math.floor(date.getTime() / 1000);
  return `<t:${unix}:F> (<t:${unix}:R>)`;
}
```

### 5.10 Formatter: ERROR

Show both the human-readable summary **and** the raw trace (collapsed in a code block) so Peter can debug if needed:

```typescript
function formatError(content: string): string {
  const userMessage = extractErrorSummary(content);
  const rawTrace = extractErrorTrace(content);
  
  let result = `⚠️ ${userMessage}`;
  
  if (rawTrace && rawTrace.length > 0) {
    // Include raw trace in a code block for debugging
    const truncatedTrace = rawTrace.length > 800 
      ? rawTrace.slice(0, 800) + '\n... (truncated)'
      : rawTrace;
    result += `\n\n\`\`\`\n${truncatedTrace}\n\`\`\``;
  }
  
  return result;
}
```

### 5.11 Formatter: MIXED

Split content into segments, classify each, format individually, then reassemble:

```typescript
function formatMixed(content: string): FormattedSegment[] {
  const segments = splitIntoSegments(content);
  return segments.map(seg => ({
    type: classifySegment(seg),
    formatted: formatSegment(seg)
  }));
}
```

---

## 6. Stage 4: Chunker

Discord imposes hard limits. The Chunker splits formatted content into deliverable segments.

### 6.1 Discord Limits

| Property | Limit |
|----------|-------|
| Message content | 2,000 characters |
| Embed title | 256 characters |
| Embed description | 4,096 characters |
| Embed fields | 25 per embed |
| Embed field name | 256 characters |
| Embed field value | 1,024 characters |
| Embeds per message | 10 |
| Total embed characters | 6,000 |
| Messages per channel per second | 5 (bot rate limit) |

### 6.2 Chunking Strategy

Inspired by OpenClaw's EmbeddedBlockChunker:

```typescript
interface ChunkerConfig {
  maxChars: number;          // 1900 (leave buffer below 2000)
  maxLinesPerMessage: number; // 20 (prevent visual overwhelm)
  minChars: number;          // 200 (don't send tiny fragments)
}

enum SplitPriority {
  PARAGRAPH = 1,    // Split on \n\n (preferred)
  NEWLINE = 2,      // Split on \n
  SENTENCE = 3,     // Split on '. ' or '.\n'
  WHITESPACE = 4,   // Split on ' '
  HARD_BREAK = 5,   // Split at maxChars (last resort)
}
```

**Critical Rules:**
1. **Never split inside a code block** — if a code fence would be split, close it and re-open in the next chunk
2. **Never split inside an embed** — embeds are atomic
3. **Prefer paragraph boundaries** — split on `\n\n` before anything else
4. **Keep lists together** — don't split a list across messages if avoidable
5. **Number the chunks** if there are 3+ — add `-# (1/3)` `-# (2/3)` `-# (3/3)` using Discord subtext

### 6.3 Code Fence Safety

```typescript
function splitPreservingCodeFences(text: string, maxChars: number): string[] {
  const chunks: string[] = [];
  let current = '';
  let inCodeBlock = false;
  let codeLang = '';
  
  for (const line of text.split('\n')) {
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        inCodeBlock = false;
        codeLang = '';
      } else {
        inCodeBlock = true;
        codeLang = line.slice(3).trim();
      }
    }
    
    if ((current + '\n' + line).length > maxChars) {
      // Need to split
      if (inCodeBlock) {
        // Close the code block in current chunk
        current += '\n```';
        chunks.push(current.trim());
        // Re-open in next chunk
        current = '```' + codeLang + '\n' + line;
      } else {
        chunks.push(current.trim());
        current = line;
      }
    } else {
      current += (current ? '\n' : '') + line;
    }
  }
  
  if (current.trim()) chunks.push(current.trim());
  return chunks;
}
```

---

## 7. Stage 5: Renderer

The Renderer converts formatted segments into Discord API objects.

### 7.1 Render Decisions

```typescript
interface RenderDecision {
  useEmbed: boolean;      // Should this be an embed or plain text?
  embedColor: number;     // Colour coding by content type
  includeTimestamp: boolean;
  includeFooter: boolean;
}

const RENDER_RULES: Record<ResponseType, RenderDecision> = {
  CONVERSATIONAL:    { useEmbed: false, embedColor: 0, includeTimestamp: false, includeFooter: false },
  DATA_TABLE:        { useEmbed: true,  embedColor: 0x5865F2, includeTimestamp: false, includeFooter: false },
  CODE:              { useEmbed: false, embedColor: 0, includeTimestamp: false, includeFooter: false },
  SEARCH_RESULTS:    { useEmbed: true,  embedColor: 0xFB542B, includeTimestamp: true,  includeFooter: true },
  NEWS_RESULTS:      { useEmbed: true,  embedColor: 0x1DA1F2, includeTimestamp: true,  includeFooter: true },
  IMAGE_RESULTS:     { useEmbed: true,  embedColor: 0x7C3AED, includeTimestamp: false, includeFooter: true },
  LOCAL_RESULTS:     { useEmbed: true,  embedColor: 0x34A853, includeTimestamp: false, includeFooter: true },
  LIST:              { useEmbed: false, embedColor: 0, includeTimestamp: false, includeFooter: false },
  SCHEDULE:          { useEmbed: false, embedColor: 0, includeTimestamp: false, includeFooter: false },
  ERROR:             { useEmbed: false, embedColor: 0, includeTimestamp: false, includeFooter: false },
  PROACTIVE:         { useEmbed: true,  embedColor: 0xF59E0B, includeTimestamp: true,  includeFooter: false },
  LONG_RUNNING_ACK:  { useEmbed: false, embedColor: 0, includeTimestamp: false, includeFooter: false },
};
```

**Key Principle:** Conversational responses are **always plain text**. Never wrap casual chat in an embed. Embeds are reserved for structured/data content where they add genuine value.

---

## 8. Long-Running Command Handling

### 8.1 The Problem

When Peter sends a complex request to Claude Code (e.g., a build task, multi-step research, Brave search with synthesis), there can be 30-60+ seconds of silence. This is unacceptable in a messaging context.

### 8.2 Solution: Intermediate Feedback System

```typescript
interface LongRunningConfig {
  ackDelayMs: number;           // 3000 — send "thinking" after 3s
  progressIntervalMs: number;   // 30000 — update every 30s
  maxWaitMs: number;            // 600000 — timeout after 10 min
}

// Phase 1: Quick Acknowledgement (3s)
// "🔍 Searching for LEGO 42100 prices..."
// "⚙️ Working on that build..."
// "🧠 Thinking about this..."

// Phase 2: Progress Updates (every 30s)
// "Still working — found 3 search results, synthesising..."
// "Running step 2 of 4..."

// Phase 3: Timeout
// "⚠️ This is taking longer than expected. I'm still working on it — 
//  I'll send the result when it's ready."
```

### 8.3 Detecting Long-Running Commands

The ack message should reflect **what Peter is doing**, not generic "please wait":

```typescript
const ACK_TEMPLATES: Record<string, string> = {
  'brave_web_search':   '🔍 Searching the web...',
  'brave_news_search':  '📰 Checking the latest news...',
  'brave_image_search': '🖼️ Looking for images...',
  'brave_local_search': '📍 Finding local results...',
  'build_task':         '⚙️ Working on that...',
  'file_operation':     '📂 Updating files...',
  'multi_step':         '🧠 Thinking through this — might take a moment...',
  'default':            '💭 Working on it...',
};
```

### 8.4 Implementation Pattern

```typescript
async function handleWithFeedback(
  message: Discord.Message,
  ccPromise: Promise<string>,
  config: LongRunningConfig
): Promise<void> {
  let ackSent = false;
  let ackMessage: Discord.Message | null = null;
  
  // Phase 1: Quick ack timer
  const ackTimer = setTimeout(async () => {
    const taskType = detectTaskType(message.content);
    ackMessage = await message.reply(ACK_TEMPLATES[taskType] || ACK_TEMPLATES.default);
    ackSent = true;
  }, config.ackDelayMs);
  
  // Phase 2: Progress timer
  const progressTimer = setInterval(async () => {
    if (ackMessage) {
      await ackMessage.edit(ackMessage.content + '\n-# Still working...');
    }
  }, config.progressIntervalMs);
  
  try {
    const result = await Promise.race([
      ccPromise,
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('timeout')), config.maxWaitMs)
      )
    ]);
    
    clearTimeout(ackTimer);
    clearInterval(progressTimer);
    
    // Delete the ack message if we sent one, then deliver the real response
    if (ackMessage) await ackMessage.delete().catch(() => {});
    
    // Process through pipeline
    await deliverResponse(message, result as string);
    
  } catch (err) {
    clearTimeout(ackTimer);
    clearInterval(progressTimer);
    
    if (ackMessage) {
      await ackMessage.edit('⚠️ This is taking longer than expected. I\'ll send the result when it\'s ready.');
    }
  }
}
```

---

## 9. Prompt-Level Response Instructions

The pipeline handles post-processing, but we should also **instruct Claude Code** to produce cleaner output in the first place. These instructions should be added to Peter's system prompt / CLAUDE.md:

### 9.1 CC Response Instructions (add to CLAUDE.md / petersoul.md)

```markdown
## Response Format Rules

You are responding via Discord. Follow these rules for ALL responses:

### General
- Respond in natural language unless explicitly asked for code/data
- Never include session info, token counts, or tool-use markers in your response
- Never start responses with "I" repeatedly — vary your sentence openings
- Keep casual responses to 1-3 short paragraphs
- For substantive requests (document summaries, nutrition logs, research, trip plans), give a full thorough response — the pipeline will handle splitting across multiple Discord messages
- Use Discord markdown: **bold**, *italic*, `inline code`, ```code blocks```
- Do NOT use markdown headers (#, ##, ###) in conversational responses
- Do NOT use horizontal rules (---)

### Data & Tables
- Discord cannot render markdown tables — never output pipe-delimited tables
- For comparisons: use embed-friendly format or descriptive prose
- For data: structure as key-value pairs or short lists instead of tables

### Search Results
- When presenting web search results, lead with a 1-2 sentence natural language summary
- Follow with structured results (titles, URLs, snippets)
- Never dump raw JSON search results

### JSON / API Data
- When you receive API data (JSON, XML), translate it to natural language
- Only show raw data if explicitly asked ("show me the JSON", "raw output", "--raw")
- Summarise numerical data conversationally: "The set is going for about £380-£450" not {"price_range":{"min":380,"max":450}}

### Lists
- Use Discord list format: `- item` or `1. item`
- Keep list items to one line each where possible
- Limit to 10 items unless more are specifically requested

### Code
- Default to **summarising what you did** — Peter can see the files directly via CC
- Only show raw code if Peter explicitly asks ("show me the code", "show me the API output", "paste the function")
- When showing code, use fenced code blocks with language hints: ```javascript
- Cap code blocks at 30 lines — offer file path for longer output
- Include a brief natural language explanation before or after code

### Reminders & Scheduling
- Use Discord timestamp format: <t:UNIX:F> for absolute, <t:UNIX:R> for relative
- Lead with the most important time info, then details

### Long Responses
- If your response would exceed ~1500 characters, structure it with clear sections
- Use **bold** section labels instead of headers for Discord readability
- End with the most actionable information
```

---

## 10. Brave API Response Handling — Specific Patterns

### 10.1 Brave Search Tool → Response Type Mapping

| Brave MCP Tool | Response Type | Formatting |
|----------------|---------------|------------|
| `brave_web_search` | SEARCH_RESULTS | Embed with links + NL summary |
| `brave_news_search` | NEWS_RESULTS | Embed with sources + timestamps |
| `brave_image_search` | IMAGE_RESULTS | Image embeds (max 3) |
| `brave_local_search` | LOCAL_RESULTS | Embed with ratings, address, phone |
| `brave_video_search` | SEARCH_RESULTS | Embed with video links (thumbnail if available) |

### 10.2 Search Result Quality Rules

1. **Always summarise first** — never lead with an embed
2. **Limit to 10 results** unless user asks for more (or fewer)
3. **Truncate snippets** to 100 chars in embeds (full text is at the URL)
4. **De-duplicate** results with same domain
5. **Date-stamp** news results using Discord relative timestamps
6. **Personal context** — if the search relates to something Peter knows (LEGO prices, Japan trip, running events), add a connecting sentence

### 10.3 Example Flows

**Price Check:**
```
Chris: What's the going rate for LEGO 42100 on eBay UK?

Peter: The Technic Liebherr R 9800 is currently going for around £380-£450 
new/sealed on eBay UK. Open box sets are closer to £300-£340.

[Embed: 🔍 Web Search — 3 results with eBay links]
```

**Weather:**
```
Chris: What's the weather like tomorrow?

Peter: Looking mild for Tonbridge tomorrow — around 9°C with clouds and 
a chance of light rain in the afternoon. Good enough for a run if 
you go in the morning.
```

**News:**
```
Chris: Any LEGO news?

Peter: Couple of things worth knowing:

[Embed: 📰 News — 3 results with LEGO Group announcements]
```

---

## 11. Proactive Message Formatting

Peter-initiated messages (reminders, morning briefings, alerts) need distinct formatting to be recognisable as proactive:

### 11.1 Morning Briefing Format

```
☀️ **Morning, Chris**

**Weather** — 8°C, partly cloudy. Good running conditions.
**Calendar** — 2 meetings today: standup at 9:30, 1:1 with client at 14:00
**eBay** — 3 items sold overnight (£47.50 total)
**Reminders** — Max's PE kit needs washing

-# 06:45 • Proactive briefing
```

### 11.2 Reminder Format

```
⏰ **Reminder**
Put the bins out — collection tomorrow morning.

-# Scheduled reminder
```

### 11.3 Alert Format

```
🔔 **eBay Alert**
Someone made an offer on LEGO 42115 Lamborghini — £180 (asking £210).
BrickLink average is £195.

React ✅ to accept, ❌ to decline, or reply with a counter.

-# Automatic offer notification
```

---

## 12. Testing Plan

### 12.1 Test Architecture

```
tests/
  response/
    __fixtures__/           # Raw CC output samples (real captures)
    sanitiser.test.ts       # Sanitiser unit tests
    classifier.test.ts      # Classifier unit tests  
    formatter.test.ts       # Formatter unit tests (per type)
    chunker.test.ts         # Chunker unit tests
    renderer.test.ts        # Renderer unit tests
    pipeline.test.ts        # Full pipeline integration tests
    migration.test.ts       # Migration regression tests (Section 13.7)
    scenarios/              # End-to-end scenario tests
      conversational.test.ts
      search-results.test.ts
      tables.test.ts
      code.test.ts
      scheduling.test.ts
      long-running.test.ts
      proactive.test.ts
      edge-cases.test.ts
    stubs/                  # Stub test prompt bank
      prompts.json          # 1000 test prompts
      expected-types.json   # Expected classification for each
```

### 12.2 Stub Testing: The 1000-Prompt Bank

The prompt bank tests classification accuracy across all response types. Each prompt simulates a real CC interaction scenario.

#### 12.2.1 Prompt Categories (1000 total)

| Category | Count | Examples |
|----------|-------|---------|
| **Casual Conversation** | 150 | "how's it going", "what should I have for lunch", "tell me a joke" |
| **Factual Q&A** | 100 | "when was LEGO founded", "what's the capital of Japan", "how far is Tokyo from Kyoto" |
| **Brave Web Search** | 100 | "what's LEGO 42100 worth", "weather in Tonbridge", "best running shoes 2026" |
| **Brave News Search** | 50 | "any LEGO news today", "what happened in the marathon yesterday" |
| **Brave Image Search** | 30 | "show me what Tokyo Skytree looks like", "picture of LEGO 42115" |
| **Brave Local Search** | 30 | "restaurants near me", "running shops in Tonbridge" |
| **Code Requests** | 80 | "write a function to sort LEGO sets by price", "fix this TypeScript error" |
| **Data/Table Responses** | 80 | "compare these 5 LEGO sets", "eBay sales this week", "show my inventory" |
| **Schedule/Calendar** | 60 | "what's on my calendar tomorrow", "remind me at 5pm", "when is the half marathon" |
| **List Requests** | 50 | "top 10 things to do in Tokyo", "my eBay listings", "shopping list for dinner" |
| **Mixed Content** | 60 | "research LEGO 42100 and give me a price comparison with alternatives" |
| **Error Scenarios** | 40 | CC timeout, API failures, rate limits, empty results |
| **CC Artifact Contamination** | 50 | Responses with headers, footers, tool markers, ANSI codes mixed in |
| **JSON Leakage** | 40 | Responses containing raw JSON that should be summarised |
| **Long Responses (>2000 chars)** | 40 | Multi-paragraph explanations, detailed research results |
| **Proactive Messages** | 20 | Morning briefings, eBay alerts, reminders |
| **Edge Cases** | 20 | Empty responses, single-word answers, emoji-only, Unicode |

#### 12.2.2 Test Prompt Structure

```json
{
  "id": "conv-001",
  "category": "casual_conversation",
  "userPrompt": "how's it going Peter?",
  "ccRawOutput": "I'm doing well! Always ready to help. What are you working on today?",
  "expectedType": "CONVERSATIONAL",
  "expectedSanitiserActions": [],
  "expectedFormat": "plain_text",
  "expectedChunks": 1,
  "validationRules": [
    "no_embed",
    "no_headers",
    "no_json",
    "under_500_chars",
    "no_cc_artifacts"
  ]
}
```

```json
{
  "id": "search-042",
  "category": "brave_web_search",
  "userPrompt": "What's LEGO 42100 going for on eBay UK?",
  "ccRawOutput": "⏺ Searching for LEGO 42100 prices...\n\n  brave_web_search: \"LEGO 42100 eBay UK price\"\n\n⏺ Based on the search results, the LEGO Technic Liebherr R 9800 (42100) is currently listing at:\n\n| Platform | Price Range | Condition |\n|----------|------------|----------|\n| eBay UK | £380-£450 | New/Sealed |\n| eBay UK | £300-£340 | Open Box |\n| BrickLink | £360-£420 | New |\n\nHere are the top results:\n\n1. **LEGO Technic 42100** - https://ebay.co.uk/...\n   £399.99 new sealed\n2. **Liebherr R 9800** - https://ebay.co.uk/...\n   £385.00 free postage\n\nTotal tokens: 1,247 | Cost: $0.003",
  "expectedType": "MIXED",
  "expectedSanitiserActions": ["strip_cc_bullet_markers", "strip_cc_tool_indicators", "strip_cc_token_summary"],
  "expectedFormat": "text_plus_embed",
  "expectedChunks": 1,
  "validationRules": [
    "has_natural_language_summary",
    "has_embed",
    "no_markdown_table",
    "no_cc_artifacts",
    "no_raw_json",
    "search_results_in_embed"
  ]
}
```

```json
{
  "id": "artifact-015",
  "category": "cc_artifact_contamination",
  "userPrompt": "What time is my next meeting?",
  "ccRawOutput": "╭────────────────────────────────────────╮\n│ Session: peter-main (claude-4-sonnet)  │\n╰────────────────────────────────────────╯\n\n⏺ Let me check your calendar.\n\n  mcp__gcal__list_events\n\n⏺ Your next meeting is a 1:1 with the client at 2:00 PM today.\n\nTotal tokens: 832 | Cost: $0.002",
  "expectedType": "CONVERSATIONAL",
  "expectedSanitiserActions": ["strip_cc_session_header", "strip_cc_bullet_markers", "strip_cc_tool_indicators", "strip_cc_token_summary"],
  "expectedFormat": "plain_text",
  "expectedChunks": 1,
  "validationRules": [
    "no_embed",
    "no_cc_artifacts",
    "contains_meeting_info",
    "uses_discord_timestamp_or_natural_time",
    "under_300_chars"
  ]
}
```

#### 12.2.3 Validation Rules Catalogue

```typescript
const VALIDATION_RULES: Record<string, (output: RenderedMessage) => boolean> = {
  'no_embed':             (m) => m.embeds.length === 0,
  'has_embed':            (m) => m.embeds.length > 0,
  'no_headers':           (m) => !/^#{1,3}\s/m.test(m.content),
  'no_json':              (m) => !isValidJson(m.content) && !/```json/i.test(m.content),
  'no_cc_artifacts':      (m) => !containsCcArtifacts(m.content),
  'no_markdown_table':    (m) => !/\|.*\|.*\|/m.test(m.content.replace(/```[\s\S]*?```/g, '')),
  'no_raw_json':          (m) => !/^\s*[\[{]/.test(m.content.trim()),
  'under_300_chars':      (m) => m.content.length < 300,
  'under_500_chars':      (m) => m.content.length < 500,
  'under_2000_chars':     (m) => m.content.length <= 2000,
  'has_natural_language':  (m) => m.content.split(' ').length > 5,
  'has_natural_language_summary': (m) => m.content.split('\n')[0].split(' ').length > 5,
  'search_results_in_embed': (m) => m.embeds.some(e => e.description?.includes('http')),
  'contains_meeting_info': (m) => /meeting|1:1|standup|call/i.test(m.content),
  'uses_discord_timestamp_or_natural_time': (m) => /<t:\d+:[FfDdTtR]>/.test(m.content) || /\d{1,2}:\d{2}|today|tomorrow|tonight/i.test(m.content),
  'code_block_properly_fenced': (m) => {
    const unfenced = m.content.replace(/```[\s\S]*?```/g, '');
    return !/(?:function|const|let|var|import|class)\s+\w+/.test(unfenced);
  },
  'chunks_numbered':      (m) => /\(\d+\/\d+\)/.test(m.content),
  'max_list_items_10':    (m) => (m.content.match(/^[-*]\s/gm) || []).length <= 10,
};
```

#### 12.2.4 Test Execution

```typescript
describe('Response Pipeline - 1000 Prompt Stub Tests', () => {
  const prompts: TestPrompt[] = loadTestPrompts('tests/response/stubs/prompts.json');
  
  for (const prompt of prompts) {
    it(`[${prompt.id}] ${prompt.category}: "${truncate(prompt.userPrompt, 50)}"`, async () => {
      // Run through full pipeline
      const result = await pipeline.process(prompt.ccRawOutput, {
        userPrompt: prompt.userPrompt,
        channel: 'discord'
      });
      
      // Check classification
      expect(result.detectedType).toBe(prompt.expectedType);
      
      // Check sanitiser actions
      for (const action of prompt.expectedSanitiserActions) {
        expect(result.sanitiserLog).toContain(action);
      }
      
      // Check format
      expect(result.format).toBe(prompt.expectedFormat);
      
      // Check chunk count
      expect(result.chunks.length).toBe(prompt.expectedChunks);
      
      // Run validation rules
      for (const rule of prompt.validationRules) {
        expect(VALIDATION_RULES[rule](result.rendered)).toBe(true);
      }
    });
  }
});
```

### 12.3 Regression Testing

Two categories of regression:

**A. Live regressions** — Every time a real Discord message triggers a formatting issue:
1. Capture the raw CC output
2. Add it to the fixture bank
3. Write a test that reproduces the issue
4. Fix the pipeline
5. Ensure all 1000+ tests still pass

**B. Migration regressions** — After stripping formatting from CLAUDE.md / petersoul.md:
1. Run `migration.test.ts` (see Section 13.7)
2. Verify no formatting rules remain in CLAUDE.md or petersoul.md
3. Verify no conflicting instructions across files
4. Verify proactive messages still render correctly
5. Full 1000-prompt bank passes
6. Manual spot-check with 5 live messages

### 12.4 Visual Verification

For initial development, add a `--preview` mode that renders pipeline output as HTML mimicking Discord's styling. This allows quick visual verification without sending actual Discord messages.

```bash
npm run test:preview -- --prompt "What's LEGO 42100 worth?"
# Opens browser with Discord-style preview of the formatted response
```

### 12.5 Test Coverage Targets

| Component | Target |
|-----------|--------|
| Sanitiser rules | 100% (every regex tested with positive and negative cases) |
| Classifier accuracy | >95% across 1000 prompts |
| Formatter type coverage | 100% (every ResponseType has ≥10 test cases) |
| Chunker edge cases | 100% (code fence splits, embed boundaries, exact-2000-char messages) |
| Pipeline integration | >98% pass rate on full 1000 prompt bank |

---

## 13. Migration: Stripping Guidance from CLAUDE.md and petersoul.md

### 13.1 Separation of Concerns

| File | Owns | After Migration |
|------|------|----------------|
| **CLAUDE.md** | CC operational rules, tool config, session management | Remove ALL formatting/rendering rules. Single reference to RESPONSE.md. |
| **petersoul.md** | Personality, tone, humour, relationship with Chris | Remove ALL Discord formatting, table handling, embed rules, message length logic. Keep ONLY tone/voice/personality. |
| **RESPONSE.md** (this file) | ALL response formatting & rendering | Authoritative source for formatting, chunking, rendering, sanitising, proactive message formats. |
| **response/pipeline.ts** | Code implementation | Pipeline stages as executable code. |

### 13.2 What to Strip from petersoul.md

Remove and migrate to RESPONSE.md:
- Discord markdown formatting rules (bold, italic, code blocks, etc.)
- Table rendering preferences and constraints
- Code block formatting rules
- Message length handling / chunking guidance
- Embed usage rules (when to use embeds, colours, structure)
- Search result formatting guidance
- Proactive message templates (morning briefing format, reminder format, alert format)
- Any rules about headers, lists, or structural formatting in Discord

**Keep in petersoul.md:**
- Personality traits and voice
- Tone and formality level
- Humour style and boundaries
- Relationship context with Chris/family
- How Peter addresses Chris (first name, casual, etc.)
- Emotional intelligence / empathy rules
- Topics Peter is knowledgeable about

### 13.3 What to Strip from CLAUDE.md

Remove and migrate to RESPONSE.md:
- Any Discord-specific formatting instructions
- Response length guidance
- Table formatting rules
- Code output formatting rules
- Embed construction rules
- Search result presentation rules
- Proactive/scheduled message formatting

**Keep in CLAUDE.md:**
- Session management and tool configuration
- MCP server references and tool access rules
- File system and project structure
- Memory system configuration (heartbeat, session, etc.)
- Development workflow rules
- API keys and credentials handling
- Error handling at the CC/system level (not Discord formatting of errors)

### 13.4 CLAUDE.md Reference (add after migration)

Replace all stripped formatting content with this single reference:

```markdown
## Response Formatting
@RESPONSE.md governs ALL response formatting for Discord delivery.
Every response passes through the Response Pipeline before reaching Discord.
Never bypass the pipeline. For debugging, use --raw flag.
```

### 13.5 petersoul.md Reference (add after migration)

Add a note to petersoul.md clarifying the boundary:

```markdown
## Formatting
All Discord formatting, message structure, embeds, chunking, and rendering 
rules live in @RESPONSE.md. This file (petersoul.md) only governs Peter's 
personality, tone, and voice — not how messages are structured or displayed.
```

### 13.6 Proactive Message Consistency Check

After migration, verify that proactive message formats (Section 11) remain consistent:
- Morning briefing format (☀️) — template lives here, tone comes from petersoul.md
- Reminder format (⏰) — template here, wording style from petersoul.md
- Alert format (🔔) — template + reaction options here, personality from petersoul.md
- The pipeline must apply sanitiser + formatter + chunker to proactive messages too, not just user-triggered responses

### 13.7 Migration Regression Testing

After stripping guidance from CLAUDE.md and petersoul.md, run a dedicated regression pass to ensure nothing is lost or contradictory:

```typescript
describe('Migration Regression Tests', () => {
  
  // 1. Verify RESPONSE.md is the single source of truth
  describe('Source of Truth', () => {
    it('CLAUDE.md contains no formatting rules', () => {
      const claude = loadFile('CLAUDE.md');
      // Should not contain Discord-specific formatting guidance
      expect(claude).not.toMatch(/discord.*format/i);
      expect(claude).not.toMatch(/embed.*colour/i);
      expect(claude).not.toMatch(/chunk|split.*message/i);
      expect(claude).not.toMatch(/markdown.*table/i);
      // Should contain exactly one reference to RESPONSE.md
      expect(claude.match(/@?RESPONSE\.md/g)?.length).toBe(1);
    });
    
    it('petersoul.md contains no formatting rules', () => {
      const soul = loadFile('petersoul.md');
      expect(soul).not.toMatch(/embed|code.?block|chunk|2000.*char/i);
      expect(soul).not.toMatch(/discord.*markdown/i);
      expect(soul).not.toMatch(/table.*render|pipe.*delimit/i);
      // Should contain personality/tone content
      expect(soul).toMatch(/tone|personality|voice|humour/i);
    });
    
    it('RESPONSE.md contains all formatting rules', () => {
      const response = loadFile('RESPONSE.md');
      expect(response).toMatch(/sanitiser/i);
      expect(response).toMatch(/classifier/i);
      expect(response).toMatch(/formatter/i);
      expect(response).toMatch(/chunker/i);
      expect(response).toMatch(/renderer/i);
      expect(response).toMatch(/proactive/i);
    });
  });
  
  // 2. Verify no conflicting instructions
  describe('No Conflicts', () => {
    it('no contradictory formatting rules across files', () => {
      const claude = loadFile('CLAUDE.md');
      const soul = loadFile('petersoul.md');
      const response = loadFile('RESPONSE.md');
      
      // If CLAUDE.md or petersoul.md mention formatting, 
      // they should only point to RESPONSE.md
      const claudeFormatMentions = claude.match(/format/gi) || [];
      for (const mention of claudeFormatMentions) {
        // Context around mention should reference RESPONSE.md
        // (implementation: check surrounding lines)
      }
    });
  });
  
  // 3. Verify proactive messages still work post-migration
  describe('Proactive Message Consistency', () => {
    it('morning briefing renders correctly', async () => {
      const result = await pipeline.process(MORNING_BRIEFING_FIXTURE, {
        messageType: 'proactive',
        channel: 'discord'
      });
      expect(result.rendered.content).toMatch(/☀️/);
      expect(result.rendered.content).toMatch(/-#.*proactive/i);
    });
    
    it('reminder renders correctly', async () => {
      const result = await pipeline.process(REMINDER_FIXTURE, {
        messageType: 'proactive',
        channel: 'discord'
      });
      expect(result.rendered.content).toMatch(/⏰/);
    });
    
    it('alert renders with reaction prompt', async () => {
      const result = await pipeline.process(ALERT_FIXTURE, {
        messageType: 'proactive',
        channel: 'discord'
      });
      expect(result.rendered.content).toMatch(/✅|❌/);
    });
  });
  
  // 4. Full pipeline still passes after migration
  describe('Pipeline Regression', () => {
    it('all 1000 prompt bank tests still pass', async () => {
      const prompts = loadTestPrompts('tests/response/stubs/prompts.json');
      const results = await Promise.all(
        prompts.map(p => pipeline.process(p.ccRawOutput, {
          userPrompt: p.userPrompt,
          channel: 'discord'
        }))
      );
      
      const failures = results.filter((r, i) => {
        const p = prompts[i];
        return r.detectedType !== p.expectedType ||
          !p.validationRules.every(rule => VALIDATION_RULES[rule](r.rendered));
      });
      
      expect(failures.length).toBe(0);
    });
  });
});
```

### 13.8 Migration Checklist

Run through this checklist after completing the migration:

- [ ] All formatting rules removed from CLAUDE.md
- [ ] All formatting rules removed from petersoul.md
- [ ] Single `@RESPONSE.md` reference added to CLAUDE.md
- [ ] Formatting boundary note added to petersoul.md
- [ ] Proactive message templates (briefing, reminder, alert) confirmed in RESPONSE.md Section 11
- [ ] No duplicate or conflicting rules across the three files
- [ ] Migration regression tests pass
- [ ] Full 1000-prompt test bank passes
- [ ] Manual spot-check: send 5 real messages to Peter and verify formatting

---

## 14. Implementation Priority

| Phase | Scope | Effort |
|-------|-------|--------|
| **P0: Sanitiser** | Strip CC artifacts — biggest immediate win | Small |
| **P1: Chunker** | Message splitting with code fence safety | Small |
| **P2: Conversational Formatter** | Clean up 80% of responses | Medium |
| **P3: Table Formatter** | Code block tables for data | Medium |
| **P4: Search Result Formatter** | Brave API embeds | Medium |
| **P5: Long-Running Feedback** | Intermediate ack messages | Medium |
| **P6: Full Classifier** | Automatic type detection | Medium |
| **P7: Proactive Message Formatting** | Briefings, alerts, reminders | Small |
| **P8: Migration — Strip CLAUDE.md & petersoul.md** | Remove formatting from other files, add references, run regression | Medium |
| **P9: 1000-Prompt Test Bank** | Build and validate full test suite | Large |
| **P10: Visual Preview Tool** | HTML preview for rapid iteration | Small |

---

## Appendix A: Discord Embed Colour Palette

| Content Type | Hex | Visual |
|-------------|-----|--------|
| Data / Tables | `0x5865F2` | Discord Blurple |
| Web Search | `0xFB542B` | Brave Orange |
| News | `0x1DA1F2` | Twitter Blue |
| Images | `0x7C3AED` | Purple |
| Local / Maps | `0x34A853` | Google Green |
| Proactive | `0xF59E0B` | Amber |
| Error | `0xEF4444` | Red |
| Schedule | `0x3B82F6` | Blue |

## Appendix B: OpenClaw Reference Architecture

Key lessons learned from OpenClaw (68k+ stars, mature Discord integration):

1. **Separate concerns** — SOUL.md (personality) vs AGENTS.md (operational rules) vs response rendering (code-level). Peter mirrors this with petersoul.md / CLAUDE.md / RESPONSE.md.

2. **EmbeddedBlockChunker** — OpenClaw's chunker uses paragraph → newline → sentence → whitespace → hard break priority for splitting. We adopt the same priority.

3. **`textChunkLimit` per channel** — Discord gets 2000, Telegram gets 4096. Future-proofing if Peter ever multi-channels.

4. **`maxLinesPerMessage`** — OpenClaw defaults to 17 for Discord. We use 20 but the principle is the same: prevent visual overwhelm.

5. **Code fence preservation** — OpenClaw specifically handles never splitting inside code fences, closing and re-opening across chunks. Critical for CC's code-heavy responses.

6. **`table-image` skill** — OpenClaw has a skill that renders tables as images for messaging apps. We could add this as a future enhancement for complex data.

7. **MEDIA: tag parsing** — OpenClaw uses `MEDIA:` line-start tags for explicit content type hints from the model. We could adopt similar structured hints in CC's prompt.

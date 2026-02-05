# Self-Improving Parser System

**Specification for Peterbot Response Parser Evolution**

Version 1.2 · February 2026

---

## Overview

The Peterbot response parser (`parser.py` + `response/pipeline.py`) extracts clean text from raw tmux screen captures of Claude Code output. This is an inherently fragile process — Claude Code's output format evolves with updates, new tool types introduce new patterns, and edge cases surface unpredictably. Rather than hand-tuning the parser reactively, this system treats parsing as a continuously-tested, self-improving pipeline.

### Architecture Summary

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                         Self-Improving Parser System                          │
├──────────┬──────────────┬───────────────┬───────────────┬────────────────────┤
│ Fixture  │   Capture    │  Regression   │  Improvement  │  Scheduled Output  │
│ Cache    │   System     │  Runner       │  Agent        │  Monitor           │
│ (300+)   │   (24h)      │  (Scoring)    │  (AI Loop)    │  (Format QA)       │
├──────────┴──────────────┴───────┬───────┴───────────────┴────────────────────┤
│          Feedback Loop          │        Morning Quality Report              │
│    (Discord → next cycle)      │       (Daily digest → #peterbot-dev)       │
└─────────────────────────────────┴────────────────────────────────────────────┘
```

**Seven components:**

1. **Fixture Cache** — 300+ curated input/output pairs covering every known response shape
2. **Capture System** — Intercepts every real message, storing raw + parsed pairs with quality signals
3. **Regression Runner** — Scores parser output against fixtures using a structured rubric
4. **Improvement Agent** — Reviews failures, proposes targeted parser changes, validates via regression
5. **Scheduled Output Monitor** — Tracks format consistency of recurring skill outputs (briefings, digests, reports) over time, flagging drift and recommending prompt or code fixes
6. **Feedback Loop** — Collects human feedback throughout the day via Discord reactions, commands, and natural language, feeding it into the next improvement cycle as prioritised input
7. **Morning Quality Report** — Consolidated daily report delivered before the morning briefing, summarising overnight improvement runs, capture quality, scheduled output health, feedback status, and action items

---

## Phase 1: Fixture Cache & Capture System

### 1.1 Fixture Cache Database

**Location:** `data/parser_fixtures.db` (SQLite)

**Schema:**

```sql
CREATE TABLE fixtures (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Input: exactly what the parser receives
    raw_capture     TEXT NOT NULL,           -- Raw tmux screen content (pre-parsing)
    screen_before   TEXT,                    -- Screen state before message (for diff-based extraction)

    -- Expected output: what the parser should produce
    expected_output TEXT NOT NULL,           -- Clean text that should be sent to Discord

    -- Classification
    category        TEXT NOT NULL,           -- Primary category (see taxonomy below)
    tags            TEXT DEFAULT '[]',       -- JSON array of secondary tags
    difficulty      TEXT DEFAULT 'normal',   -- easy | normal | hard | adversarial

    -- Provenance
    source          TEXT NOT NULL,           -- seed | capture | manual | failure
    source_date     TIMESTAMP,              -- When the original message occurred
    channel_id      TEXT,                    -- Discord channel (if from capture)
    notes           TEXT,                    -- Human notes on why this fixture matters

    -- Quality tracking
    last_pass       BOOLEAN,                -- Did the parser pass this fixture on last run?
    last_run_at     TIMESTAMP,
    fail_count      INTEGER DEFAULT 0,      -- How many times this fixture has failed
    regression_at   TIMESTAMP               -- When this fixture last regressed (was passing, now failing)
);

CREATE INDEX idx_fixtures_category ON fixtures(category);
CREATE INDEX idx_fixtures_source ON fixtures(source);
CREATE INDEX idx_fixtures_last_pass ON fixtures(last_pass);
CREATE INDEX idx_fixtures_difficulty ON fixtures(difficulty);
```

### 1.2 Fixture Taxonomy

Every fixture gets one primary `category` and zero or more `tags`. The initial 300 fixtures must cover **every category** with at minimum the counts shown.

**Categories (minimum fixtures per category):**

| Category | Min | Description |
|---|---|---|
| `short_text` | 30 | 1-3 sentence responses, no formatting |
| `long_text` | 20 | Multi-paragraph prose responses |
| `code_block` | 30 | Response contains fenced code blocks (single or multiple) |
| `code_inline` | 10 | Response contains inline `code` references |
| `multi_tool_use` | 25 | Response where CC used tools (bash, file edit, etc.) — tool output mixed in |
| `tool_use_only` | 15 | Response is purely tool output with brief summary |
| `error_response` | 15 | CC encountered an error, output includes error traces |
| `skill_output` | 25 | Structured skill responses (health digest, HB P&L, briefings, etc.) |
| `markdown_rich` | 20 | Heavy markdown: tables, headers, bold, lists, blockquotes |
| `emoji_formatting` | 10 | Responses with Discord emoji formatting (✅, ❌, progress bars, etc.) |
| `image_reference` | 10 | Response references or describes images |
| `empty_response` | 10 | CC returned nothing useful (spinner-only, blank, timeout) |
| `truncated` | 10 | Response that exceeds Discord limits, needs splitting |
| `instruction_echo` | 20 | Raw capture contains echoed instruction text that must be stripped |
| `ansi_heavy` | 15 | Capture has heavy ANSI escape sequences (colors, cursor moves) |
| `spinner_frames` | 10 | Capture includes spinner/progress indicator frames |
| `mixed_format` | 15 | Combination of code, prose, lists, and formatting |
| `edge_case` | 10 | Unusual or adversarial patterns (nested code fences, unicode, etc.) |

**Tags (applied in addition to category):**

- `has_code`, `has_table`, `has_list`, `has_header`, `has_emoji`
- `has_ansi`, `has_spinner`, `has_echo`
- `multi_message` (response needs splitting across Discord messages)
- `contains_url`, `contains_path`
- `scheduled_job` (response from a scheduled skill execution)
- `interactive` (response to a user message)

### 1.3 Building the Initial 300 Fixtures

**Strategy: three sources combined.**

**Source 1 — Seed from production captures (target: 150 fixtures)**

Run a one-off extraction against the existing capture_store SQLite database and Discord message history:

```python
# Pseudo-approach
# 1. Query capture_store for last 7 days of raw captures
# 2. For each capture, also fetch the corresponding Discord message that was sent
# 3. The raw capture = input, the Discord message = expected output (human-verified baseline)
# 4. Auto-classify by category using heuristics:
#    - Contains ``` → code_block
#    - Contains ANSI escapes → ansi_heavy
#    - Response < 100 chars → short_text
#    - Contains tool markers → multi_tool_use
#    - etc.
# 5. Human review pass: correct misclassifications, verify expected_output is actually correct
```

**Source 2 — Synthetic adversarial (target: 80 fixtures)**

Manually craft or generate fixtures that stress specific parser stages:

- Nested triple-backtick code blocks (code block inside a code block)
- ANSI sequences mid-word (color codes splitting a word)
- Spinner frame captured mid-rotation
- Instruction echo that partially overlaps with the response
- Unicode edge cases (emoji, CJK, RTL text)
- Response that is exactly 2000 chars (Discord limit boundary)
- Response that is 2001 chars (must split)
- Empty screen diff (identical before/after)
- Multiple tool uses with interleaved commentary

**Source 3 — Curated from known failures (target: 70 fixtures)**

Review Discord channels for messages where:
- Peter sent an empty response when one was expected
- ANSI artifacts appeared in the Discord message
- Instruction text leaked into the response
- Formatting was broken (unclosed code blocks, mangled tables)
- Response was truncated incorrectly

Each of these becomes a fixture with `source: 'failure'` and the corrected expected_output.

### 1.4 Capture System

**Purpose:** Intercept every message flowing through the parser and store the raw input + final output pair for later analysis. This feeds the improvement loop and grows the fixture cache automatically.

**Integration points in existing code:**

```
router.py                          parser.py                    pipeline.py
    │                                  │                            │
    ├─ [CAPTURE POINT A]               │                            │
    │  Raw tmux screen content         │                            │
    │  + screen_before state           │                            │
    │                                  │                            │
    │──────────────────────────────────►│                            │
    │                                  ├─ [CAPTURE POINT B]         │
    │                                  │  Parser output             │
    │                                  │  (post-diff, post-strip)   │
    │                                  │                            │
    │                                  │───────────────────────────►│
    │                                  │                            ├─ [CAPTURE POINT C]
    │                                  │                            │  Pipeline output
    │                                  │                            │  (final Discord text)
    │                                  │                            │
    ▼                                  ▼                            ▼
```

**Database (extend `parser_fixtures.db`):**

```sql
CREATE TABLE captures (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    captured_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Context
    channel_id      TEXT NOT NULL,
    channel_name    TEXT,
    is_scheduled    BOOLEAN DEFAULT FALSE,  -- Was this a scheduled job?
    skill_name      TEXT,                   -- If scheduled, which skill?

    -- Raw data at each stage
    screen_before   TEXT,                   -- tmux screen state before message
    screen_after    TEXT NOT NULL,          -- tmux screen state after response
    parser_output   TEXT,                   -- Output of parser.py (intermediate)
    pipeline_output TEXT,                   -- Final output of pipeline (sent to Discord)

    -- Quality signals
    was_empty       BOOLEAN DEFAULT FALSE,  -- Pipeline output was empty/None
    had_ansi        BOOLEAN DEFAULT FALSE,  -- ANSI sequences detected in pipeline output
    had_echo        BOOLEAN DEFAULT FALSE,  -- Instruction text detected in pipeline output
    was_truncated   BOOLEAN DEFAULT FALSE,  -- Response was split across messages
    discord_msg_id  TEXT,                   -- Discord message ID (for reaction tracking)
    user_reacted    TEXT,                   -- Reaction emoji if user reacted (👎, ❌, etc.)

    -- Processing
    reviewed        BOOLEAN DEFAULT FALSE,  -- Has the improvement agent reviewed this?
    promoted        BOOLEAN DEFAULT FALSE,  -- Has this been promoted to a fixture?
    fixture_id      TEXT,                   -- If promoted, link to fixture
    quality_score   REAL                    -- Score from regression rubric (0.0 - 1.0)
);

CREATE INDEX idx_captures_date ON captures(captured_at);
CREATE INDEX idx_captures_quality ON captures(quality_score);
CREATE INDEX idx_captures_reviewed ON captures(reviewed);
CREATE INDEX idx_captures_empty ON captures(was_empty);
```

**Capture implementation:**

```python
# domains/peterbot/capture_parser.py

import sqlite3
import re
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path("data/parser_fixtures.db")

ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

class ParserCaptureStore:
    """Captures raw/parsed message pairs for parser improvement."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- Tables created from schema above
                -- (elided for brevity, use full schema)
            """)

    def capture(
        self,
        channel_id: str,
        channel_name: str,
        screen_before: str | None,
        screen_after: str,
        parser_output: str | None,
        pipeline_output: str | None,
        is_scheduled: bool = False,
        skill_name: str | None = None,
        discord_msg_id: str | None = None,
    ) -> str:
        """Store a capture. Returns capture ID."""

        was_empty = not pipeline_output or not pipeline_output.strip()
        had_ansi = bool(ANSI_PATTERN.search(pipeline_output or ""))
        had_echo = self._detect_echo(screen_before, pipeline_output)
        was_truncated = len(pipeline_output or "") > 1900

        with sqlite3.connect(self.db_path) as conn:
            capture_id = self._generate_id()
            conn.execute("""
                INSERT INTO captures
                (id, channel_id, channel_name, screen_before, screen_after,
                 parser_output, pipeline_output, is_scheduled, skill_name,
                 discord_msg_id, was_empty, had_ansi, had_echo, was_truncated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (capture_id, channel_id, channel_name, screen_before,
                  screen_after, parser_output, pipeline_output, is_scheduled,
                  skill_name, discord_msg_id, was_empty, had_ansi, had_echo,
                  was_truncated))

        return capture_id

    def get_recent_failures(self, hours: int = 24) -> list[dict]:
        """Get captures with quality issues from the last N hours."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM captures
                WHERE captured_at > ?
                AND (was_empty = 1 OR had_ansi = 1 OR had_echo = 1
                     OR quality_score < 0.8 OR user_reacted IS NOT NULL)
                AND reviewed = 0
                ORDER BY captured_at DESC
            """, (cutoff.isoformat(),)).fetchall()
        return [dict(r) for r in rows]

    def promote_to_fixture(self, capture_id: str, expected_output: str,
                           category: str, tags: list[str] | None = None) -> str:
        """Promote a capture to a permanent fixture."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cap = conn.execute(
                "SELECT * FROM captures WHERE id = ?", (capture_id,)
            ).fetchone()
            if not cap:
                raise ValueError(f"Capture {capture_id} not found")

            fixture_id = self._generate_id()
            conn.execute("""
                INSERT INTO fixtures
                (id, raw_capture, screen_before, expected_output, category,
                 tags, source, source_date, channel_id)
                VALUES (?, ?, ?, ?, ?, ?, 'capture', ?, ?)
            """, (fixture_id, cap['screen_after'], cap['screen_before'],
                  expected_output, category, json.dumps(tags or []),
                  cap['captured_at'], cap['channel_id']))

            conn.execute("""
                UPDATE captures SET promoted = 1, fixture_id = ?
                WHERE id = ?
            """, (fixture_id, capture_id))

        return fixture_id

    def cleanup_old_captures(self, keep_days: int = 7):
        """Remove old captures that haven't been promoted. Keep failures longer."""
        cutoff_normal = datetime.utcnow() - timedelta(days=keep_days)
        cutoff_failures = datetime.utcnow() - timedelta(days=keep_days * 4)
        with sqlite3.connect(self.db_path) as conn:
            # Normal captures: keep 7 days
            conn.execute("""
                DELETE FROM captures
                WHERE captured_at < ?
                AND promoted = 0
                AND was_empty = 0 AND had_ansi = 0 AND had_echo = 0
                AND user_reacted IS NULL
            """, (cutoff_normal.isoformat(),))
            # Failure captures: keep 28 days
            conn.execute("""
                DELETE FROM captures
                WHERE captured_at < ?
                AND promoted = 0
            """, (cutoff_failures.isoformat(),))

    def _detect_echo(self, screen_before: str | None,
                     pipeline_output: str | None) -> bool:
        """Detect if instruction text leaked into output."""
        if not screen_before or not pipeline_output:
            return False
        # Extract the last user instruction from screen_before
        # and check if it appears in the pipeline output
        # (heuristic: last line(s) of screen_before that look like user input)
        lines = screen_before.strip().split('\n')
        if len(lines) < 2:
            return False
        last_input = lines[-1].strip()
        if len(last_input) > 20 and last_input in pipeline_output:
            return True
        return False
```

**Wiring into router.py:**

The capture calls are non-blocking and must never interfere with message delivery. Wrap in `asyncio.create_task` with error suppression.

```python
# In router.py, after response is sent to Discord:

async def _capture_for_parser(self, channel_id, channel_name, screen_before,
                               screen_after, parser_output, pipeline_output,
                               discord_msg_id, is_scheduled, skill_name):
    """Non-blocking capture for parser improvement system."""
    try:
        self.parser_capture_store.capture(
            channel_id=str(channel_id),
            channel_name=channel_name,
            screen_before=screen_before,
            screen_after=screen_after,
            parser_output=parser_output,
            pipeline_output=pipeline_output,
            is_scheduled=is_scheduled,
            skill_name=skill_name,
            discord_msg_id=str(discord_msg_id) if discord_msg_id else None,
        )
    except Exception as e:
        logger.warning(f"Parser capture failed (non-fatal): {e}")
```

### 1.5 Reaction Tracking

Add a listener in `bot.py` to catch user reactions on Peter's messages and update the capture record:

```python
@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    # If reaction is on one of Peter's messages, update capture
    if reaction.message.author == bot.user:
        emoji = str(reaction.emoji)
        if emoji in ('👎', '❌', '🔧', '⚠️'):
            # Signal that this response had a problem
            parser_capture_store.flag_reaction(
                discord_msg_id=str(reaction.message.id),
                reaction=emoji
            )
```

---

## Phase 2: Regression Runner

### 2.1 Scoring Rubric

Each fixture is scored on six dimensions. Each dimension produces a score from 0.0 to 1.0. The overall fixture score is the weighted average.

| Dimension | Weight | What it measures |
|---|---|---|
| **Content Preservation** | 0.30 | Does the parsed output contain the meaningful content from the raw capture? No content loss. |
| **ANSI Cleanliness** | 0.20 | Zero ANSI escape sequences in the output. Binary: 1.0 if clean, 0.0 if any ANSI present. |
| **Echo Removal** | 0.15 | Instruction/prompt text from the user is not present in the output. |
| **Format Integrity** | 0.15 | Markdown formatting survives: code blocks are closed, tables are intact, lists are preserved. |
| **Length Compliance** | 0.10 | Output respects Discord limits. Single messages ≤ 2000 chars, or properly split. |
| **Noise Removal** | 0.10 | Spinner frames, tool invocation noise, thinking indicators are stripped. |

**Pass threshold:** A fixture passes if its overall score ≥ 0.90.

**Regression detection:** A fixture has regressed if it previously passed (score ≥ 0.90) and now scores < 0.90.

### 2.2 Scorer Implementation

```python
# domains/peterbot/parser_scorer.py

import re
from dataclasses import dataclass

ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
SPINNER_PATTERNS = [
    re.compile(r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]'),     # Braille spinners
    re.compile(r'[\|/\-\\](?:\s|$)'),          # Classic spinners at line boundaries
    re.compile(r'\.{3,}'),                      # Loading dots (3+)
]

@dataclass
class ScoreResult:
    content_preservation: float
    ansi_cleanliness: float
    echo_removal: float
    format_integrity: float
    length_compliance: float
    noise_removal: float

    @property
    def overall(self) -> float:
        weights = {
            'content_preservation': 0.30,
            'ansi_cleanliness': 0.20,
            'echo_removal': 0.15,
            'format_integrity': 0.15,
            'length_compliance': 0.10,
            'noise_removal': 0.10,
        }
        return sum(
            getattr(self, dim) * w
            for dim, w in weights.items()
        )

    @property
    def passed(self) -> bool:
        return self.overall >= 0.90

    @property
    def failures(self) -> list[str]:
        """Which dimensions scored below 0.8?"""
        dims = ['content_preservation', 'ansi_cleanliness', 'echo_removal',
                'format_integrity', 'length_compliance', 'noise_removal']
        return [d for d in dims if getattr(self, d) < 0.8]


class ParserScorer:
    """Scores parser output against expected output using the rubric."""

    def score(self, raw_capture: str, expected_output: str,
              actual_output: str, screen_before: str | None = None) -> ScoreResult:
        return ScoreResult(
            content_preservation=self._score_content(expected_output, actual_output),
            ansi_cleanliness=self._score_ansi(actual_output),
            echo_removal=self._score_echo(screen_before, actual_output),
            format_integrity=self._score_format(expected_output, actual_output),
            length_compliance=self._score_length(actual_output),
            noise_removal=self._score_noise(actual_output),
        )

    def _score_content(self, expected: str, actual: str) -> float:
        """Measure content preservation using normalised token overlap."""
        if not expected.strip():
            # Empty expected output — actual should also be empty
            return 1.0 if not actual.strip() else 0.5

        expected_tokens = set(self._tokenise(expected))
        actual_tokens = set(self._tokenise(actual))

        if not expected_tokens:
            return 1.0

        # Recall: what fraction of expected tokens appear in actual?
        recall = len(expected_tokens & actual_tokens) / len(expected_tokens)
        # Penalise heavily for low recall (content loss)
        # Penalise lightly for extra tokens (some noise acceptable)
        precision = (len(expected_tokens & actual_tokens) / len(actual_tokens)
                     if actual_tokens else 0.0)

        # F1-weighted toward recall (content loss is worse than noise)
        if recall + precision == 0:
            return 0.0
        beta = 2.0  # Recall-weighted F-score
        return ((1 + beta**2) * precision * recall) / (beta**2 * precision + recall)

    def _score_ansi(self, actual: str) -> float:
        """Binary: 1.0 if no ANSI, 0.0 if any present."""
        return 0.0 if ANSI_PATTERN.search(actual or "") else 1.0

    def _score_echo(self, screen_before: str | None, actual: str) -> float:
        """Check if user instruction leaked into output."""
        if not screen_before or not actual:
            return 1.0
        # Extract likely user input lines
        lines = screen_before.strip().split('\n')
        user_lines = [l.strip() for l in lines[-3:] if len(l.strip()) > 15]
        for line in user_lines:
            if line in actual:
                return 0.0
        return 1.0

    def _score_format(self, expected: str, actual: str) -> float:
        """Check markdown formatting survived parsing."""
        score = 1.0
        penalties = []

        # Code block balance
        expected_fences = expected.count('```')
        actual_fences = actual.count('```')
        if expected_fences > 0 and actual_fences != expected_fences:
            penalties.append(0.3)
        # Unclosed code blocks (odd number of fences)
        if actual_fences % 2 != 0:
            penalties.append(0.4)

        # Table pipe alignment (rough check)
        expected_tables = expected.count('|')
        actual_tables = actual.count('|')
        if expected_tables > 4 and actual_tables < expected_tables * 0.5:
            penalties.append(0.3)

        # Bold/italic markers
        expected_bold = expected.count('**')
        actual_bold = actual.count('**')
        if expected_bold > 0 and actual_bold < expected_bold * 0.5:
            penalties.append(0.2)

        return max(0.0, score - sum(penalties))

    def _score_length(self, actual: str) -> float:
        """Check Discord message limit compliance."""
        if not actual:
            return 1.0
        if len(actual) <= 2000:
            return 1.0
        # Over limit — should have been split
        overage = len(actual) - 2000
        # Gradual penalty
        return max(0.0, 1.0 - (overage / 2000))

    def _score_noise(self, actual: str) -> float:
        """Check for spinner frames, tool noise, thinking indicators."""
        if not actual:
            return 1.0
        noise_count = 0
        for pattern in SPINNER_PATTERNS:
            noise_count += len(pattern.findall(actual))
        # Thinking block indicators
        if '<antThinking>' in actual or '</antThinking>' in actual:
            noise_count += 5
        # Tool invocation noise
        if 'tool_use' in actual and 'content_block' in actual:
            noise_count += 3

        if noise_count == 0:
            return 1.0
        return max(0.0, 1.0 - (noise_count * 0.1))

    def _tokenise(self, text: str) -> list[str]:
        """Simple whitespace tokenisation with normalisation."""
        text = ANSI_PATTERN.sub('', text or '')
        text = text.lower().strip()
        return [t for t in text.split() if len(t) > 2]
```

### 2.3 Regression Runner

```python
# domains/peterbot/parser_regression.py

import sqlite3
import json
from datetime import datetime
from dataclasses import dataclass, field
from parser_scorer import ParserScorer, ScoreResult

@dataclass
class RegressionReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    regressions: int = 0          # Previously passing, now failing
    improvements: int = 0          # Previously failing, now passing
    by_category: dict = field(default_factory=dict)
    failures: list = field(default_factory=list)
    overall_score: float = 0.0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def summary(self) -> str:
        lines = [
            f"=== Parser Regression Report ===",
            f"Run at: {datetime.utcnow().isoformat()}Z",
            f"",
            f"Total fixtures:  {self.total}",
            f"Passed:          {self.passed} ({self.pass_rate:.1%})",
            f"Failed:          {self.failed}",
            f"Regressions:     {self.regressions} ⚠️" if self.regressions else f"Regressions:     0 ✅",
            f"Improvements:    {self.improvements} 🎉" if self.improvements else f"Improvements:    0",
            f"Overall score:   {self.overall_score:.3f}",
            f"",
            f"--- By Category ---",
        ]
        for cat, stats in sorted(self.by_category.items()):
            rate = stats['passed'] / stats['total'] if stats['total'] else 0
            marker = "✅" if rate >= 0.9 else "⚠️" if rate >= 0.7 else "❌"
            lines.append(f"  {marker} {cat}: {stats['passed']}/{stats['total']} ({rate:.0%})")

        if self.failures:
            lines.append(f"")
            lines.append(f"--- Failed Fixtures (top 10) ---")
            for f in self.failures[:10]:
                lines.append(f"  [{f['category']}] {f['id']}: {f['score']:.3f} — {', '.join(f['failed_dims'])}")

        return '\n'.join(lines)


class RegressionRunner:
    """Run all fixtures through the current parser and score them."""

    def __init__(self, db_path: str, parser_fn, scorer: ParserScorer = None):
        """
        Args:
            db_path: Path to parser_fixtures.db
            parser_fn: Callable(raw_capture, screen_before) -> parsed_output
                       This wraps the current parser.py + pipeline.py logic
            scorer: ParserScorer instance
        """
        self.db_path = db_path
        self.parser_fn = parser_fn
        self.scorer = scorer or ParserScorer()

    def run(self) -> RegressionReport:
        """Execute full regression suite."""
        report = RegressionReport()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            fixtures = conn.execute("SELECT * FROM fixtures ORDER BY category").fetchall()

        for fixture in fixtures:
            report.total += 1
            fx = dict(fixture)

            # Run parser
            try:
                actual_output = self.parser_fn(
                    raw_capture=fx['raw_capture'],
                    screen_before=fx['screen_before']
                )
            except Exception as e:
                actual_output = f"[PARSER ERROR: {e}]"

            # Score
            result = self.scorer.score(
                raw_capture=fx['raw_capture'],
                expected_output=fx['expected_output'],
                actual_output=actual_output,
                screen_before=fx['screen_before']
            )

            passed = result.passed
            was_passing = fx['last_pass']

            # Track category stats
            cat = fx['category']
            if cat not in report.by_category:
                report.by_category[cat] = {'total': 0, 'passed': 0, 'failed': 0}
            report.by_category[cat]['total'] += 1

            if passed:
                report.passed += 1
                report.by_category[cat]['passed'] += 1
                if was_passing is False:
                    report.improvements += 1
            else:
                report.failed += 1
                report.by_category[cat]['failed'] += 1
                report.failures.append({
                    'id': fx['id'],
                    'category': cat,
                    'score': result.overall,
                    'failed_dims': result.failures,
                    'actual_output_preview': (actual_output or '')[:200],
                })
                if was_passing is True:
                    report.regressions += 1

            # Update fixture record
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE fixtures SET
                        last_pass = ?,
                        last_run_at = ?,
                        fail_count = fail_count + ?,
                        regression_at = CASE WHEN ? = 1 AND last_pass = 1
                                        THEN ? ELSE regression_at END
                    WHERE id = ?
                """, (
                    passed,
                    datetime.utcnow().isoformat(),
                    0 if passed else 1,
                    0 if passed else 1,
                    datetime.utcnow().isoformat(),
                    fx['id']
                ))

        report.overall_score = report.passed / report.total if report.total else 0.0
        return report
```

### 2.4 CLI Interface

The regression runner should be callable from Claude Code and from scheduled jobs:

```bash
# Run full regression
python -m peterbot.parser_regression run

# Run only fixtures in a category
python -m peterbot.parser_regression run --category code_block

# Run only previously-failing fixtures
python -m peterbot.parser_regression run --failing-only

# Show detailed failure analysis for a specific fixture
python -m peterbot.parser_regression inspect <fixture_id>

# Promote a capture to a fixture
python -m peterbot.parser_regression promote <capture_id> --category <cat> --expected "..."
```

---

## Phase 3: Self-Improving Agent Loop

### 3.1 Overview

The improvement agent runs as a scheduled job (suggested: daily at 02:00, after capture_cleanup). It follows a strict cycle:

```
┌──────────────┐
│  1. Review    │ ← Analyze 24h captures + fixture failures
│              │
└──────┬───────┘
       ▼
┌──────────────┐
│  2. Plan      │ ← Identify worst dimension, propose targeted change
│              │
└──────┬───────┘
       ▼
┌──────────────┐
│  3. Implement │ ← Modify ONE parser stage (guardrailed)
│              │
└──────┬───────┘
       ▼
┌──────────────┐
│  4. Validate  │ ← Run full regression suite
│              │
└──────┬───────┘
       ▼
┌──────────────┐     ┌──────────────┐
│  Regressions?├────►│  5a. Rollback │ ← Revert change, log failure reason
│              │ YES └──────────────┘
└──────┬───────┘
       │ NO
       ▼
┌──────────────┐
│  5b. Commit   │ ← Git commit with regression report
│              │
└──────┬───────┘
       ▼
┌──────────────┐
│  6. Report    │ ← Post summary to #peterbot-dev channel
└──────────────┘
```

### 3.2 Guardrails

These constraints prevent the improvement agent from making dangerous or unmaintainable changes:

1. **One stage per cycle.** The parser has distinct stages (ANSI stripping, diff extraction, echo removal, format detection, sanitisation, length management). Each improvement cycle may only modify code within ONE stage. The agent must declare which stage it is targeting before making changes.

2. **No architecture changes.** The agent may not rename files, change function signatures in public APIs, alter the pipeline stage order, or introduce new dependencies. It can only modify internal logic within existing functions.

3. **Zero regressions policy.** If ANY previously-passing fixture now fails, the change is rejected. No exceptions.

4. **Maximum diff size.** Changes are limited to 100 lines of diff. Larger changes indicate an architectural change and are rejected.

5. **Preserve existing tests.** If there are unit tests for parser functions, they must continue to pass.

6. **Logging required.** Every change must include a log line explaining what was modified and why.

7. **Human review for accumulated changes.** After every 5 successful improvement cycles, the system flags for human review before continuing. Post a summary to Discord with a diff of all changes since last review.

### 3.3 Review Phase

```python
# domains/peterbot/parser_improver.py

class ParserImprover:
    """Self-improving parser agent loop."""

    PARSER_STAGES = {
        'ansi_strip':       'parser.py::strip_ansi()',
        'diff_extract':     'parser.py::extract_response()',
        'echo_removal':     'parser.py::remove_echo()',
        'format_detect':    'response/pipeline.py::detect_format()',
        'sanitise':         'response/pipeline.py::sanitise()',
        'length_manage':    'response/pipeline.py::manage_length()',
    }

    def review(self) -> dict:
        """
        Analyze recent captures, fixture failures, and human feedback.

        Returns a review report:
        {
            "capture_summary": {
                "total_24h": 142,
                "failures": 8,
                "failure_rate": 0.056,
                "failure_breakdown": {
                    "was_empty": 2,
                    "had_ansi": 3,
                    "had_echo": 1,
                    "low_quality": 2,
                }
            },
            "fixture_summary": {
                "total": 312,
                "pass_rate": 0.936,
                "worst_category": "multi_tool_use",
                "worst_dimension": "echo_removal",
                "chronic_failures": [...],  # Fixtures that have failed 3+ times
            },
            "feedback_summary": {
                "pending": 4,
                "by_category": {
                    "parser_issue": 2,
                    "format_drift": 1,
                    "prompt_issue": 1,
                },
                "high_priority": [...],     # Feedback items marked urgent
                "parser_relevant": [...],   # Feedback that maps to parser stages
            },
            "recommended_target": {
                "stage": "echo_removal",
                "rationale": "3 captures in 24h had instruction echo leakage,
                              and echo_removal is the worst-scoring dimension
                              across fixtures (avg 0.72). Additionally, 1 human
                              feedback item flagged echo text in a response.",
                "affected_fixtures": ["abc123", "def456", ...],
                "related_feedback": ["fb_789"],
                "example_failure": { ... },
            }
        }
        """
        # Implementation: query captures, fixtures, AND feedback DB
        # Human feedback is weighted 3x vs automated signals when
        # determining recommended_target — if a human flagged it,
        # it's almost certainly a real problem worth prioritising.
        pass
```

### 3.4 Plan Phase

The plan phase takes the review output and produces a concrete, scoped change proposal:

```python
def plan(self, review: dict) -> dict:
    """
    Produce a change plan targeting one parser stage.

    Returns:
    {
        "target_stage": "echo_removal",
        "target_file": "parser.py",
        "target_function": "remove_echo",
        "problem_statement": "The current echo removal checks for exact line
                             matches but CC sometimes wraps/reformats the echo.
                             3 fixtures fail because partial echo text remains.",
        "proposed_approach": "Add fuzzy matching using token overlap. If >70%
                             of tokens from the last user input line appear in
                             a contiguous block of the response, strip that block.",
        "affected_fixtures": ["abc123", "def456", "ghi789"],
        "risk_assessment": "Low — change is isolated to remove_echo(). No
                           other functions call this directly.",
        "estimated_diff_lines": 25,
    }
    """
    pass
```

### 3.5 Implement Phase

The agent applies changes to the parser. Implementation uses the existing Claude Code tool (bash/file edit) with explicit constraints:

```
CONSTRAINTS FOR PARSER MODIFICATION:

You are modifying the Peterbot response parser. Follow these rules:

1. You may ONLY modify code within the function: {target_function}
   in the file: {target_file}

2. DO NOT change function signatures, imports, or class structure.

3. Your change must be ≤ 100 lines of diff.

4. Add a comment at the modification site:
   # PARSER-IMPROVE: {date} — {one-line description}

5. Add a logger.debug() call that logs when the new logic activates.

6. After making changes, run the regression suite:
   python -m peterbot.parser_regression run

7. Report the results. If ANY regressions exist, REVERT your change
   immediately with: git checkout -- {target_file}
```

### 3.6 Validate & Commit

```python
def validate_and_commit(self, plan: dict, regression_before: RegressionReport,
                         regression_after: RegressionReport) -> bool:
    """
    Validate the change and commit if safe.

    Commit criteria (ALL must be true):
    1. Zero regressions (no fixture went from pass → fail)
    2. At least one improvement (at least one fixture went from fail → pass)
       OR overall score improved by ≥ 0.005
    3. Diff is ≤ 100 lines
    4. No architecture changes detected

    Returns True if committed, False if rolled back.
    """
    # Check for regressions
    if regression_after.regressions > 0:
        self._rollback(plan['target_file'])
        self._log_rejection("regressions_detected", plan, regression_after)
        return False

    # Check for improvement
    improved = (
        regression_after.improvements > 0 or
        regression_after.overall_score > regression_before.overall_score + 0.005
    )
    if not improved:
        self._rollback(plan['target_file'])
        self._log_rejection("no_improvement", plan, regression_after)
        return False

    # Commit
    commit_msg = (
        f"parser-improve: {plan['target_stage']}\n\n"
        f"Problem: {plan['problem_statement'][:200]}\n"
        f"Approach: {plan['proposed_approach'][:200]}\n"
        f"Score: {regression_before.overall_score:.3f} → {regression_after.overall_score:.3f}\n"
        f"Fixtures improved: {regression_after.improvements}\n"
        f"Regressions: 0"
    )
    # git add + commit
    return True
```

### 3.7 Reporting

Post results to a Discord channel after each cycle:

```
📊 **Parser Improvement Report**
🕐 2026-02-05 02:15 UTC

**Review findings:**
• 142 captures in last 24h, 8 failures (5.6%)
• Worst dimension: echo_removal (avg 0.72)
• 3 captures had instruction echo leakage

**Change applied:**
• Stage: `echo_removal` in `parser.py`
• Added fuzzy token matching for wrapped instruction echoes
• Diff: +18 / -3 lines

**Regression results:**
• Score: 0.936 → 0.949 (+0.013) ✅
• Fixtures improved: 4
• Regressions: 0
• New pass rate: 94.9% (296/312)

**New fixtures added from captures:**
• 2 failures promoted to fixture cache (now 314 total)
```

---

## Phase 4: Scheduled Output Monitor

### 4.1 Problem Statement

Scheduled skills (morning briefing, school run report, health digest, news summary, etc.) produce formatted output that users rely on having a consistent structure. Format drift happens in two ways:

1. **Parser drift** — The parser changes how it handles the output (covered by Phases 1-3)
2. **Prompt/model drift** — Claude Code's interpretation of the skill prompt shifts over time, producing subtly different formatting even though the parser is working correctly. A briefing that used to have weather → traffic → calendar sections might start omitting the traffic section, or a health digest might stop using the expected emoji indicators.

Phase 4 catches the second type. It's not about whether the parser stripped ANSI correctly — it's about whether the *content and structure* of skill outputs remains consistent with the established format.

### 4.2 Format Specification Registry

Each monitored skill gets a format spec that defines what a "correct" output looks like. These specs are stored alongside the skill definitions.

**Location:** `data/parser_fixtures.db` (extends existing database)

```sql
CREATE TABLE scheduled_output_specs (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    skill_name      TEXT NOT NULL UNIQUE,    -- e.g. 'morning-briefing', 'school-run'
    display_name    TEXT NOT NULL,            -- e.g. 'Morning Briefing'
    schedule_ref    TEXT,                     -- Reference to SCHEDULE.md entry

    -- Format specification
    required_sections   TEXT NOT NULL,        -- JSON array of section names that must appear
    section_order       TEXT,                 -- JSON array of expected section order (null = any order)
    required_indicators TEXT DEFAULT '[]',    -- JSON array of emoji/markers that should appear (✅, ❌, 🌡️, etc.)
    min_length          INTEGER DEFAULT 100,  -- Minimum expected output length
    max_length          INTEGER DEFAULT 3000, -- Maximum expected output length
    expected_patterns   TEXT DEFAULT '[]',    -- JSON array of regex patterns that should match
    forbidden_patterns  TEXT DEFAULT '[]',    -- JSON array of regex patterns that should NOT match

    -- Reference examples
    golden_examples     TEXT DEFAULT '[]',    -- JSON array of 3-5 "ideal" outputs for comparison
    
    -- Thresholds
    format_score_threshold REAL DEFAULT 0.85, -- Below this = format drift alert
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE scheduled_output_history (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    skill_name      TEXT NOT NULL,
    captured_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    channel_id      TEXT,

    -- The actual output
    output_text     TEXT NOT NULL,

    -- Scoring
    format_score    REAL,                    -- Overall format compliance score
    section_scores  TEXT,                    -- JSON: per-section presence/quality
    drift_detected  BOOLEAN DEFAULT FALSE,
    drift_details   TEXT,                    -- JSON: what specifically drifted

    -- Review
    reviewed        BOOLEAN DEFAULT FALSE,
    action_taken    TEXT,                    -- 'none' | 'prompt_update' | 'code_fix' | 'spec_update'
    notes           TEXT,

    FOREIGN KEY (skill_name) REFERENCES scheduled_output_specs(skill_name)
);

CREATE INDEX idx_soh_skill ON scheduled_output_history(skill_name);
CREATE INDEX idx_soh_date ON scheduled_output_history(captured_at);
CREATE INDEX idx_soh_drift ON scheduled_output_history(drift_detected);
```

### 4.3 Initial Format Specs

Define specs for every recurring scheduled skill. These are seeded from the current "good" outputs:

| Skill | Required Sections | Key Indicators | Patterns |
|---|---|---|---|
| `morning-briefing` | weather, traffic, calendar, ev_status, ring_status | 🌡️, 🚗, 📅, 🔋, 🔔 | Temperature regex, event count |
| `school-run` | route, traffic, departure_time, weather | 🚗, ⏰, 🌧️/☀️ | ETA pattern, "leave by" phrase |
| `health-digest` | steps, sleep, weight, hydration, heart_rate | Steps count, sleep hours | Number + unit patterns |
| `news-digest` | headlines, summaries | Numbered items | At least 3 items |
| `email-summary` | unread_count, priority_emails, action_items | 📧, ⚡, 📌 | Count patterns |
| `weekly-health` | week_summary, trends, goals_progress | 📊, 📈/📉 | Percentage patterns, comparison language |
| `monthly-health` | month_summary, trends, achievements, recommendations | 📊, 🏆 | Date range, comparison to previous month |
| `hb-daily-sales` | sales_count, revenue, top_items | 💰, 📦 | Currency patterns, item counts |
| `balance-monitor` | account_balances, changes | 💰, 📊 | Currency values |

### 4.4 Format Scorer

```python
# domains/peterbot/scheduled_output_scorer.py

import re
import json
from dataclasses import dataclass
from difflib import SequenceMatcher

@dataclass
class FormatScoreResult:
    overall: float
    section_presence: float       # Are all required sections present?
    section_order: float          # Are sections in the expected order?
    indicator_presence: float     # Are expected emoji/markers present?
    length_compliance: float      # Within min/max length bounds?
    pattern_compliance: float     # Do expected patterns match?
    structural_similarity: float  # How similar to golden examples?
    drift_details: list[str]      # Human-readable list of what drifted

    @property
    def drifted(self) -> bool:
        return self.overall < 0.85  # Default threshold


class ScheduledOutputScorer:
    """Scores scheduled skill outputs against format specifications."""

    def score(self, output: str, spec: dict) -> FormatScoreResult:
        details = []

        # 1. Section presence
        required = json.loads(spec['required_sections'])
        sections_found = self._detect_sections(output, required)
        section_presence = len(sections_found) / len(required) if required else 1.0
        missing = [s for s in required if s not in sections_found]
        if missing:
            details.append(f"Missing sections: {', '.join(missing)}")

        # 2. Section order
        if spec.get('section_order'):
            expected_order = json.loads(spec['section_order'])
            found_order = [s for s in expected_order if s in sections_found]
            section_order = self._order_score(expected_order, found_order)
            if section_order < 1.0:
                details.append(f"Section order drift (expected: {' → '.join(expected_order[:4])}...)")
        else:
            section_order = 1.0

        # 3. Indicator presence
        indicators = json.loads(spec.get('required_indicators', '[]'))
        if indicators:
            found_indicators = [i for i in indicators if i in output]
            indicator_presence = len(found_indicators) / len(indicators)
            missing_ind = [i for i in indicators if i not in output]
            if missing_ind:
                details.append(f"Missing indicators: {' '.join(missing_ind)}")
        else:
            indicator_presence = 1.0

        # 4. Length compliance
        min_len = spec.get('min_length', 100)
        max_len = spec.get('max_length', 3000)
        output_len = len(output)
        if min_len <= output_len <= max_len:
            length_compliance = 1.0
        elif output_len < min_len:
            length_compliance = max(0.0, output_len / min_len)
            details.append(f"Output too short ({output_len} chars, min {min_len})")
        else:
            length_compliance = max(0.0, 1.0 - (output_len - max_len) / max_len)
            details.append(f"Output too long ({output_len} chars, max {max_len})")

        # 5. Pattern compliance
        expected_patterns = json.loads(spec.get('expected_patterns', '[]'))
        forbidden_patterns = json.loads(spec.get('forbidden_patterns', '[]'))
        pattern_hits = 0
        pattern_total = len(expected_patterns) + len(forbidden_patterns)
        for pat in expected_patterns:
            if re.search(pat, output):
                pattern_hits += 1
            else:
                details.append(f"Expected pattern not found: {pat[:50]}")
        for pat in forbidden_patterns:
            if not re.search(pat, output):
                pattern_hits += 1
            else:
                details.append(f"Forbidden pattern found: {pat[:50]}")
        pattern_compliance = pattern_hits / pattern_total if pattern_total else 1.0

        # 6. Structural similarity to golden examples
        golden = json.loads(spec.get('golden_examples', '[]'))
        if golden:
            similarities = [
                self._structural_similarity(output, example)
                for example in golden
            ]
            structural_similarity = max(similarities)  # Best match
            if structural_similarity < 0.6:
                details.append(f"Low structural similarity to golden examples ({structural_similarity:.2f})")
        else:
            structural_similarity = 1.0  # No golden examples = skip

        # Weighted overall
        overall = (
            section_presence * 0.25 +
            section_order * 0.10 +
            indicator_presence * 0.15 +
            length_compliance * 0.10 +
            pattern_compliance * 0.15 +
            structural_similarity * 0.25
        )

        return FormatScoreResult(
            overall=overall,
            section_presence=section_presence,
            section_order=section_order,
            indicator_presence=indicator_presence,
            length_compliance=length_compliance,
            pattern_compliance=pattern_compliance,
            structural_similarity=structural_similarity,
            drift_details=details,
        )

    def _detect_sections(self, output: str, required: list[str]) -> list[str]:
        """
        Detect which required sections are present in the output.
        Uses multiple strategies: header matching, keyword clusters, emoji markers.
        """
        found = []
        output_lower = output.lower()

        # Section detection heuristics per section name
        SECTION_SIGNALS = {
            'weather':       ['🌡️', '°c', '°f', 'temperature', 'rain', 'sunny', 'cloudy', 'weather'],
            'traffic':       ['🚗', 'traffic', 'minutes', 'route', 'congestion', 'a21', 'a26', 'm25'],
            'calendar':      ['📅', 'calendar', 'meeting', 'event', 'appointment', 'schedule'],
            'ev_status':     ['🔋', 'battery', 'charge', 'kia', 'ev', 'range', 'miles'],
            'ring_status':   ['🔔', 'ring', 'doorbell', 'motion', 'last seen'],
            'route':         ['route', 'via', 'direction', 'distance'],
            'departure_time':['⏰', 'leave by', 'depart', 'departure'],
            'steps':         ['steps', 'walked', 'step count'],
            'sleep':         ['sleep', 'slept', 'hours sleep', 'rem', 'deep sleep'],
            'weight':        ['weight', 'kg', 'lbs', 'body comp'],
            'hydration':     ['💧', 'water', 'hydration', 'ml', 'glasses'],
            'heart_rate':    ['❤️', 'heart rate', 'bpm', 'resting hr'],
            'headlines':     ['headline', 'news', 'top stories'],
            'summaries':     ['summary', 'key points', 'highlights'],
            'unread_count':  ['unread', 'new emails', 'inbox'],
            'priority_emails':['priority', 'important', 'urgent', 'flagged'],
            'action_items':  ['action', 'todo', 'follow up', 'respond'],
            'sales_count':   ['sales', 'orders', 'sold'],
            'revenue':       ['revenue', '£', 'total', 'earnings'],
            'top_items':     ['top items', 'best sellers', 'popular'],
            'account_balances':['balance', 'account', '£'],
            'changes':       ['change', 'movement', 'difference', 'vs'],
            'week_summary':  ['this week', 'weekly', 'past 7'],
            'month_summary': ['this month', 'monthly', 'past 30'],
            'trends':        ['📈', '📉', 'trend', 'trending', 'compared to'],
            'goals_progress':['goal', 'target', 'progress', '%'],
            'achievements':  ['🏆', 'achievement', 'personal best', 'pb', 'milestone'],
            'recommendations':['recommend', 'suggestion', 'consider', 'try'],
        }

        for section in required:
            signals = SECTION_SIGNALS.get(section, [section])
            matches = sum(1 for s in signals if s in output_lower)
            if matches >= 2 or (matches >= 1 and len(signals) <= 2):
                found.append(section)

        return found

    def _order_score(self, expected: list, actual: list) -> float:
        """Score how well the actual order matches expected order."""
        if not expected or not actual:
            return 1.0
        # Longest common subsequence ratio
        matcher = SequenceMatcher(None, expected, actual)
        return matcher.ratio()

    def _structural_similarity(self, output: str, golden: str) -> float:
        """
        Compare structural similarity (not content).
        Normalise both to a structural skeleton, then compare.
        """
        def skeletonise(text: str) -> str:
            """Reduce text to structural markers."""
            lines = text.strip().split('\n')
            skeleton_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    skeleton_lines.append('[BLANK]')
                elif stripped.startswith('#'):
                    skeleton_lines.append('[HEADER]')
                elif stripped.startswith(('- ', '• ', '* ')):
                    skeleton_lines.append('[BULLET]')
                elif stripped.startswith(('1.', '2.', '3.', '4.', '5.')):
                    skeleton_lines.append('[NUMBERED]')
                elif re.match(r'^[│├└┌┐┘┤┬┴┼─]+', stripped):
                    skeleton_lines.append('[TABLE_BORDER]')
                elif '|' in stripped and stripped.count('|') >= 2:
                    skeleton_lines.append('[TABLE_ROW]')
                elif any(e in stripped for e in ['✅', '❌', '⚠️', '🔋', '🌡️', '📅', '🚗']):
                    skeleton_lines.append('[INDICATOR_LINE]')
                elif stripped.startswith('```'):
                    skeleton_lines.append('[CODE_FENCE]')
                elif len(stripped) < 40 and stripped.endswith(':'):
                    skeleton_lines.append('[LABEL]')
                else:
                    skeleton_lines.append('[TEXT]')
            return '\n'.join(skeleton_lines)

        skel_output = skeletonise(output)
        skel_golden = skeletonise(golden)
        return SequenceMatcher(None, skel_output, skel_golden).ratio()
```

### 4.5 Capture Integration

The existing capture system (Phase 1) already records `is_scheduled` and `skill_name`. The scheduled output monitor hooks into the same data:

```python
# In router.py, after sending a scheduled skill response:

async def _capture_scheduled_output(self, skill_name: str, output: str, channel_id: str):
    """Score scheduled output against format spec and store history."""
    try:
        spec = self.scheduled_scorer.get_spec(skill_name)
        if not spec:
            return  # No spec defined for this skill, skip

        result = self.scheduled_scorer.score(output, spec)

        self.scheduled_scorer.store_history(
            skill_name=skill_name,
            channel_id=channel_id,
            output_text=output,
            format_score=result.overall,
            section_scores=result,
            drift_detected=result.drifted,
            drift_details=result.drift_details,
        )

        if result.drifted:
            logger.warning(
                f"Format drift detected in {skill_name}: "
                f"score={result.overall:.2f}, issues={result.drift_details}"
            )
    except Exception as e:
        logger.warning(f"Scheduled output scoring failed (non-fatal): {e}")
```

### 4.6 Drift Response Actions

When format drift is detected, the system determines the appropriate response:

| Drift Type | Likely Cause | Recommended Action |
|---|---|---|
| Missing sections | Model skipped a section, or data source was unavailable | Check if data source returned empty → if so, code fix to handle gracefully. If data was available, prompt update to reinforce section requirement. |
| Section order changed | Model reorganised the output | Prompt update to explicitly specify order. |
| Missing indicators (emoji) | Model stopped using expected formatting | Prompt update to include explicit emoji requirements. |
| Output too short | Model summarised too aggressively, or data source partial failure | Check data sources first, then prompt update if data was complete. |
| Output too long | Model became verbose | Prompt update to specify length constraints. |
| Low structural similarity | Major format overhaul by model | Flag for human review — may need spec update if new format is better. |

The improvement agent (Phase 3) can be extended to make prompt modifications for scheduled skills, following the same guardrail approach: propose a change to the skill's SKILL.md, run the skill with test data, compare against the format spec, commit only if format score improves with no regressions.

### 4.7 Spec Evolution

Format specs aren't static. When a skill is intentionally redesigned:

1. Update `golden_examples` with 3-5 new reference outputs
2. Adjust `required_sections`, `required_indicators`, etc.
3. Reset drift history for that skill
4. Run the skill once and verify score ≥ threshold

A CLI command handles this:

```bash
# Update golden examples for a skill from recent good outputs
python -m peterbot.scheduled_monitor update-golden morning-briefing --last 5

# View current drift status for all skills
python -m peterbot.scheduled_monitor status

# View drift history for a specific skill
python -m peterbot.scheduled_monitor history morning-briefing --days 14
```

---

## Phase 5: Morning Quality Report

### 5.1 Overview

Every morning, before the regular morning briefing runs, a consolidated quality report is posted to `#peterbot-dev`. This is the single place to check parser and output health each day — no need to dig through logs or databases.

### 5.2 Execution Schedule

```
02:00 UK  →  Improvement Agent runs (Phase 3)
02:30 UK  →  Capture cleanup
03:00 UK  →  Embedding report (existing)
06:45 UK  →  Morning Quality Report ← NEW
07:00 UK  →  Morning Briefing (existing)
```

The quality report runs at 06:45, 15 minutes before the morning briefing. This ensures:
- All overnight jobs have completed
- The report covers a full 24-hour cycle
- You see it just before the briefing, so any issues are top of mind

### 5.3 Report Structure

```
🔧 **Parser & Output Quality Report**
📅 Wednesday 5 Feb 2026 · 06:45 GMT

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 **Parser Health**
• Fixture pass rate: 296/312 (94.9%) — target ≥95%
• 24h captures: 142 total, 8 failures (5.6%)
• ANSI leaks: 0 ✅
• Echo leaks: 2 ⚠️
• Empty responses: 1 ⚠️
• Fixture cache: 314 fixtures (+2 promoted overnight)

🔄 **Overnight Improvement Cycle**
• Target stage: echo_removal
• Result: ✅ Committed — score 0.936 → 0.949
• Fixtures improved: 4 | Regressions: 0
• Cumulative cycles since last human review: 3/5

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **Scheduled Output Health**

✅ Morning Briefing        0.94  (5/5 sections, consistent)
✅ School Run Report       0.91  (4/4 sections, consistent)
⚠️ Health Digest           0.78  (missing: hydration section)
✅ News Digest             0.92  (consistent)
✅ Email Summary           0.96  (consistent)
✅ HB Daily Sales          0.89  (consistent)
⚠️ Balance Monitor         0.71  (output too short last 2 runs)
─  Weekly Health           —     (not due until Sunday)
─  Monthly Health          —     (not due until 1st)

Drift alerts (last 24h): 2
• Health Digest: hydration section missing in 3 of last 5 runs
  → Likely cause: Garmin hydration API returning empty
  → Recommended: Check data_fetchers.py hydration endpoint
• Balance Monitor: output 62 chars (min 100) at 09:00 and 10:00
  → Likely cause: API returned minimal data
  → Recommended: Review balance skill prompt for empty-data handling

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 **7-Day Trends**
• Parser pass rate: 92.1% → 94.9% (↑2.8%)
• Capture failure rate: 8.2% → 5.6% (↓2.6%)
• Scheduled output avg score: 0.88 → 0.90 (↑0.02)
• Fixtures added this week: 12

🚨 **Action Items**
1. Check Garmin hydration API — possible endpoint change
2. Review balance-monitor skill prompt for short-output handling
3. Human review checkpoint approaching (3/5 improvement cycles)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Next report: Thursday 6 Feb 2026 06:45 GMT
```

### 5.4 Report Generator

```python
# domains/peterbot/morning_quality_report.py

from datetime import datetime, timedelta
from dataclasses import dataclass

@dataclass
class QualityReport:
    """Consolidated morning quality report."""

    # Parser health
    fixture_total: int
    fixture_passed: int
    capture_total_24h: int
    capture_failures_24h: int
    ansi_leaks: int
    echo_leaks: int
    empty_responses: int
    fixture_cache_size: int
    fixtures_promoted_overnight: int

    # Improvement cycle
    improvement_ran: bool
    improvement_target: str | None
    improvement_committed: bool
    improvement_score_before: float | None
    improvement_score_after: float | None
    improvement_fixtures_improved: int
    improvement_regressions: int
    cycles_since_human_review: int

    # Scheduled output health
    scheduled_scores: list[dict]   # [{skill, score, status, sections_ok, notes}]
    drift_alerts: list[dict]       # [{skill, issue, likely_cause, recommendation}]

    # 7-day trends
    trend_parser_pass_rate: tuple[float, float]     # (7_days_ago, now)
    trend_capture_failure_rate: tuple[float, float]
    trend_scheduled_avg: tuple[float, float]
    trend_fixtures_added: int

    # Action items (auto-generated)
    action_items: list[str]

    def format_discord(self) -> str:
        """Format as Discord message."""
        now = datetime.utcnow()
        lines = []

        lines.append("🔧 **Parser & Output Quality Report**")
        lines.append(f"📅 {now.strftime('%A %d %b %Y')} · {now.strftime('%H:%M')} GMT")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # Parser health
        lines.append("📊 **Parser Health**")
        pass_rate = self.fixture_passed / self.fixture_total if self.fixture_total else 0
        fail_rate = self.capture_failures_24h / self.capture_total_24h if self.capture_total_24h else 0
        target_marker = "✅" if pass_rate >= 0.95 else "⚠️" if pass_rate >= 0.90 else "❌"

        lines.append(f"• Fixture pass rate: {self.fixture_passed}/{self.fixture_total} "
                      f"({pass_rate:.1%}) {target_marker}")
        lines.append(f"• 24h captures: {self.capture_total_24h} total, "
                      f"{self.capture_failures_24h} failures ({fail_rate:.1%})")
        lines.append(f"• ANSI leaks: {self.ansi_leaks} {'✅' if self.ansi_leaks == 0 else '⚠️'}")
        lines.append(f"• Echo leaks: {self.echo_leaks} {'✅' if self.echo_leaks == 0 else '⚠️'}")
        lines.append(f"• Empty responses: {self.empty_responses} "
                      f"{'✅' if self.empty_responses == 0 else '⚠️'}")
        lines.append(f"• Fixture cache: {self.fixture_cache_size} fixtures "
                      f"(+{self.fixtures_promoted_overnight} promoted overnight)")
        lines.append("")

        # Improvement cycle
        lines.append("🔄 **Overnight Improvement Cycle**")
        if self.improvement_ran:
            status = "✅ Committed" if self.improvement_committed else "❌ Rolled back"
            lines.append(f"• Target stage: {self.improvement_target}")
            lines.append(f"• Result: {status} — score "
                          f"{self.improvement_score_before:.3f} → {self.improvement_score_after:.3f}")
            lines.append(f"• Fixtures improved: {self.improvement_fixtures_improved} | "
                          f"Regressions: {self.improvement_regressions}")
        else:
            lines.append("• No improvement cycle ran overnight")
        lines.append(f"• Cumulative cycles since last human review: "
                      f"{self.cycles_since_human_review}/5"
                      f"{' ⚠️ review due' if self.cycles_since_human_review >= 4 else ''}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # Scheduled output health
        lines.append("📋 **Scheduled Output Health**")
        lines.append("")
        for s in self.scheduled_scores:
            if s['status'] == 'not_due':
                lines.append(f"─  {s['skill']:<24} —     ({s['notes']})")
            else:
                marker = "✅" if s['score'] >= 0.85 else "⚠️" if s['score'] >= 0.70 else "❌"
                lines.append(f"{marker} {s['skill']:<24} {s['score']:.2f}  ({s['notes']})")

        if self.drift_alerts:
            lines.append("")
            lines.append(f"Drift alerts (last 24h): {len(self.drift_alerts)}")
            for alert in self.drift_alerts:
                lines.append(f"• {alert['skill']}: {alert['issue']}")
                lines.append(f"  → Likely cause: {alert['likely_cause']}")
                lines.append(f"  → Recommended: {alert['recommendation']}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # 7-day trends
        lines.append("📈 **7-Day Trends**")
        pr_old, pr_new = self.trend_parser_pass_rate
        cf_old, cf_new = self.trend_capture_failure_rate
        sa_old, sa_new = self.trend_scheduled_avg

        pr_arrow = "↑" if pr_new > pr_old else "↓" if pr_new < pr_old else "→"
        cf_arrow = "↓" if cf_new < cf_old else "↑" if cf_new > cf_old else "→"
        sa_arrow = "↑" if sa_new > sa_old else "↓" if sa_new < sa_old else "→"

        lines.append(f"• Parser pass rate: {pr_old:.1%} → {pr_new:.1%} "
                      f"({pr_arrow}{abs(pr_new - pr_old):.1%})")
        lines.append(f"• Capture failure rate: {cf_old:.1%} → {cf_new:.1%} "
                      f"({cf_arrow}{abs(cf_new - cf_old):.1%})")
        lines.append(f"• Scheduled output avg score: {sa_old:.2f} → {sa_new:.2f} "
                      f"({sa_arrow}{abs(sa_new - sa_old):.2f})")
        lines.append(f"• Fixtures added this week: {self.trend_fixtures_added}")
        lines.append("")

        # Action items
        if self.action_items:
            lines.append("🚨 **Action Items**")
            for i, item in enumerate(self.action_items, 1):
                lines.append(f"{i}. {item}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        tomorrow = now + timedelta(days=1)
        lines.append(f"Next report: {tomorrow.strftime('%A %d %b %Y')} 06:45 GMT")

        return '\n'.join(lines)


class MorningQualityReportBuilder:
    """Gathers data from all subsystems and builds the morning report."""

    def __init__(self, db_path: str, regression_runner, scheduled_scorer):
        self.db_path = db_path
        self.regression_runner = regression_runner
        self.scheduled_scorer = scheduled_scorer

    def build(self) -> QualityReport:
        """Collect all data and build the report."""

        # 1. Run regression suite for current fixture status
        regression = self.regression_runner.run()

        # 2. Query 24h captures
        captures = self._get_capture_stats(hours=24)

        # 3. Get improvement cycle results (from last overnight run)
        improvement = self._get_last_improvement_result()

        # 4. Score all scheduled skills
        scheduled = self._get_scheduled_output_health()

        # 5. Compute 7-day trends
        trends = self._compute_trends()

        # 6. Generate action items
        action_items = self._generate_action_items(
            regression, captures, improvement, scheduled
        )

        return QualityReport(
            fixture_total=regression.total,
            fixture_passed=regression.passed,
            capture_total_24h=captures['total'],
            capture_failures_24h=captures['failures'],
            ansi_leaks=captures['ansi'],
            echo_leaks=captures['echo'],
            empty_responses=captures['empty'],
            fixture_cache_size=self._get_fixture_count(),
            fixtures_promoted_overnight=captures['promoted'],
            improvement_ran=improvement['ran'],
            improvement_target=improvement.get('target'),
            improvement_committed=improvement.get('committed', False),
            improvement_score_before=improvement.get('score_before'),
            improvement_score_after=improvement.get('score_after'),
            improvement_fixtures_improved=improvement.get('fixtures_improved', 0),
            improvement_regressions=improvement.get('regressions', 0),
            cycles_since_human_review=improvement.get('cycles_since_review', 0),
            scheduled_scores=scheduled['scores'],
            drift_alerts=scheduled['alerts'],
            trend_parser_pass_rate=trends['parser_pass_rate'],
            trend_capture_failure_rate=trends['capture_failure_rate'],
            trend_scheduled_avg=trends['scheduled_avg'],
            trend_fixtures_added=trends['fixtures_added'],
            action_items=action_items,
        )

    def _generate_action_items(self, regression, captures, improvement, scheduled) -> list[str]:
        """Auto-generate prioritised action items from all data sources."""
        items = []

        # Critical: regressions
        if regression.regressions > 0:
            items.append(f"🔴 {regression.regressions} fixture regressions detected — investigate immediately")

        # Drift alerts → action items
        for alert in scheduled.get('alerts', []):
            items.append(f"{alert['recommendation']} ({alert['skill']})")

        # ANSI leaks
        if captures['ansi'] > 0:
            items.append(f"ANSI leakage detected in {captures['ansi']} messages — check strip_ansi()")

        # Echo leaks
        if captures['echo'] > 2:
            items.append(f"Echo leakage elevated ({captures['echo']} in 24h) — check remove_echo()")

        # Empty responses
        if captures['empty'] > 3:
            items.append(f"High empty response rate ({captures['empty']} in 24h) — check tmux session health")

        # Human review approaching
        cycles = improvement.get('cycles_since_review', 0)
        if cycles >= 4:
            items.append(f"Human review checkpoint approaching ({cycles}/5 improvement cycles)")

        # Pass rate below target
        if regression.total > 0:
            rate = regression.passed / regression.total
            if rate < 0.90:
                items.append(f"🔴 Fixture pass rate critical ({rate:.1%}) — below 90% threshold")
            elif rate < 0.95:
                items.append(f"Fixture pass rate below target ({rate:.1%}) — target ≥95%")

        return items
```

### 5.5 Action Item Intelligence

Action items are auto-generated but need to be specific and actionable, not generic warnings. The generator follows a decision tree:

```
Drift in scheduled output?
├─ Section missing?
│   ├─ Data source returned empty → "Check {endpoint} — possible API change"
│   └─ Data source returned data → "Update {skill} SKILL.md to reinforce {section} section"
├─ Output too short?
│   ├─ Multiple skills affected → "Check Hadley API health — multiple skills returning short output"
│   └─ Single skill → "Review {skill} prompt for empty-data handling"
├─ Indicators missing?
│   └─ "Update {skill} SKILL.md to include explicit emoji requirements"
└─ Low structural similarity?
    └─ "Flag {skill} for human review — significant format change detected"

Parser failure?
├─ ANSI leaks > 0 → "Check strip_ansi() — new escape sequence pattern?"
├─ Echo leaks > 2 → "Check remove_echo() — instruction format may have changed"
├─ Empty responses > 3 → "Check tmux session health and screen capture timing"
└─ Fixture regressions > 0 → "🔴 Investigate immediately — previously passing fixtures now failing"
```

---

## Phase 6: Feedback Loop

### 6.1 Overview

The automated capture system and regression runner catch a lot, but they miss things that only a human would notice — a response that's technically well-formatted but gives the wrong answer, a briefing that has all the right sections but the traffic data is stale, or a skill output that "feels off" in a way no rubric would catch. The feedback loop gives you a way to flag these throughout the day, and they feed directly into the next improvement cycle as prioritised input.

Human feedback is weighted higher than automated signals. If you flagged it, it's real.

### 6.2 Input Methods

Four ways to submit feedback, ranging from zero-effort to detailed:

**Method 1: Reaction (zero-effort)**

React to any of Peter's messages with one of these emoji:

| Emoji | Meaning | Auto-category |
|---|---|---|
| 🔧 | Something's wrong with this response | `parser_issue` |
| 📋 | Format/structure is wrong | `format_drift` |
| ❌ | Content is wrong or missing | `content_wrong` |
| 🗑️ | This response shouldn't have been sent | `false_positive` |

The system captures the message, its raw capture data, and the reaction. No further action needed — this alone is enough signal for the improvement agent.

**Method 2: Reaction + Thread Reply (low-effort, high-value)**

React with any of the above emoji, then reply in the thread with details:

```
🔧 [reaction on Peter's message]

Chris (in thread): "The echo text from my original question is showing
at the top of this response. It starts with 'Hey Peter' and goes to
the second line."
```

The thread reply gets stored as the feedback description, linked to the message and its capture data. This is the highest-value input — the system knows exactly which message failed and exactly what the human thinks went wrong.

**Method 3: Slash Command (for general or forward-looking feedback)**

```
/parser-feedback The morning briefing has been missing the EV section
for the last 3 days. I think the KIA API might have changed.
```

```
/parser-feedback type:prompt_issue skill:morning-briefing The weather
section should show the hourly forecast, not just the current temp.
```

**Slash command parameters:**

| Parameter | Required | Default | Options |
|---|---|---|---|
| `message` | Yes | — | Free text description |
| `type` | No | `general` | `parser_issue`, `format_drift`, `content_wrong`, `prompt_issue`, `general` |
| `skill` | No | `null` | Any skill name (for scheduled output feedback) |
| `priority` | No | `normal` | `normal`, `high` |

**Method 4: Natural Language (most natural)**

In any channel, tell Peter directly. The system recognises feedback intent:

```
"Peter, that last briefing was missing the traffic section"
"Hey the health digest format has changed, it used to show steps first"
"The school run report gave the wrong departure time yesterday"
```

Peter acknowledges the feedback and stores it:

```
📝 Noted — I've logged that as format feedback on the health digest.
It'll be reviewed in tonight's improvement cycle.
```

**Intent detection triggers:**

- "that was wrong" / "that's not right" / "that's broken"
- "missing the ... section" / "should have included"
- "used to" / "it changed" / "different from before"
- "format is wrong" / "formatting issue"
- "fix the ..." / "parser issue" / "output issue"
- References to a specific skill name + a problem description

### 6.3 Feedback Store

**Location:** `data/parser_fixtures.db` (extends existing database)

```sql
CREATE TABLE feedback (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Source
    input_method    TEXT NOT NULL,            -- 'reaction' | 'thread_reply' | 'slash_command' | 'natural_language'
    channel_id      TEXT,
    channel_name    TEXT,
    user_id         TEXT NOT NULL,

    -- Linked message (if feedback is on a specific Peter response)
    discord_msg_id  TEXT,                    -- The Peter message being flagged
    capture_id      TEXT,                    -- Link to captures table (if available)

    -- Content
    category        TEXT NOT NULL DEFAULT 'general',
        -- 'parser_issue' | 'format_drift' | 'content_wrong' | 'prompt_issue' | 'false_positive' | 'general'
    skill_name      TEXT,                    -- If about a specific scheduled skill
    description     TEXT,                    -- Human description of the issue
    reaction_emoji  TEXT,                    -- Which emoji was used (if reaction-based)
    priority        TEXT DEFAULT 'normal',   -- 'normal' | 'high'

    -- Processing
    status          TEXT DEFAULT 'pending',  -- 'pending' | 'processing' | 'resolved' | 'wont_fix' | 'duplicate'
    consumed_by_cycle TEXT,                  -- ID of the improvement cycle that consumed this
    resolution      TEXT,                    -- What action was taken
    resolved_at     TIMESTAMP,

    -- Fixture promotion
    promoted_to_fixture BOOLEAN DEFAULT FALSE,
    fixture_id      TEXT
);

CREATE INDEX idx_feedback_status ON feedback(status);
CREATE INDEX idx_feedback_date ON feedback(created_at);
CREATE INDEX idx_feedback_category ON feedback(category);
CREATE INDEX idx_feedback_skill ON feedback(skill_name);
```

### 6.4 Feedback Processor

```python
# domains/peterbot/feedback_processor.py

import sqlite3
import json
from datetime import datetime
from dataclasses import dataclass

@dataclass
class FeedbackEntry:
    id: str
    input_method: str
    category: str
    skill_name: str | None
    description: str | None
    discord_msg_id: str | None
    capture_id: str | None
    priority: str
    created_at: str


class FeedbackProcessor:
    """Manages the feedback loop between human input and improvement cycles."""

    # Category detection from reaction emoji
    REACTION_CATEGORIES = {
        '🔧': 'parser_issue',
        '📋': 'format_drift',
        '❌': 'content_wrong',
        '🗑️': 'false_positive',
    }

    # Natural language intent patterns
    INTENT_PATTERNS = {
        'parser_issue': [
            r'(?:ansi|escape|garbled|mangled|broken.*output|parser)',
            r'(?:echo|instruction.*showing|my.*question.*appeared)',
            r'(?:empty.*response|blank.*message|nothing.*sent)',
        ],
        'format_drift': [
            r'(?:missing.*section|should.*(?:have|include)|used to)',
            r'(?:format.*(?:wrong|changed|different|broken))',
            r'(?:order.*(?:wrong|changed)|sections.*(?:moved|swapped))',
        ],
        'content_wrong': [
            r'(?:wrong|incorrect|inaccurate|not right)',
            r'(?:stale|outdated|old data|yesterday)',
            r'(?:should.*(?:be|say)|that.*(?:was|is)n.t)',
        ],
        'prompt_issue': [
            r'(?:prompt|instruction|skill.*(?:needs|should))',
            r'(?:tone|style|approach).*(?:wrong|different|change)',
        ],
    }

    def __init__(self, db_path: str):
        self.db_path = db_path

    def record_reaction(self, discord_msg_id: str, user_id: str,
                        emoji: str, channel_id: str,
                        channel_name: str) -> str | None:
        """Record feedback from a reaction on Peter's message."""
        category = self.REACTION_CATEGORIES.get(emoji)
        if not category:
            return None

        # Look up the capture for this message
        capture_id = self._find_capture(discord_msg_id)

        feedback_id = self._store(
            input_method='reaction',
            channel_id=channel_id,
            channel_name=channel_name,
            user_id=user_id,
            discord_msg_id=discord_msg_id,
            capture_id=capture_id,
            category=category,
            reaction_emoji=emoji,
        )
        return feedback_id

    def record_thread_reply(self, feedback_id: str, description: str):
        """Add a thread reply description to an existing reaction feedback."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE feedback SET description = ?, input_method = 'thread_reply' WHERE id = ?",
                (description, feedback_id)
            )

    def record_slash_command(self, user_id: str, channel_id: str,
                             channel_name: str, message: str,
                             category: str = 'general',
                             skill_name: str | None = None,
                             priority: str = 'normal') -> str:
        """Record feedback from /parser-feedback command."""
        return self._store(
            input_method='slash_command',
            channel_id=channel_id,
            channel_name=channel_name,
            user_id=user_id,
            category=category,
            skill_name=skill_name,
            description=message,
            priority=priority,
        )

    def record_natural_language(self, user_id: str, channel_id: str,
                                 channel_name: str, message: str,
                                 referenced_msg_id: str | None = None) -> str:
        """Record feedback from natural language detection."""
        category = self._detect_category(message)
        skill_name = self._detect_skill(message)
        capture_id = self._find_capture(referenced_msg_id) if referenced_msg_id else None

        return self._store(
            input_method='natural_language',
            channel_id=channel_id,
            channel_name=channel_name,
            user_id=user_id,
            discord_msg_id=referenced_msg_id,
            capture_id=capture_id,
            category=category,
            skill_name=skill_name,
            description=message,
        )

    def get_pending(self) -> list[FeedbackEntry]:
        """Get all pending feedback for the next improvement cycle."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM feedback
                WHERE status = 'pending'
                ORDER BY
                    CASE priority WHEN 'high' THEN 0 ELSE 1 END,
                    created_at ASC
            """).fetchall()
        return [FeedbackEntry(**dict(r)) for r in rows]

    def get_pending_summary(self) -> dict:
        """Get summary stats for pending feedback."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            total = conn.execute(
                "SELECT COUNT(*) as c FROM feedback WHERE status = 'pending'"
            ).fetchone()['c']

            by_category = {}
            rows = conn.execute("""
                SELECT category, COUNT(*) as c FROM feedback
                WHERE status = 'pending' GROUP BY category
            """).fetchall()
            for r in rows:
                by_category[r['category']] = r['c']

            by_skill = {}
            rows = conn.execute("""
                SELECT skill_name, COUNT(*) as c FROM feedback
                WHERE status = 'pending' AND skill_name IS NOT NULL
                GROUP BY skill_name
            """).fetchall()
            for r in rows:
                by_skill[r['skill_name']] = r['c']

            high_priority = conn.execute(
                "SELECT COUNT(*) as c FROM feedback WHERE status = 'pending' AND priority = 'high'"
            ).fetchone()['c']

        return {
            'total': total,
            'by_category': by_category,
            'by_skill': by_skill,
            'high_priority': high_priority,
        }

    def mark_consumed(self, feedback_ids: list[str], cycle_id: str):
        """Mark feedback as consumed by an improvement cycle."""
        with sqlite3.connect(self.db_path) as conn:
            for fid in feedback_ids:
                conn.execute("""
                    UPDATE feedback SET
                        status = 'processing',
                        consumed_by_cycle = ?
                    WHERE id = ?
                """, (cycle_id, fid))

    def resolve(self, feedback_id: str, resolution: str,
                status: str = 'resolved'):
        """Mark feedback as resolved with an explanation."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE feedback SET
                    status = ?,
                    resolution = ?,
                    resolved_at = ?
                WHERE id = ?
            """, (status, resolution, datetime.utcnow().isoformat(), feedback_id))

    def _detect_category(self, message: str) -> str:
        """Detect feedback category from natural language."""
        import re
        message_lower = message.lower()
        for category, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    return category
        return 'general'

    def _detect_skill(self, message: str) -> str | None:
        """Detect if feedback references a specific skill."""
        SKILL_KEYWORDS = {
            'morning-briefing': ['briefing', 'morning brief', 'morning report'],
            'school-run': ['school run', 'school report', 'departure'],
            'health-digest': ['health digest', 'health report', 'health summary'],
            'news-digest': ['news', 'news digest', 'headlines'],
            'email-summary': ['email', 'email summary', 'inbox'],
            'hb-daily-sales': ['sales', 'daily sales', 'hb sales', 'revenue'],
            'balance-monitor': ['balance', 'bank', 'accounts'],
            'weekly-health': ['weekly health', 'weekly report'],
            'monthly-health': ['monthly health', 'monthly report'],
        }
        message_lower = message.lower()
        for skill, keywords in SKILL_KEYWORDS.items():
            if any(kw in message_lower for kw in keywords):
                return skill
        return None

    def _find_capture(self, discord_msg_id: str | None) -> str | None:
        """Find the capture record for a Discord message."""
        if not discord_msg_id:
            return None
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id FROM captures WHERE discord_msg_id = ?",
                (discord_msg_id,)
            ).fetchone()
        return row[0] if row else None

    def _store(self, **kwargs) -> str:
        """Store a feedback entry."""
        feedback_id = self._generate_id()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO feedback
                (id, input_method, channel_id, channel_name, user_id,
                 discord_msg_id, capture_id, category, skill_name,
                 description, reaction_emoji, priority)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                feedback_id,
                kwargs.get('input_method'),
                kwargs.get('channel_id'),
                kwargs.get('channel_name'),
                kwargs.get('user_id'),
                kwargs.get('discord_msg_id'),
                kwargs.get('capture_id'),
                kwargs.get('category', 'general'),
                kwargs.get('skill_name'),
                kwargs.get('description'),
                kwargs.get('reaction_emoji'),
                kwargs.get('priority', 'normal'),
            ))
        return feedback_id

    def _generate_id(self) -> str:
        import secrets
        return secrets.token_hex(8)
```

### 6.5 Discord Integration

**Reaction handler (extends existing `on_reaction_add` in bot.py):**

```python
@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    if reaction.message.author != bot.user:
        return

    emoji = str(reaction.emoji)

    # Parser capture system (existing)
    if emoji in ('👎', '❌', '🔧', '⚠️'):
        parser_capture_store.flag_reaction(
            discord_msg_id=str(reaction.message.id),
            reaction=emoji
        )

    # Feedback loop (new)
    feedback_emoji = {'🔧', '📋', '❌', '🗑️'}
    if emoji in feedback_emoji:
        feedback_id = feedback_processor.record_reaction(
            discord_msg_id=str(reaction.message.id),
            user_id=str(user.id),
            emoji=emoji,
            channel_id=str(reaction.message.channel.id),
            channel_name=reaction.message.channel.name,
        )
        if feedback_id:
            # Store feedback_id so thread replies can be linked
            # Use a short-lived cache: message_id → feedback_id
            feedback_pending_threads[str(reaction.message.id)] = feedback_id
```

**Thread reply handler:**

```python
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Check if this is a thread reply to a feedback-flagged message
    if (message.reference and
        str(message.reference.message_id) in feedback_pending_threads):
        feedback_id = feedback_pending_threads[str(message.reference.message_id)]
        feedback_processor.record_thread_reply(feedback_id, message.content)
        await message.add_reaction('📝')  # Acknowledge
        return

    # ... rest of message handling
```

**Slash command:**

```python
@bot.tree.command(name="parser-feedback", description="Submit feedback on parser or output quality")
@app_commands.describe(
    message="Describe the issue",
    type="Type of issue",
    skill="Which scheduled skill (if applicable)",
    priority="Priority level"
)
@app_commands.choices(
    type=[
        app_commands.Choice(name="Parser issue", value="parser_issue"),
        app_commands.Choice(name="Format drift", value="format_drift"),
        app_commands.Choice(name="Content wrong", value="content_wrong"),
        app_commands.Choice(name="Prompt issue", value="prompt_issue"),
        app_commands.Choice(name="General", value="general"),
    ],
    priority=[
        app_commands.Choice(name="Normal", value="normal"),
        app_commands.Choice(name="High", value="high"),
    ]
)
async def parser_feedback(interaction, message: str,
                           type: str = "general",
                           skill: str = None,
                           priority: str = "normal"):
    feedback_id = feedback_processor.record_slash_command(
        user_id=str(interaction.user.id),
        channel_id=str(interaction.channel_id),
        channel_name=interaction.channel.name,
        message=message,
        category=type,
        skill_name=skill,
        priority=priority,
    )
    await interaction.response.send_message(
        f"📝 Feedback logged (`{feedback_id[:8]}`). "
        f"It'll be reviewed in tonight's improvement cycle.",
        ephemeral=True
    )
```

**Natural language detection (in the message handler):**

```python
# In the message routing logic, before sending to Claude Code:

import re

FEEDBACK_TRIGGERS = [
    r'(?:that|this|last)\s+(?:was|is)\s+(?:wrong|broken|bad|off)',
    r'missing\s+(?:the\s+)?(?:\w+\s+)?section',
    r'(?:format|formatting)\s+(?:is\s+)?(?:wrong|broken|changed)',
    r'used\s+to\s+(?:show|have|include|display)',
    r'(?:fix|broken|issue\s+with)\s+(?:the\s+)?(?:parser|output|response)',
    r'(?:should\s+have|should\s+include|supposed\s+to)',
    r'(?:echo|instruction)\s+(?:text|showing|leaked)',
]

def is_parser_feedback(message_text: str) -> bool:
    """Detect if a message is parser/output feedback."""
    text_lower = message_text.lower()
    return any(re.search(p, text_lower) for p in FEEDBACK_TRIGGERS)


# In message handler:
if is_parser_feedback(message.content):
    # Still send to Claude Code for a normal response, but also log feedback
    referenced_msg = None
    if message.reference:
        referenced_msg = str(message.reference.message_id)

    feedback_processor.record_natural_language(
        user_id=str(message.author.id),
        channel_id=str(message.channel.id),
        channel_name=message.channel.name,
        message=message.content,
        referenced_msg_id=referenced_msg,
    )
    # Peter responds normally AND acknowledges the feedback was captured
```

### 6.6 Feedback Consumption by Improvement Agent

The improvement agent (Phase 3) reads pending feedback during its review phase. Feedback is weighted 3x compared to automated signals:

```python
# In parser_improver.py, during review():

def _weight_signals(self, automated_failures: list, feedback: list) -> dict:
    """
    Combine automated and human signals to determine improvement priority.

    Human feedback gets 3x weight because:
    - If a human noticed it, it's definitely a real problem
    - Automated scoring might miss subtle quality issues
    - Human feedback often captures the "why" not just the "what"
    """
    signal_scores = {}  # stage → weighted score

    # Automated signals: 1x weight each
    for failure in automated_failures:
        for dim in failure.get('failed_dims', []):
            stage = self._dimension_to_stage(dim)
            signal_scores[stage] = signal_scores.get(stage, 0) + 1.0

    # Human feedback: 3x weight each
    for fb in feedback:
        if fb.category == 'parser_issue':
            # Try to map to specific stage from description
            stage = self._infer_stage_from_description(fb.description)
            signal_scores[stage] = signal_scores.get(stage, 0) + 3.0
        elif fb.category == 'format_drift':
            signal_scores['format_detect'] = signal_scores.get('format_detect', 0) + 3.0
        elif fb.category == 'content_wrong':
            signal_scores['diff_extract'] = signal_scores.get('diff_extract', 0) + 3.0

    # High priority feedback: 5x weight
    for fb in feedback:
        if fb.priority == 'high':
            stage = self._infer_stage_from_description(fb.description)
            signal_scores[stage] = signal_scores.get(stage, 0) + 2.0  # Additional 2x on top of 3x

    return signal_scores


def _infer_stage_from_description(self, description: str | None) -> str:
    """Map human description to parser stage."""
    if not description:
        return 'sanitise'  # Default

    desc_lower = description.lower()
    if any(w in desc_lower for w in ['ansi', 'escape', 'garbled', 'colour code']):
        return 'ansi_strip'
    if any(w in desc_lower for w in ['echo', 'instruction', 'question appeared', 'my message']):
        return 'echo_removal'
    if any(w in desc_lower for w in ['empty', 'blank', 'nothing', 'no response']):
        return 'diff_extract'
    if any(w in desc_lower for w in ['format', 'markdown', 'code block', 'table']):
        return 'format_detect'
    if any(w in desc_lower for w in ['truncat', 'cut off', 'split', 'too long']):
        return 'length_manage'
    return 'sanitise'
```

### 6.7 Feedback Resolution Reporting

When the improvement agent consumes feedback, it marks each item with what happened:

| Status | Meaning |
|---|---|
| `pending` | Submitted, not yet reviewed by improvement agent |
| `processing` | Picked up by current improvement cycle |
| `resolved` | Change was made that addresses this feedback |
| `wont_fix` | Reviewed but no change needed (with explanation) |
| `duplicate` | Same issue already reported (linked to original) |

Resolution messages are posted back to the original channel as a reply:

```
📝 **Feedback resolved** (`fb_a1b2c3d4`)
Your feedback about echo text appearing in responses was addressed
in tonight's improvement cycle.

Change: Updated echo_removal() with fuzzy token matching.
Parser score: 0.936 → 0.949
```

### 6.8 Feedback in the Morning Report

The morning quality report (Phase 5) includes a feedback section:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 **Feedback Summary**
• Received yesterday: 4 items
• Resolved overnight: 2 ✅
• Pending review: 1 ⏳
• Won't fix: 1 (duplicate)

Resolved:
• 🔧 Echo text in response (parser_issue) → fixed in echo_removal stage
• 📋 Health digest missing hydration (format_drift) → Garmin API endpoint updated

Pending:
• 📋 School run report departure time wrong (content_wrong)
  → Needs manual investigation — traffic API data was correct

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 6.9 Feedback Lifecycle Flow

```
                    ┌──────────────────────────────────────────┐
                    │              Throughout the day           │
                    │                                          │
                    │  🔧 Reaction    /parser-feedback          │
                    │  📋 Reaction    "that was wrong"          │
                    │  + Thread reply  Natural language         │
                    │                                          │
                    └────────────────┬─────────────────────────┘
                                     │
                                     ▼
                    ┌──────────────────────────────────────────┐
                    │          Feedback Store (SQLite)          │
                    │                                          │
                    │  status: pending                         │
                    │  Accumulates throughout the day           │
                    │                                          │
                    └────────────────┬─────────────────────────┘
                                     │
                              02:00 UK overnight
                                     │
                                     ▼
                    ┌──────────────────────────────────────────┐
                    │     Improvement Agent — Review Phase      │
                    │                                          │
                    │  1. Read all pending feedback             │
                    │  2. Weight 3x vs automated signals        │
                    │  3. Map to parser stages                  │
                    │  4. Include in recommended_target         │
                    │  5. Mark feedback as 'processing'         │
                    │                                          │
                    └────────────────┬─────────────────────────┘
                                     │
                          Improvement cycle runs
                                     │
                          ┌──────────┴──────────┐
                          │                     │
                    Change committed       Change rolled back
                          │                     │
                          ▼                     ▼
                    Mark feedback          Mark feedback
                    status: resolved       status: pending
                    Post resolution        (retry next cycle)
                    to Discord
                                     │
                              06:45 UK
                                     │
                                     ▼
                    ┌──────────────────────────────────────────┐
                    │         Morning Quality Report            │
                    │                                          │
                    │  💬 Feedback Summary section              │
                    │  Shows resolved, pending, won't fix       │
                    │                                          │
                    └──────────────────────────────────────────┘
```

---

## Scheduled Job Integration

Add to `SCHEDULE.md`:

| Time | Skill | Channel | Description |
|---|---|---|---|
| `daily 02:00 UK` | `parser-improve` | `#peterbot-dev` | Self-improving parser cycle (consumes feedback) |
| `daily 02:30 UK` | `parser-capture-cleanup` | — | Clean old captures (keep 7 days normal, 28 days failures) |
| `daily 06:45 UK` | `morning-quality-report` | `#peterbot-dev` | Consolidated parser & output quality report |

**Always-on listeners (not scheduled):**

| Listener | Trigger | Action |
|---|---|---|
| Reaction handler | 🔧 📋 ❌ 🗑️ on Peter's messages | Store feedback entry |
| Thread reply handler | Reply in thread after feedback reaction | Attach description to feedback |
| `/parser-feedback` | Slash command invocation | Store feedback entry |
| Natural language detector | Feedback intent phrases in any channel | Store feedback entry + acknowledge |

**Execution order (overnight pipeline):**

```
                          Throughout the day
                          │
                          │  Feedback accumulates via reactions,
                          │  slash commands, natural language
                          │
23:00 UK  ─────  Quiet hours begin (no scheduled jobs)
                  │
02:00 UK  ─────  parser-improve: Self-improving agent cycle
                  ├─ Review 24h captures + fixture failures
                  ├─ Read pending feedback (weighted 3x)
                  ├─ Plan targeted parser change
                  ├─ Implement (guardrailed)
                  ├─ Validate (full regression)
                  ├─ Commit or rollback
                  └─ Resolve consumed feedback + post resolutions
                  │
02:30 UK  ─────  parser-capture-cleanup: Remove old captures
                  │
03:00 UK  ─────  embedding_report (existing)
                  capture_cleanup (existing)
                  │
06:00 UK  ─────  Quiet hours end
                  │
06:45 UK  ─────  morning-quality-report:
                  ├─ Run regression suite (fresh scores)
                  ├─ Aggregate 24h capture stats
                  ├─ Score all scheduled output specs
                  ├─ Summarise feedback (resolved/pending/won't fix)
                  ├─ Compute 7-day trends
                  ├─ Generate action items
                  └─ Post to #peterbot-dev
                  │
07:00 UK  ─────  Morning Briefing (existing)
```

---

## Implementation Order

### Phase 1 (Fixture Cache + Capture System)

1. Create `data/parser_fixtures.db` with both schemas
2. Build `ParserCaptureStore` class
3. Wire capture points into `router.py` (points A, B, C)
4. Wire reaction tracking into `bot.py`
5. Run seed extraction: pull 7 days of captures, auto-classify, store as fixtures
6. Manual review pass: correct categories, verify expected outputs
7. Build synthetic adversarial fixtures (80)
8. Curate known failure fixtures (70)
9. Verify 300+ fixtures with full category coverage

### Phase 2 (Regression Runner)

1. Build `ParserScorer` with all six dimensions
2. Build `RegressionRunner` with report generation
3. Build CLI interface
4. Create `parser_fn` wrapper that calls existing parser.py + pipeline.py
5. Run initial baseline: record current pass rate
6. Fix any scorer bugs surfaced by real data
7. Add regression run to CI / pre-commit workflow

### Phase 3 (Self-Improving Agent)

1. Build review phase (capture + fixture analysis)
2. Build plan phase (targeted change proposal)
3. Build implement phase with guardrails
4. Build validate & commit logic
5. Build Discord reporting
6. Add to SCHEDULE.md as daily job
7. Monitor first 5 cycles closely (human review)
8. Enable autonomous operation after confidence is established

### Phase 4 (Scheduled Output Monitor)

1. Create `scheduled_output_specs` and `scheduled_output_history` tables
2. Build `ScheduledOutputScorer` with section detection and structural similarity
3. Define format specs for all recurring skills (seed from recent good outputs)
4. Build golden example extraction CLI (`update-golden`, `status`, `history`)
5. Wire scoring into `router.py` for scheduled responses
6. Build drift response action decision tree
7. Backfill 7 days of scheduled output history from capture_store
8. Verify scoring accuracy against known good/bad outputs

### Phase 5 (Morning Quality Report)

1. Build `MorningQualityReportBuilder` data collection layer
2. Build `QualityReport.format_discord()` output formatter
3. Build action item generator with decision tree logic
4. Build 7-day trend computation (queries across fixtures + captures + scheduled_output_history)
5. Create `morning-quality-report` skill definition
6. Add to SCHEDULE.md at 06:45 UK → #peterbot-dev
7. Test with 3 days of manual runs before enabling schedule
8. Iterate on report format based on actual usefulness

### Phase 6 (Feedback Loop)

1. Create `feedback` table in parser_fixtures.db
2. Build `FeedbackProcessor` class with all four input methods
3. Wire reaction handler into `bot.py` (extend existing `on_reaction_add`)
4. Wire thread reply handler into `bot.py` message handler
5. Build `/parser-feedback` slash command
6. Build natural language intent detection with trigger patterns
7. Wire feedback consumption into improvement agent review phase (Phase 3)
8. Build feedback resolution posting (reply to original channel)
9. Add feedback summary section to morning quality report (Phase 5)
10. Test all four input methods end-to-end
11. Monitor false positive rate on natural language detection for first week

---

## Success Metrics

### Parser Health (Phases 1-3)

| Metric | Baseline | Target (30 days) | Target (90 days) |
|---|---|---|---|
| Fixture pass rate | TBD (measure at Phase 2) | ≥ 95% | ≥ 98% |
| 24h capture failure rate | TBD (measure at Phase 1) | < 5% | < 2% |
| ANSI leakage incidents | TBD | 0 per day | 0 per day |
| Instruction echo leakage | TBD | < 1 per day | 0 per day |
| Empty responses (false) | TBD | < 2 per day | < 1 per day |
| Fixture cache size | 300 | 400+ | 600+ |
| Improvement cycles (successful) | 0 | 10+ | 30+ |
| Regressions caused by agent | 0 | 0 | 0 |

### Scheduled Output Health (Phase 4)

| Metric | Baseline | Target (30 days) | Target (90 days) |
|---|---|---|---|
| Average format score (all skills) | TBD | ≥ 0.88 | ≥ 0.92 |
| Skills scoring below threshold | TBD | ≤ 2 per day | ≤ 1 per day |
| Drift alerts requiring human action | TBD | < 3 per week | < 1 per week |
| Drift alerts auto-resolved | 0% | 40% | 70% |
| Skills with defined format specs | 0 | All recurring skills | All recurring skills |
| Golden examples per skill | 0 | ≥ 3 | ≥ 5 |

### Operational Health (Phase 5)

| Metric | Baseline | Target (30 days) | Target (90 days) |
|---|---|---|---|
| Morning report delivered on time | N/A | ≥ 95% | ≥ 99% |
| Action items generated per report | N/A | ≤ 5 (lower = healthier) | ≤ 3 |
| Action items actioned within 24h | N/A | ≥ 60% | ≥ 80% |
| False positive action items | N/A | < 30% | < 15% |

### Feedback Loop (Phase 6)

| Metric | Baseline | Target (30 days) | Target (90 days) |
|---|---|---|---|
| Feedback items resolved per cycle | N/A | ≥ 50% of pending | ≥ 75% of pending |
| Average feedback resolution time | N/A | < 24h | < 18h |
| Feedback items promoted to fixtures | N/A | ≥ 30% | ≥ 50% |
| Natural language detection false positives | N/A | < 20% | < 10% |
| Feedback-driven improvements (% of cycles) | 0% | ≥ 30% | ≥ 50% |

---

*This specification is designed to be implemented by Claude Code using the standard agent workflow: /test-plan → /test-build → /test-execute → /code-review → commit.*

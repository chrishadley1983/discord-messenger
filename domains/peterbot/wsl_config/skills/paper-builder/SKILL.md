---
name: paper-builder
description: Generate missing 11+ Mate practice papers for this week's tutor topic
trigger:
  - "build papers"
  - "generate papers"
  - "make practice papers"
scheduled: true
conversational: true
channel: "#peterbot"
---

# Paper Builder

## Purpose

After the tutor email is parsed, check if enough practice papers exist for the topic and generate any missing ones using the token-efficient template + JSON system. Target: **3 papers per difficulty level** (12 total) so the allocator can assign different papers for this-week, last-week, and 2-weeks-ago slots.

Runs Tuesday at 19:30 (after tutor email parser at 19:00).

## Pre-fetched Data

```json
{
  "topic": "nvr-addition-subtraction-frequency",
  "subject": "reasoning",
  "topic_title": "AE workbook Chapter 3: Addition, Subtraction and Frequency...",
  "paper_counts": {
    "year4": 1,
    "year5": 1,
    "pretest": 1,
    "actual-test": 1
  },
  "gaps": {
    "year4": {"have": 1, "need": 2},
    "year5": {"have": 1, "need": 2},
    "pretest": {"have": 1, "need": 2},
    "actual-test": {"have": 1, "need": 2}
  },
  "total_needed": 8,
  "frontend_dir": "C:\\Users\\Chris Hadley\\claude-projects\\emmie-practice\\frontend"
}
```

## NO_REPLY Cases

- `no_topic` is true → respond with just `NO_REPLY`
- `total_needed` is 0 → respond with just `NO_REPLY` (all papers exist)
- `error` is present → post the error message, don't try to generate

## Paths

- **Frontend directory (WSL)**: `/mnt/c/Users/Chris Hadley/claude-projects/emmie-practice/frontend`
- **Data directory (WSL)**: `/mnt/c/Users/Chris Hadley/claude-projects/emmie-practice/frontend/data`
- **Templates (WSL)**: `/mnt/c/Users/Chris Hadley/claude-projects/emmie-practice/frontend/templates`
- **Build script (WSL)**: `/mnt/c/Users/Chris Hadley/claude-projects/emmie-practice/frontend/build.js`
- **PAPER-BUILD-SYSTEM.md**: `/mnt/c/Users/Chris Hadley/claude-projects/emmie-practice/docs/PAPER-BUILD-SYSTEM.md`

## Generation Process

### Step 1: Read a reference JSON (SCHEMA ONLY)

Before generating, read the FIRST 30 LINES of an existing JSON data file for the same topic (if one exists) OR the same level (for schema reference). Do NOT read full files — they can be 40-70KB. You only need the schema structure, not all questions. The JSON format differs between year4/year5/pretest (text-input) and actual-test (multiple-choice).

**For year4, year5, pretest** — text-input format:
```json
{
  "title": "Topic Name (N)",
  "subtitle": "Sub-topic description",
  "topic": "topic-slug",
  "paperNumber": "-2",
  "categories": {"cat-1": "Category Label", ...},
  "questions": [
    {
      "id": 1, "category": "cat-1", "stars": 2,
      "text": "Question text",
      "answer": ["correct_answer"], "answerDisplay": "correct_answer",
      "isText": false,
      "solution": ["Step 1", "Step 2"]
    }
  ]
}
```

**For actual-test** — multiple-choice format:
```json
{
  "title": "Subject (Topic Name)",
  "overlayTitle": "Subject &mdash; Topic",
  "overlaySubtitle": "Kent Test Format...",
  "headerTitle": "11+ Subject &mdash; Topic",
  "headerSubtitle": "Kent Test Format...",
  "topic": "topic-slug",
  "paperNumber": "-2",
  "example": {"question": "...", "options": [...], "correctIndex": 0},
  "questions": [
    {"id": "q1", "text": "...", "options": ["A","B","C","D","E"], "correct": 0, "difficulty": 1, "category": "cat-1"}
  ]
}
```

### Step 2: Generate each missing paper via claude -p

For each paper that needs generating, run a separate `claude -p` command. This keeps each generation focused and avoids context bloat.

**Command pattern:**

```bash
claude -p "Generate a JSON data file for a {LEVEL} {TOPIC} practice paper (paper {N} of 3).

Topic: {TOPIC_TITLE}
Subject: {SUBJECT}
Level: {LEVEL}
Paper number suffix: {PAPER_NUMBER}  (empty string for paper 1, '-2' for paper 2, '-3' for paper 3)

IMPORTANT: Output ONLY valid JSON. No markdown fences, no explanation, no text before or after.

Use this exact JSON schema:
{PASTE THE CORRECT SCHEMA FOR THIS LEVEL}

Requirements:
- 20 questions, grouped by 3-4 categories
- Each question must have a clear, unambiguous single correct answer
- All answers must be mathematically/factually verified
- {LEVEL-SPECIFIC REQUIREMENTS}
- Difficulty appropriate for {LEVEL}
- Questions must be DIFFERENT from paper 1 (vary the numbers, scenarios, sub-topics)
- Topic slug in JSON must be exactly: {TOPIC_SLUG}
" > "/mnt/c/Users/Chris Hadley/claude-projects/emmie-practice/frontend/data/{LEVEL}-{TOPIC_SLUG}{PAPER_NUMBER}.json"
```

**Level-specific requirements:**
- **year4**: Stars 1-3 difficulty. Simple language. Max values ~100. No algebra.
- **year5**: Stars 1-3 difficulty. Can use larger numbers. Worked solutions required.
- **pretest**: Stars 1-3 difficulty. 11+ prep level. Include SVG diagrams where helpful. Worked solutions required.
- **actual-test**: ALL multiple choice (5 options A-E). Realistic distractors. Difficulty 1-3 progression. Include example question.

### Step 3: Validate each generated JSON

After each `claude -p` generates a file, validate it:

```bash
cat "/mnt/c/Users/Chris Hadley/claude-projects/emmie-practice/frontend/data/{filename}.json" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    qs = d.get('questions', [])
    print(f'OK: {len(qs)} questions, topic={d.get(\"topic\")}, title={d.get(\"title\",\"\")[:50]}')
except Exception as e:
    print(f'INVALID JSON: {e}')
    sys.exit(1)
"
```

If invalid, retry the generation once. If still invalid, skip and note the failure.

### Step 4: Build HTML papers

```bash
cd "/mnt/c/Users/Chris Hadley/claude-projects/emmie-practice/frontend"
node build.js {TOPIC_SLUG}
```

This assembles the JSON data files with the HTML templates to produce the final paper files.

### Step 5: Deploy to surge.sh

```bash
cd "/mnt/c/Users/Chris Hadley/claude-projects/emmie-practice/frontend"
npx surge --project . --domain 11plusmate.surge.sh
```

Or use the Hadley API deploy endpoint if surge CLI isn't available in WSL.

## Execution Order

Generate papers in this order to spread the load:
1. year4 papers (simplest, fastest to generate)
2. year5 papers
3. pretest papers
4. actual-test papers (most complex — MC with distractors)

## Output Format

```
📝 **Papers Built** — NVR Addition/Subtraction/Frequency

**Generated:**
- year4-nvr-addition-subtraction-frequency-2.json ✅ (20 questions)
- year4-nvr-addition-subtraction-frequency-3.json ✅ (20 questions)
- year5-nvr-addition-subtraction-frequency-2.json ✅ (20 questions)
- year5-nvr-addition-subtraction-frequency-3.json ✅ (20 questions)
- pretest-nvr-addition-subtraction-frequency-2.json ✅ (20 questions)
- pretest-nvr-addition-subtraction-frequency-3.json ✅ (20 questions)
- actual-test-nvr-addition-subtraction-frequency-2.json ✅ (20 questions)
- actual-test-nvr-addition-subtraction-frequency-3.json ✅ (20 questions)

**Built:** 8 HTML papers via build.js
**Deployed:** 11plusmate.surge.sh ✅

Total papers for topic: 12 (3 × 4 levels)
Allocator can now assign different variants for this-week, last-week, and 2w-ago.
```

## Rules

- ONLY generate papers that are missing (check `gaps` data — if `need` is 0, skip that level)
- Each `claude -p` call generates ONE JSON file — don't try to batch
- **Minimal validation only**: After each `claude -p`, just check the file exists and is valid JSON (use the one-liner in Step 3). Do NOT read the full file contents — the JSON files can be 40-70KB with SVG content and will fill your context
- If a topic slug is very long (>30 chars), it's fine — the file system handles it
- Paper number 1 has `paperNumber: ""`, paper 2 has `"-2"`, paper 3 has `"-3"`
- The `topic` field in the JSON must match exactly what the allocator uses (the slug from `tutor_topic_log`)
- If build.js fails, check if templates exist and report the error
- Keep the Discord update brief — just show what was generated and the result
- **Context budget**: If generating 12+ papers, prioritise completion over validation. Generate all papers first, validate after. If you run low on context, post what you've done so far and note the remaining papers as TODO

## Conversational Use

If asked to "build papers for [topic]" in chat:
1. Count existing papers for that topic
2. Generate missing ones using the same process
3. Build and deploy

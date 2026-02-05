# Behaviour Analyser Agent Specification

**Version:** 1.0  
**Type:** Initializer (Observational) + Advisory  
**Command:** `/behaviour-analyse [mode]`  
**Project:** PeterBot (Primary), adaptable to any bot/assistant system

---

## Table of Contents

1. [Overview](#1-overview)
2. [Design Principles Alignment](#2-design-principles-alignment)
3. [Modes](#3-modes)
4. [Standard Boot Sequence](#4-standard-boot-sequence)
5. [Phase 1: Capture Pipeline](#5-phase-1-capture-pipeline)
6. [Phase 2: Interaction Classification](#6-phase-2-interaction-classification)
7. [Phase 3: Pattern Analysis](#7-phase-3-pattern-analysis)
8. [Phase 4: Quality Scoring](#8-phase-4-quality-scoring)
9. [Phase 5: Enhancement Recommendations](#9-phase-5-enhancement-recommendations)
10. [Phase 6: Personality Calibration](#10-phase-6-personality-calibration)
11. [Anti-Bias Prompts](#11-anti-bias-prompts)
12. [State Management](#12-state-management)
13. [Behaviour Registry Schema](#13-behaviour-registry-schema)
14. [Error Handling](#14-error-handling)
15. [Output Templates](#15-output-templates)
16. [Handoffs](#16-handoffs)
17. [Examples](#17-examples)

---

## 1. Overview

### 1.1 Purpose

The Behaviour Analyser Agent captures, classifies, and analyses ALL PeterBot output — responses, actions, tool calls, memory retrievals, and failures — to systematically identify opportunities for enhancing Peter's behaviour as a Personal Assistant. Its goal is to evolve Peter from a functional relay into the **best possible PA tailored specifically to Chris's needs, communication style, and daily workflow**.

### 1.2 Why This Agent?

PeterBot is designed to replace Claude.ai as the primary AI interface. As usage scales, behaviour patterns emerge that are invisible in individual conversations:
- Responses that miss context the memory system should have provided
- Tone mismatches (too formal for casual chat, too casual for work tasks)
- Repeated failures to understand intent on specific topic types
- Missed opportunities for proactive assistance
- Memory retrieval that injects irrelevant or stale context
- Actions that take too many steps when shortcuts exist
- Moments where Peter could have anticipated a need but didn't

Without systematic observation, these patterns remain anecdotal. This agent turns them into actionable, prioritised improvements.

### 1.3 The Vision

Peter should evolve towards a PA that:

| Attribute | Description |
|-----------|-------------|
| **Anticipatory** | Knows what Chris needs before he asks (based on time, context, patterns) |
| **Contextually Aware** | Always has the right memory loaded — never asks "what project?" when it's obvious |
| **Tonally Calibrated** | Matches the mood — concise during work sprints, conversational during downtime |
| **Proactively Helpful** | Surfaces reminders, flags conflicts, suggests actions at the right moment |
| **Efficiently Capable** | Uses the shortest path to accomplish tasks (fewer tool calls, better routing) |
| **Honest About Limits** | Says "I don't know" rather than confabulating, and routes to the right tool |

### 1.4 Scope

| In Scope | Out of Scope |
|----------|--------------|
| All PeterBot responses (text, actions, tool calls) | Claude.ai conversations (separate system) |
| Memory retrieval quality (what was injected, was it relevant?) | Memory system architecture (that's peterbot-mem design) |
| Response quality (accuracy, helpfulness, tone) | Code quality of the bot itself (that's Tech-Debt Agent) |
| Interaction patterns (what works, what fails) | Security/privacy of messages (that's Security Agent) |
| Proactive behaviour opportunities | Feature implementation (that's the build pipeline) |
| Personality consistency and calibration | Personality design (that's a human decision) |
| User satisfaction signals | Explicit user feedback collection (no surveys) |

### 1.5 Relationship to Memory System

```
PeterBot Memory Architecture:
┌───────────────────────────────────────────────────────┐
│ Discord Messages                                       │
│     ↓ capture                                          │
│ peterbot-mem (observations, compression, retrieval)    │
│     ↓ inject                                           │
│ Claude Code Session                                    │
│     ↓ respond                                          │
│ Discord Response                                       │
│     ↓ capture (response pair)                          │
│ peterbot-mem (store pair)                              │
│                                                        │
│ ──── Behaviour Analyser sits HERE ────                 │
│                                                        │
│ Reads: ALL of the above                                │
│ Analyses: Quality, patterns, gaps                      │
│ Outputs: Enhancement recommendations                   │
│ Does NOT: Modify memory, change responses, alter flow  │
└───────────────────────────────────────────────────────┘
```

The Behaviour Analyser is **read-only and advisory**. It observes and recommends. Changes to Peter's behaviour happen through the normal build pipeline (Define Done → Feature Spec → Build → Verify).

---

## 2. Design Principles Alignment

| Principle | Implementation |
|-----------|----------------|
| **Externalise the Goal** | Behaviour Registry (`behaviour-registry.json`) — machine-readable log of all observations with quality scores and enhancement opportunities |
| **Atomic Progress** | Each analysis session processes a batch of interactions, scores them, logs findings. Never modifies the system. |
| **Clean Campsite** | Every analysis produces a report. Registry is always current. Recommendations are structured and actionable. |
| **Standard Boot-up** | Reads CLAUDE.md → reads behaviour state → loads recent interaction log → checks what's been analysed → proceeds |
| **Tests as Truth** | Enhancement recommendations include verification criteria. When implemented, Verify Done checks the improvement landed. |

---

## 3. Modes

### 3.1 Analysis Modes

| Command | Scope | When to Use |
|---------|-------|-------------|
| `/behaviour-analyse recent` | Last 24 hours of interactions | Daily review |
| `/behaviour-analyse session <id>` | Specific conversation session | After a notably good/bad interaction |
| `/behaviour-analyse full` | Full interaction history | Weekly/sprint review |
| `/behaviour-analyse topic <keyword>` | Interactions about a specific topic | Deep-dive on a domain |
| `/behaviour-analyse failures` | Only failed/poor interactions | Targeted improvement |

### 3.2 Report Modes

| Command | Output | When to Use |
|---------|--------|-------------|
| `/behaviour-analyse report` | Summary dashboard of current state | Sprint planning |
| `/behaviour-analyse trends` | Trend analysis over time | Monthly review |
| `/behaviour-analyse recommendations` | Prioritised enhancement backlog | Before development work |
| `/behaviour-analyse personality` | Personality calibration report | Quarterly review |

---

## 4. Standard Boot Sequence

```
┌─────────────────────────────────────────────────────────────┐
│ BOOT SEQUENCE                                                │
│                                                               │
│ 1. Read CLAUDE.md (PeterBot project context)                 │
│ 2. Read docs/agents/behaviour/state.json                     │
│    → lastAnalysisDate, interactionsProcessed, batchCursor    │
│ 3. Read docs/agents/behaviour/behaviour-registry.json        │
│    → Current observations, scores, recommendations           │
│ 4. Load interaction log since last analysis                  │
│    → Source: peterbot-mem SQLite (message pairs)              │
│    → Source: Discord message history (if accessible)          │
│    → Source: Claude Code session logs (tool calls, errors)    │
│ 5. Count unprocessed interactions                             │
│    → "48 new interactions since last analysis"                │
│ 6. Report boot status                                        │
│ 7. Proceed based on mode                                     │
└─────────────────────────────────────────────────────────────┘
```

### Data Sources

| Source | What It Provides | Access Method |
|--------|-----------------|---------------|
| peterbot-mem SQLite | Message pairs (user input + bot response), timestamps, channel | Direct DB query |
| peterbot-mem ChromaDB | Compressed observations, semantic embeddings | ChromaDB query |
| Discord message history | Raw messages, reactions, edits, deletions | Discord API / bot logs |
| Claude Code session logs | Tool calls, errors, token usage, duration | Session log files |
| Memory injection logs | What context was retrieved and injected per request | peterbot-mem retrieval logs |

---

## 5. Phase 1: Capture Pipeline

### 5.1 What Gets Captured

Every interaction produces an **Interaction Record**:

```json
{
  "id": "INT-2026-02-01-001",
  "timestamp": "2026-02-01T10:30:00Z",
  "channel": "#peterbot",
  "sessionId": "sess-abc123",
  "userInput": {
    "text": "What's on my calendar today?",
    "intent": null,
    "context": "morning, weekday"
  },
  "memoryInjected": {
    "coreContext": ["lives in Tonbridge", "runs Hadley Bricks"],
    "activeProjects": ["PeterBot Phase 1", "eBay API integration"],
    "semanticResults": ["Japan trip planning April 2026"],
    "recentChat": ["discussed eBay listing optimiser yesterday"]
  },
  "botResponse": {
    "text": "Here's your calendar for today...",
    "actions": ["list_gcal_events"],
    "toolCalls": 1,
    "tokenUsage": 850,
    "duration": "2.3s"
  },
  "outcome": {
    "userFollowUp": null,
    "satisfaction": null,
    "errorOccurred": false
  }
}
```

### 5.2 Satisfaction Signal Detection

Since we don't explicitly survey, satisfaction is inferred from signals:

| Signal | Interpretation | Confidence |
|--------|---------------|------------|
| User says "thanks", "perfect", "great" | Positive | High |
| User immediately asks follow-up on same topic | Neutral-positive (needed more) | Medium |
| User rephrases the same question | Negative (wasn't understood) | High |
| User says "no", "that's wrong", "not what I meant" | Negative | High |
| User corrects Peter's output | Negative (but recoverable) | High |
| User moves to different topic quickly | Neutral | Low |
| User provides more context after response | Negative (context was missing) | Medium |
| Long pause before next message | Ambiguous | Low |
| User asks Claude.ai the same question | Negative (Peter failed) | Very High |
| User gives thumbs reaction on Discord | Positive | High |
| User gives thumbs down / ❌ on Discord | Negative | Very High |

---

## 6. Phase 2: Interaction Classification

Every interaction is classified along multiple dimensions:

### 6.1 Intent Categories

| Category | Code | Examples |
|----------|------|---------|
| **Information Retrieval** | `INFO` | "What's on my calendar?", "Check eBay sales" |
| **Task Execution** | `TASK` | "Send that email", "Create a listing" |
| **Planning & Strategy** | `PLAN` | "Help me plan the Japan trip", "What should I work on?" |
| **Creative/Ideation** | `CREATE` | "Draft a listing title for this set", "Write a message to Abby" |
| **Conversation/Social** | `SOCIAL` | "How's it going?", casual chat |
| **Technical/Development** | `DEV` | "Fix that bug in the heartbeat", "Run the tests" |
| **Memory/Recall** | `RECALL` | "What did we discuss yesterday?", "When is the race?" |
| **Emotional/Support** | `EMOTE` | "I'm stressed about deadlines", venting |

### 6.2 Complexity Tiers

| Tier | Description | Expected Behaviour |
|------|-------------|-------------------|
| **Simple** | Single fact, single action | Immediate, concise response |
| **Moderate** | Requires context + action | Memory injection + tool call |
| **Complex** | Multi-step, requires reasoning | Planning + multiple tool calls + synthesis |
| **Ambiguous** | Unclear intent | Clarification OR smart default |

### 6.3 Context Dependency

| Level | Description | Memory Requirement |
|-------|-------------|-------------------|
| **None** | Generic question, no personal context needed | Minimal injection |
| **Light** | Benefits from knowing name/preferences | Core context only |
| **Heavy** | Requires project/activity knowledge | Full tiered retrieval |
| **Critical** | Answer depends entirely on personal memory | Precise semantic search |

---

## 7. Phase 3: Pattern Analysis

The core analytical engine. Processes batches of interactions to find patterns:

### 7.1 Success Patterns (What's Working)

| Pattern | Detection | Example |
|---------|-----------|---------|
| **Fast Resolution** | Single exchange, positive signal | "What's the weather?" → accurate answer → "thanks" |
| **Effective Memory Use** | Context injection matched the need | Memory included Japan trip when asked about April plans |
| **Appropriate Tone** | Response matched the mood/context | Casual chat got casual response, work task got structured response |
| **Proactive Value** | Bot offered something unasked but useful | Reminded about upcoming deadline during morning check-in |
| **Efficient Routing** | Used minimal tool calls | Calendar check used 1 API call, not 3 |

### 7.2 Failure Patterns (What's Not Working)

| Pattern | Detection | Impact | Example |
|---------|-----------|--------|---------|
| **Context Miss** | User had to provide context that memory should have known | Frustration, wasted time | "I told you about this yesterday" |
| **Tone Mismatch** | Overly formal/casual for the situation | Feels robotic or unprofessional | Business email drafted in casual tone |
| **Over-Verbose** | Response way longer than needed | Wastes reading time | Simple yes/no question gets 5 paragraphs |
| **Under-Informative** | Response too brief, missing key details | Requires follow-up | "How are sales?" → "Fine" (no data) |
| **Wrong Tool** | Used inappropriate tool or missed available tool | Slow, inaccurate | Web search for something in Google Drive |
| **Hallucination** | Confabulated facts not in memory or knowledge | Trust erosion | Stated a meeting exists that doesn't |
| **Repeated Clarification** | Had to ask >1 clarifying question | Slow, annoying | "What project?" when context was obvious |
| **Missed Opportunity** | Could have been proactive but wasn't | Unrealised PA potential | Didn't mention schedule conflict when discussing plans |
| **Memory Pollution** | Injected irrelevant context that confused the response | Wrong answers | Old project context mixed into current discussion |
| **Personality Drift** | Response style inconsistent with established persona | Uncanny valley | Suddenly formal after being casual all day |

### 7.3 Opportunity Patterns (What Could Be Better)

| Pattern | Detection | Enhancement |
|---------|-----------|-------------|
| **Routine Requests** | Same question asked repeatedly at similar times | Automate (proactive morning briefing) |
| **Multi-Step Workflows** | User chains 3+ commands for one goal | Create compound action |
| **Predictable Needs** | Pattern of need after certain triggers | Pre-fetch or suggest |
| **Preference Expression** | User corrects style/format repeatedly | Learn and apply preference |
| **External Knowledge Gap** | Peter can't answer but Claude.ai could | Add tool/capability |
| **Time-Sensitive Gaps** | User asks about something after it's too late | Earlier proactive alert |

---

## 8. Phase 4: Quality Scoring

Each interaction and each pattern receives a quality score:

### 8.1 Interaction Quality Score

```
Interaction Score = weighted average of:
  - Accuracy (0-5):       Was the response factually correct?           × 3
  - Relevance (0-5):      Did it address what was actually asked?       × 3
  - Efficiency (0-5):     Minimal steps to useful response?             × 2
  - Tone Match (0-5):     Right register for the context?               × 2
  - Formatting (0-5):     Right structure for the content type?         × 2
  - Memory Quality (0-5): Was injected context helpful, not harmful?    × 2
  - Proactivity (0-5):    Appropriate level for the context?            × 2
  
  Total = weighted sum / 32  (normalised to 0-5)
```

### 8.2 Aggregate Metrics

| Metric | Calculation | Target |
|--------|-------------|--------|
| **Overall Quality Score** | Mean of all interaction scores | > 4.0 |
| **First-Response Resolution Rate** | % of interactions resolved in single exchange | > 70% |
| **Context Hit Rate** | % where memory injection was relevant | > 85% |
| **Tone Consistency** | Standard deviation of tone match scores | < 0.8 |
| **Formatting Accuracy** | % of interactions with correct format choice | > 85% |
| **Proactivity Score** | Mean proactivity level vs target level per context | > 80% of target |
| **Proactive Hit Rate** | % of proactive additions that were actually useful | > 75% |
| **Hallucination Rate** | % of interactions with confabulated content | < 2% |
| **Escalation Rate** | % of interactions that moved to Claude.ai | < 15% |

### 8.3 Scoring Approach

```
The Behaviour Analyser MUST score interactions using EVIDENCE, not impression:

1. Accuracy: Check response against available data sources
   - Calendar responses: compare to actual calendar data
   - Memory responses: compare to stored observations
   - Factual claims: verify against knowledge base
   - If unverifiable, score as 3 (neutral) and flag

2. Relevance: Compare response to detected intent
   - Did it answer the question asked?
   - Did it address the implied need behind the question?
   - Did it include extraneous information?

3. Efficiency: Count steps and tool calls
   - Minimum viable path vs actual path
   - Token usage relative to task complexity
   - Response time

4. Tone: Compare to contextual expectations
   - Time of day (morning=brief, evening=casual)
   - Channel context (#peterbot=PA mode)
   - Topic (work=structured, social=casual)
   - User's tone in the message

5. Memory Quality: Evaluate injection vs need
   - Was core context present? (always needed)
   - Was topic-relevant memory present?
   - Was any injected context misleading or stale?
   - Was relevant memory MISSING that should have been there?

6. Proactivity: Did the response go beyond literal request?
   - Flagged a related issue
   - Suggested a next step
   - Connected to a known goal/deadline
   - Offered to do something useful
```

---

## 9. Phase 5: Enhancement Recommendations

The output of analysis is a prioritised backlog of improvements:

### 9.1 Enhancement Categories

| Category | Code | Implemented By |
|----------|------|----------------|
| **Memory Tuning** | `MEM` | peterbot-mem config changes |
| **Response Template** | `RESP` | Prompt engineering / system prompt |
| **New Capability** | `CAP` | Feature development (Define Done pipeline) |
| **Proactive Feature** | `PRO` | Cron job / trigger-based action |
| **Personality Refinement** | `PERS` | Personality layer update |
| **Routing Improvement** | `ROUTE` | Tool selection logic |
| **Error Handling** | `ERR` | Code fix (Build Feature pipeline) |

### 9.2 Enhancement Record

```json
{
  "id": "ENH-001",
  "category": "PRO",
  "title": "Morning briefing - auto-send daily calendar + priority tasks",
  "description": "Chris checks calendar every weekday morning between 7:30-8:00. Currently requires explicit request. Peter should proactively send a morning brief at 7:30 on weekdays.",
  "evidence": {
    "interactions": ["INT-2026-01-28-003", "INT-2026-01-29-002", "INT-2026-01-30-004"],
    "pattern": "ROUTINE_REQUEST",
    "frequency": "5/5 weekdays in sample period",
    "averageScore": 4.2
  },
  "expectedImpact": {
    "timeSaved": "~2 min/day",
    "qualityImprovement": "Proactivity score from 0 to 5 for this interaction",
    "userSatisfaction": "High (removes friction from daily routine)"
  },
  "implementationNotes": "Requires: cron trigger in bot, calendar API pre-fetch, memory injection for context. Ties to Phase 2 proactive features.",
  "priority": "HIGH",
  "status": "PROPOSED",
  "proposedDate": "2026-02-01",
  "implementedDate": null,
  "verifiedDate": null
}
```

### 9.3 Priority Scoring for Enhancements

```
Enhancement Priority = (Frequency × 2) + (Impact × 3) + (Feasibility × 1)
                       ──────────────────────────────────────────────────────
                                               6

Where:
  Frequency (1-5):   How often this pattern occurs
  Impact (1-5):      How much improvement it would deliver
  Feasibility (1-5): How easy to implement (5 = config change, 1 = major feature)
```

---

## 10. Phase 6: Personality Calibration

A specialist analysis focused on Peter's personality consistency and calibration to Chris's preferences.

### 10.1 Personality Dimensions

| Dimension | Spectrum | Target (for Chris) |
|-----------|----------|-------------------|
| **Formality** | Casual ←→ Formal | Lean casual (3/10), professional when needed (7/10 for work emails) |
| **Verbosity** | Terse ←→ Detailed | Concise by default (3/10), detailed when asked or complex |
| **Formatting** | Plain text ←→ Heavily structured | Context-dependent — see Formatting Calibration below |
| **Humour** | Dry/None ←→ Playful | Light humour OK (4/10), never forced |
| **Assertiveness** | Passive ←→ Direct | Direct and honest (7/10), pushback welcome |
| **Empathy** | Clinical ←→ Warm | Warm but not sycophantic (6/10) |
| **Proactivity** | Reactive only ←→ Anticipatory | See Proactivity Calibration below — target varies by context |
| **Technical Depth** | Simplified ←→ Expert | Match the topic — expert for dev, accessible for life admin |

### 10.1.1 Formatting Calibration

Formatting is not a single slider — it depends on interaction type. The analyser tracks whether Peter matches the right formatting register:

| Context | Target Formatting | Score 1 (Wrong) | Score 5 (Right) |
|---------|-------------------|-----------------|-----------------|
| **Casual chat / social** | Plain prose, no headers, no bullets | Used a table to answer "how's it going?" | Natural sentence response |
| **Quick factual answer** | Plain prose, 1-3 sentences max | Formatted a simple answer with headers and bullet points | Clean single-line or short paragraph |
| **Task list / planning** | Structured — bullets or numbered list | Wall of prose for 8 action items | Clear list with actionable items |
| **Data / comparisons** | Table or structured output | Prose description of 5 products and their prices | Table with columns |
| **Technical explanation** | Code blocks + concise prose | No code formatting, just described the code | Proper code blocks with brief explanation |
| **Reports / analysis** | Headers + sections + summary | Unstructured dump | Scannable structure with clear hierarchy |
| **Email / message drafts** | Match the target recipient's expected format | Over-formatted internal Slack message | Appropriate for the medium |

**Key principle:** Formatting should be *invisible* — the user should never think "why is this formatted this way?" If they notice the formatting, it's wrong.

**Anti-patterns to detect:**
- **Over-formatting:** Using headers, bold, tables, and bullets for a simple conversational response
- **Under-formatting:** Returning a wall of text when the content clearly has structure (steps, comparisons, lists)
- **Format mismatch:** Using casual formatting for something that needs structure (e.g. a project plan) or vice versa
- **Markdown spam:** Excessive bold/italic/emoji when plain text would be cleaner
- **Inconsistent formatting:** Different formatting choices for the same type of request across sessions

**Scoring approach:**
```
For each interaction, evaluate:
1. What type of content is this? (chat, data, task, explanation, draft)
2. What formatting did Peter use?
3. Does it match the target for this content type?
4. Would a different format have been clearer or more useful?

Score 1-5 where:
  5 = Perfect format choice, invisible to user
  4 = Acceptable, minor improvement possible
  3 = Noticeable mismatch but content still usable
  2 = Wrong format, user had to work to parse it
  1 = Actively hindered understanding
```

### 10.1.2 Proactivity Calibration

Proactivity is Peter's ability to **surface relevant information, flag issues, and suggest actions without being asked**. This is the single most important dimension for evolving from "assistant that answers questions" to "PA that anticipates needs."

**Proactivity Levels:**

| Level | Description | Example |
|-------|-------------|---------|
| **0 — Reactive** | Only responds to explicit requests | "What's on my calendar?" → shows calendar, nothing else |
| **1 — Informative** | Adds relevant context to responses | Shows calendar AND mentions "you have a clash at 2pm" |
| **2 — Suggestive** | Offers next steps or recommendations | Shows calendar + clash + "want me to reschedule one?" |
| **3 — Anticipatory** | Surfaces things before asked | Morning message: "Heads up — you have back-to-back from 1-4pm today" |
| **4 — Predictive** | Acts on patterns before they become needs | "Your eBay listing for 42100 expires tomorrow — want me to relist?" |
| **5 — Autonomous** | Handles routine tasks independently with reporting | Auto-relists expiring items, sends summary: "Relisted 3 items overnight" |

**Target by context:**

| Context | Target Level | Rationale |
|---------|-------------|-----------|
| **Morning check-in** | 3-4 (Anticipatory/Predictive) | Start the day with everything surfaced |
| **Active work session** | 1-2 (Informative/Suggestive) | Don't interrupt flow, but add value |
| **Casual chat** | 0-1 (Reactive/Informative) | Don't be pushy |
| **Planning session** | 2-3 (Suggestive/Anticipatory) | Actively contribute ideas and flag conflicts |
| **Time-sensitive events** | 3-4 (Anticipatory/Predictive) | Deadlines, expiring listings, upcoming travel |
| **Routine tasks** | 4-5 (Predictive/Autonomous) | Only after pattern is established and trust earned |

**Proactivity scoring:**
```
For each interaction, evaluate:
1. Did Peter add value beyond the literal request?
2. Was there an opportunity to be proactive that was missed?
3. Was proactivity appropriate for the context (not intrusive)?
4. Was the proactive content actually useful (not noise)?

Score 0-5 where:
  5 = Anticipated a need perfectly, saved real time
  4 = Added useful unsolicited context
  3 = Responded well but missed an obvious opportunity
  2 = Purely reactive when proactivity was warranted
  1 = Was proactive but with irrelevant/unhelpful content
  0 = Missed a critical proactive opportunity (e.g. didn't flag schedule conflict)
```

**Proactivity failure types (distinct from general failures):**

| Failure | Detection | Example |
|---------|-----------|---------|
| **Missed flag** | Known conflict/deadline not surfaced | Didn't mention Japan flights unbooked with 8 weeks to go |
| **Missed connection** | Two topics discussed separately that are related | Discussed budget AND discussed Japan trip but didn't connect cost implications |
| **Missed pattern** | Repeated routine not anticipated | 5th consecutive morning calendar check, still waiting to be asked |
| **Noise proactivity** | Surfaced irrelevant information | Mentioned weather when discussing code architecture |
| **Premature autonomy** | Took action without established trust/pattern | Auto-sent an email without being asked to |

### 10.2 Calibration Tracking

For each dimension, the analyser tracks:
- **Target range** (set by Chris, adjustable)
- **Actual observed range** (from scored interactions)
- **Variance** (how consistent Peter is)
- **Context sensitivity** (does it shift appropriately?)

### 10.3 Personality Drift Detection

```
IF personality dimension observed value deviates > 2 points from target:
  → Flag as PERSONALITY_DRIFT
  → Include specific interaction examples
  → Recommend prompt adjustment

IF personality inconsistent within same conversation:
  → Flag as PERSONALITY_INCONSISTENCY
  → May indicate context confusion or memory pollution
```

---

## 11. Anti-Bias Prompts

### Analysis Integrity

```
When analysing PeterBot behaviour, you MUST:

1. NEVER rate interactions higher because the response was long
   - Length ≠ quality. A 3-word answer to a simple question is PERFECT.
   - Penalise unnecessary verbosity, don't reward it.

2. NEVER assume negative satisfaction without evidence
   - User not responding doesn't mean they're unhappy
   - Some interactions don't warrant a reply ("thanks" is closure)
   - Only infer dissatisfaction from explicit signals

3. NEVER project your own preferences onto scoring
   - Chris's preferences are defined in personality dimensions
   - If Chris likes terse responses, score terse responses highly
   - Don't penalise casual tone just because it's informal

4. NEVER recommend changes based on single interactions
   - Patterns require minimum 3 occurrences
   - Anomalies are noted but not actioned
   - One bad interaction ≠ systemic issue

5. NEVER recommend personality changes without strong evidence
   - Personality targets are human-set decisions
   - Only flag when observed behaviour consistently deviates
   - Present data, don't prescribe personality

6. ALWAYS distinguish between:
   - Peter's failure (wrong answer, bad tone, missed context)
   - Memory system's failure (wrong/missing context injection)
   - Infrastructure failure (timeout, API error, tool unavailable)
   - User's ambiguity (legitimately unclear request)
   
   These have DIFFERENT solutions. Don't conflate them.

7. ALWAYS score relative to what Peter COULD have known
   - If memory didn't have the context, Peter can't be blamed for missing it
   - If a tool wasn't available, Peter can't be blamed for not using it
   - Score against reasonable expectations, not perfect knowledge
```

---

## 12. State Management

### 12.1 State File: `docs/agents/behaviour/state.json`

```json
{
  "agent": "behaviour-analyser",
  "version": "1.0",
  "lastAnalysisDate": "2026-02-01T10:00:00Z",
  "lastAnalysisBatch": "BATCH-2026-02-01",
  "interactionsProcessed": 342,
  "interactionsUnprocessed": 48,
  "batchCursor": "INT-2026-01-31-047",
  "aggregateMetrics": {
    "overallQuality": 3.8,
    "firstResponseResolution": 0.72,
    "contextHitRate": 0.81,
    "toneConsistency": 0.9,
    "formattingAccuracy": 0.85,
    "proactivityScore": 0.42,
    "proactiveHitRate": 0.78,
    "hallucinationRate": 0.03,
    "escalationRate": 0.18
  },
  "enhancementBacklog": {
    "total": 15,
    "proposed": 8,
    "accepted": 4,
    "implemented": 2,
    "verified": 1
  },
  "personalityCalibration": {
    "lastCalibration": "2026-01-25T10:00:00Z",
    "driftAlerts": 2,
    "dimensionsInRange": 6,
    "dimensionsOutOfRange": 2,
    "contextDimensions": {
      "formatting": { "accuracy": 0.85, "trend": "stable" },
      "proactivity": { "vsTarget": 0.42, "trend": "improving" }
    }
  }
}
```

---

## 13. Behaviour Registry Schema

```json
{
  "version": "1.0",
  "lastUpdated": "2026-02-01T10:00:00Z",
  "interactions": [
    {
      "id": "INT-2026-02-01-001",
      "timestamp": "2026-02-01T10:30:00Z",
      "channel": "#peterbot",
      "intentCategory": "INFO",
      "complexityTier": "simple",
      "contextDependency": "light",
      "scores": {
        "accuracy": 5,
        "relevance": 5,
        "efficiency": 4,
        "toneMatch": 5,
        "formatting": 4,
        "memoryQuality": 3,
        "proactivity": 1,
        "overall": 4.1
      },
      "satisfactionSignal": "positive",
      "patterns": ["FAST_RESOLUTION"],
      "failurePatterns": [],
      "opportunities": [],
      "notes": ""
    }
  ],
  "patterns": {
    "successes": {
      "FAST_RESOLUTION": { "count": 45, "trend": "stable" },
      "EFFECTIVE_MEMORY": { "count": 28, "trend": "improving" }
    },
    "failures": {
      "CONTEXT_MISS": { "count": 12, "trend": "improving" },
      "OVER_VERBOSE": { "count": 8, "trend": "stable" }
    },
    "opportunities": {
      "ROUTINE_REQUEST": { "count": 5, "enhancement": "ENH-001" },
      "PREDICTABLE_NEED": { "count": 3, "enhancement": "ENH-004" }
    }
  },
  "enhancements": [
    {
      "id": "ENH-001",
      "category": "PRO",
      "title": "Morning briefing automation",
      "priority": "HIGH",
      "status": "PROPOSED",
      "evidence": ["INT-2026-01-28-003", "INT-2026-01-29-002"]
    }
  ]
}
```

---

## 14. Error Handling

| Error | Recovery | Escalation |
|-------|----------|------------|
| Interaction log unavailable | Use fallback source (Discord history) | Log gap in analysis |
| SQLite DB locked | Retry 3 times with backoff | Skip batch, log for next run |
| Too many interactions to process | Process in batches of 50, checkpoint between | Never skip, just pace |
| Scoring ambiguous (no signals) | Score as 3.0 (neutral), flag for human review | Don't guess |
| Memory injection logs missing | Score memory quality as N/A | Note data gap |
| Pattern threshold not met (<3) | Log as EMERGING, don't recommend yet | Include in next analysis |
| Registry file corrupted | Rebuild from interaction log | Alert human |

---

## 15. Output Templates

### 15.1 Daily Analysis Report

```markdown
# Behaviour Analysis Report — Daily

**Period:** {date}
**Interactions Analysed:** {count}
**Overall Quality Score:** {score}/5.0

## Quality Dashboard

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Overall Quality | 3.8 | > 4.0 | 🟡 Below |
| 1st Response Resolution | 72% | > 70% | ✅ On target |
| Context Hit Rate | 81% | > 85% | 🟡 Below |
| Tone Consistency | 0.9 σ | < 0.8 | 🟡 Above |
| Formatting Accuracy | 85% | > 85% | ✅ On target |
| Proactivity vs Target | 42% | > 80% | 🔴 Low |
| Proactive Hit Rate | 78% | > 75% | ✅ On target |
| Hallucination Rate | 3% | < 2% | 🟡 Above |

## Top Success Pattern Today
**{pattern}** — {count} instances
{Example interaction}

## Top Failure Pattern Today
**{pattern}** — {count} instances  
{Example interaction}
**Recommended fix:** {brief recommendation}

## New Enhancement Opportunities Detected
- ENH-{ID}: {title} ({priority})

## Personality Calibration
All dimensions within range ✅ / Drift detected on: {dimension} ⚠️
```

### 15.2 Enhancement Backlog Report

```markdown
# Enhancement Backlog — PeterBot

**Total Enhancements:** {count}
**Status:** {proposed} proposed | {accepted} accepted | {implemented} done

## Priority Queue

### 🔴 High Priority

#### ENH-001: Morning briefing automation
- **Category:** Proactive Feature
- **Evidence:** Routine calendar check 5/5 weekdays
- **Expected Impact:** +2 min/day saved, proactivity score boost
- **Feasibility:** Medium (requires cron trigger)
- **Status:** PROPOSED

### 🟠 Medium Priority

#### ENH-003: Response length calibration
- **Category:** Personality Refinement
- **Evidence:** 8 over-verbose interactions scored 2/5
- **Expected Impact:** Better tone consistency
- **Feasibility:** High (system prompt update)
- **Status:** PROPOSED

### Implementation via Build Pipeline
Each accepted enhancement → `/define-done` → `/feature-spec` → `/build-feature` → `/verify-done`
```

### 15.3 Personality Calibration Report

```markdown
# Personality Calibration Report

**Date:** {date}
**Interactions Sampled:** {count}

## Dimension Analysis

| Dimension | Target | Observed Mean | Observed σ | Status |
|-----------|--------|--------------|-----------|--------|
| Formality | 3/10 | 3.2 | 0.8 | ✅ |
| Verbosity | 3/10 | 4.5 | 1.2 | ⚠️ HIGH |
| Formatting | context | see below | 0.7 | ✅ |
| Humour | 4/10 | 3.8 | 0.6 | ✅ |
| Assertiveness | 7/10 | 6.5 | 0.9 | ✅ |
| Empathy | 6/10 | 5.8 | 0.7 | ✅ |
| Proactivity | context | see below | 1.5 | 🔴 LOW |
| Technical Depth | varies | varies | 0.5 | ✅ |

## Formatting Breakdown

| Context Type | Interactions | Correct Format % | Common Mistake |
|-------------|-------------|-------------------|----------------|
| Casual chat | 12 | 92% | Occasional unnecessary bold |
| Quick answers | 18 | 78% | Over-explains with bullets |
| Dev tasks | 8 | 95% | — |
| Planning | 5 | 80% | Prose when bullets needed |
| Data queries | 3 | 100% | — |

## Proactivity Breakdown

| Context | Interactions | Mean Level | Target Level | Status |
|---------|-------------|-----------|-------------|--------|
| Morning check-in | 5 | 1.2 | 3-4 | 🔴 LOW |
| Work session | 22 | 1.0 | 1-2 | ✅ |
| Casual chat | 8 | 0.5 | 0-1 | ✅ |
| Planning | 3 | 1.8 | 2-3 | 🟡 Below |
| Time-sensitive | 2 | 2.0 | 3-4 | 🔴 LOW |

## Drift Alert: Verbosity
**Observed:** 4.5/10 vs Target: 3/10
**Evidence:** 8 interactions where response exceeded expected length by >2x
**Examples:** [INT-001, INT-012, INT-034]
**Recommendation:** Tighten system prompt guidance on response length. Add instruction: "For simple questions, respond in 1-3 sentences maximum."

## Drift Alert: Initiative
**Observed:** 3.2/10 vs Target: 7/10
**Evidence:** Only 8% proactivity rate (target: 20%)
**Root Cause:** No proactive trigger system implemented yet
**Recommendation:** Prioritise ENH-001 (morning briefing) and ENH-004 (schedule conflict detection)
```

---

## 16. Handoffs

### 16.1 Behaviour Analyser → Define Done (for accepted enhancements)

```markdown
## Behaviour Analyser → Define Done

**Enhancement:** ENH-{ID}
**Title:** {title}
**Category:** {category}

### Evidence from Analysis
{Pattern details, interaction examples, quality scores}

### Expected Outcome
{What should change in Peter's behaviour}

### Verification Approach
After implementation, Behaviour Analyser will:
1. Monitor interactions in the relevant category
2. Compare quality scores before/after
3. Verify the specific improvement landed
4. Report in next analysis cycle
```

### 16.2 Behaviour Analyser → Tech-Debt (for code-level issues)

```markdown
## Behaviour Analyser → Tech-Debt

**Observation:** Bot response failures traced to code issue
**Details:** {Error patterns, stack traces if available}
**Impact on behaviour:** {How this manifests to the user}
```

### 16.3 Behaviour Analyser → peterbot-mem (for memory tuning)

```markdown
## Behaviour Analyser → Memory System

**Finding:** Context injection quality below target
**Specific Issues:**
- {Stale context being injected — examples}
- {Relevant context missing — examples}
- {Irrelevant context polluting responses — examples}

### Recommended Tuning
- Adjust TTL for {category} observations
- Modify retrieval weights for {tier}
- Add/remove from core context: {items}
```

---

## 17. Examples

### 17.1 Daily Analysis Session

```
User: /behaviour-analyse recent

Behaviour Analyser:
  [BOOT] Reading PeterBot CLAUDE.md... ✓
  [BOOT] Reading state.json... Last analysis: 2026-01-31
  [BOOT] Loading interaction log... 48 new interactions
  
  [CLASSIFY] Categorising 48 interactions...
  [CLASSIFY] INFO: 18, TASK: 12, DEV: 8, SOCIAL: 5, PLAN: 3, RECALL: 2

  [SCORE] Scoring interactions...
  [SCORE] Mean quality: 3.9/5.0

  [PATTERNS] Analysing patterns...
  [PATTERNS] Successes: FAST_RESOLUTION (15), EFFECTIVE_MEMORY (10)
  [PATTERNS] Failures: CONTEXT_MISS (3), OVER_VERBOSE (2)
  [PATTERNS] Opportunities: ROUTINE_REQUEST emerging (3 instances)

  [REPORT] Generating daily report...

  Analysis complete.
  
  Headline: Quality slightly below target (3.9 vs 4.0).
  Main issue: 3 context misses where memory should have had the answer.
  Opportunity: You check eBay sales at roughly the same time each evening — 
  Peter could proactively surface this.

  Full report: docs/agents/behaviour/reports/daily-2026-02-01.md
```

### 17.2 Failure Investigation

```
User: /behaviour-analyse failures

Behaviour Analyser:
  [BOOT] Loading context... ✓
  [FILTER] 12 interactions with negative satisfaction signals

  Top failure pattern: CONTEXT_MISS (5 instances)
  
  Example: INT-2026-01-30-023
  You: "How did the Japan booking go?"
  Peter: "I don't have information about a Japan booking. Could you tell me more?"
  
  Analysis: Memory system has Japan trip observations (April 3-19, 2026) 
  but retrieval didn't match "booking" to the trip planning context.
  Root cause: Semantic search term mismatch.
  
  Recommendation: ENH-007 — Add alias/synonym mapping to observation 
  categories so "booking", "trip", "travel", "holiday" all retrieve 
  the Japan trip observations.
  
  Priority: HIGH (trust erosion when Peter forgets known context)
```

---

## Appendix A: Chris-Specific Personality Baselines

These are starting targets based on observed Claude.ai interaction preferences. Adjustable by Chris at any time.

| Setting | Value | Rationale |
|---------|-------|-----------|
| Morning tone | Brief, functional | Chris checks in quickly before work |
| Work session tone | Structured, technical | Focused mode |
| Evening tone | Relaxed, conversational | Wind-down |
| Running/health topics | Encouraging but data-driven | Appreciates stats and targets |
| Business topics | Direct, numbers-focused | Time is money |
| Family topics | Warm, practical | Cares deeply, wants actionable help |
| Development topics | Expert peer level | Not a beginner, skip basics |

### Formatting Baselines

| Context | Default Format | Notes |
|---------|---------------|-------|
| Casual conversation | Plain prose | No headers, no bullets, no tables |
| Quick answers | 1-3 sentences | Resist the urge to over-explain |
| Development tasks | Code blocks + brief prose | Match Claude Code output style |
| Planning/strategy | Bullets or numbered steps | Structure helps, but keep it lean |
| Data/comparisons | Tables | Chris is visual and data-oriented |
| Email/message drafts | Match the medium | Slack ≠ email ≠ Discord |
| Reports | Headers + sections | But never more structure than content warrants |

### Proactivity Baselines

| Time/Context | Target Level | What to Surface |
|-------------|-------------|-----------------|
| Weekday 7:00-8:00 | Level 3-4 | Calendar, deadlines, eBay alerts, running plan |
| Weekday work hours | Level 1-2 | Context enrichment, don't interrupt flow |
| Weekday evening | Level 1 | Only surface if time-critical |
| Weekend | Level 0-1 | Respect downtime, only if asked or urgent |
| Pre-race days | Level 3 | Weather, nutrition reminders, kit prep |
| Pre-travel (Japan) | Level 4 | Booking deadlines, document checks, packing |
| eBay listing expiry | Level 4 | Always flag, suggest relist |
| PeterBot errors | Level 3 | Self-report failures, suggest fixes |

## Appendix B: Metrics Dashboard Schema

For future integration with a visual dashboard:

```json
{
  "period": "daily",
  "metrics": [
    { "name": "quality_score", "value": 3.9, "target": 4.0, "trend": "stable" },
    { "name": "resolution_rate", "value": 0.72, "target": 0.70, "trend": "improving" },
    { "name": "context_hit_rate", "value": 0.81, "target": 0.85, "trend": "declining" },
    { "name": "formatting_accuracy", "value": 0.85, "target": 0.85, "trend": "stable" },
    { "name": "proactivity_vs_target", "value": 0.42, "target": 0.80, "trend": "improving" },
    { "name": "proactive_hit_rate", "value": 0.78, "target": 0.75, "trend": "stable" },
    { "name": "hallucination_rate", "value": 0.03, "target": 0.02, "trend": "stable" }
  ],
  "topFailure": "CONTEXT_MISS",
  "topSuccess": "FAST_RESOLUTION",
  "enhancementsProposed": 2
}
```

---

**End of Behaviour Analyser Agent Specification**

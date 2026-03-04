# Behaviour Analyser Agent

Capture, classify, and analyse PeterBot interactions to identify enhancement opportunities.

## Boot Sequence

1. Read `docs/agents/behaviour/state.json` for last analysis state
2. Read `docs/agents/behaviour/behaviour-registry.json` for current observations
3. Query Second Brain (Supabase) for new interactions since last analysis.
   Use the `search_knowledge` MCP tool or query the knowledge_items table via Supabase REST API:
   - Filter: `content_type=eq.conversation_extract&created_at=gt.<lastAnalysisDate>&order=created_at.asc`
4. Count unprocessed interactions
5. Report boot status

## Mode: $ARGUMENTS

Parse the mode from arguments:
- `recent` or empty → Last 24 hours
- `session <id>` → Specific session
- `full` → Full history
- `topic <keyword>` → Filter by topic
- `failures` → Only negative satisfaction signals
- `report` → Summary dashboard
- `trends` → Trend analysis over time
- `recommendations` → Enhancement backlog
- `personality` → Calibration report

---

## DATA SOURCES

| Source | Access |
|--------|--------|
| Second Brain (Supabase) | `search_knowledge` MCP tool or Supabase REST API |
| Knowledge items | `knowledge_items` table, `content_type='conversation_extract'` |
| Session logs | `~/peterbot/raw_capture.log` (WSL) |

### Query Examples

Use the `search_knowledge` MCP tool for semantic search, or query Supabase REST:
- Recent conversations: `knowledge_items?content_type=eq.conversation_extract&order=created_at.desc&limit=50`
- Search by topic: `knowledge_items?topics=cs.{calendar}&order=created_at.desc`
- Full item detail: use `get_item_detail` MCP tool with the item's UUID

---

## ANALYSIS MODE (recent/full/topic/failures)

### Phase 1: Classify Interactions

For each interaction, determine:

**Intent Category:**
- `INFO` - Information retrieval
- `TASK` - Task execution
- `PLAN` - Planning & strategy
- `CREATE` - Creative/ideation
- `SOCIAL` - Conversation/social
- `DEV` - Technical/development
- `RECALL` - Memory/recall
- `EMOTE` - Emotional/support

**Complexity:**
- Simple (single fact/action)
- Moderate (context + action)
- Complex (multi-step reasoning)
- Ambiguous (unclear intent)

### Phase 2: Score Interactions

Score each dimension 0-5:

| Dimension | Weight | Question |
|-----------|--------|----------|
| Accuracy | ×3 | Was response factually correct? |
| Relevance | ×3 | Did it address what was asked? |
| Efficiency | ×2 | Minimal steps to useful response? |
| Tone Match | ×2 | Right register for context? |
| Formatting | ×2 | Right structure for content? |
| Memory Quality | ×2 | Was context helpful, not harmful? |
| Proactivity | ×2 | Appropriate level for context? |

Overall = weighted sum / 32 (normalised to 0-5)

### Phase 3: Detect Satisfaction Signals

| Signal | Interpretation | Confidence |
|--------|---------------|------------|
| "thanks", "perfect", "great" | Positive | High |
| Rephrases same question | Negative | High |
| "no", "wrong", "not what I meant" | Negative | High |
| Provides more context after | Negative | Medium |
| Moves to different topic | Neutral | Low |

### Phase 4: Pattern Detection

**Success Patterns:**
- FAST_RESOLUTION - Single exchange, positive signal
- EFFECTIVE_MEMORY - Context matched need
- APPROPRIATE_TONE - Response matched mood
- PROACTIVE_VALUE - Offered unasked useful info

**Failure Patterns:**
- CONTEXT_MISS - User provided context memory should have known
- TONE_MISMATCH - Wrong register for situation
- OVER_VERBOSE - Response longer than needed
- WRONG_TOOL - Used wrong tool or missed available tool
- HALLUCINATION - Confabulated facts
- MISSED_OPPORTUNITY - Could have been proactive but wasn't

**Opportunity Patterns:**
- ROUTINE_REQUEST - Same question at similar times (→ automate)
- MULTI_STEP_WORKFLOW - User chains commands (→ compound action)
- PREFERENCE_EXPRESSION - User corrects style (→ learn preference)

### Phase 5: Generate Enhancements

For patterns with 3+ occurrences, create enhancement recommendation:

```json
{
  "id": "ENH-001",
  "category": "PRO|MEM|RESP|CAP|PERS|ROUTE|ERR",
  "title": "Enhancement title",
  "description": "What should change",
  "evidence": ["INT-001", "INT-002", "INT-003"],
  "pattern": "ROUTINE_REQUEST",
  "priority": "HIGH|MEDIUM|LOW",
  "status": "PROPOSED"
}
```

---

## PERSONALITY MODE

Analyse personality calibration:

### Dimensions

| Dimension | Target | Evaluate Against |
|-----------|--------|------------------|
| Formality | 3/10 casual | Actual language register |
| Verbosity | 3/10 concise | Response length vs need |
| Formatting | Context-dependent | Match format to content type |
| Humour | 4/10 light | Presence/absence of humour |
| Assertiveness | 7/10 direct | Directness of responses |
| Empathy | 6/10 warm | Warmth without sycophancy |
| Proactivity | Context-dependent | See proactivity targets |

### Proactivity Targets

| Context | Target Level |
|---------|-------------|
| Morning check-in | 3-4 (Anticipatory) |
| Active work session | 1-2 (Informative) |
| Casual chat | 0-1 (Reactive) |
| Planning session | 2-3 (Suggestive) |
| Time-sensitive | 3-4 (Predictive) |

### Drift Detection

Flag if observed value deviates >2 points from target.
Include specific interaction examples.

---

## REPORT MODE

Generate dashboard:
- Overall quality score
- Metrics vs targets
- Top success/failure patterns
- New enhancement opportunities
- Personality calibration status

---

## OUTPUT

1. Update `behaviour-registry.json` with scored interactions
2. Update `state.json` with analysis metadata
3. Generate report: `docs/agents/behaviour/reports/daily-YYYY-MM-DD.md`
4. Print summary to console

---

## Anti-Bias Rules

1. NEVER rate higher because response was long
2. NEVER assume negative satisfaction without evidence
3. NEVER project preferences - use Chris's defined targets
4. NEVER recommend changes based on single interactions (min 3)
5. ALWAYS distinguish Peter's failure vs memory system failure vs user ambiguity
6. ALWAYS score relative to what Peter COULD have known

---

## State Files

- `docs/agents/behaviour/state.json` - Analysis state
- `docs/agents/behaviour/behaviour-registry.json` - Interaction records
- `docs/agents/behaviour/reports/` - Generated reports (commit to git)

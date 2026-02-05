# Leakage Detection Improvement Plan

**Analysis Date:** 2026-02-05
**Captures Analyzed:** 75 (past 24 hours)
**Captures with Leakage:** 69 (92%)

## Executive Summary

Current detection is catching only a tiny fraction of actual leakage. The biggest blind spot is **instruction echo** ("Current Message section") which appears in 84% of messages and is completely undetected.

## Critical Findings

| Leak Type | Occurrences | Detected | Undetected | Detection Rate |
|-----------|-------------|----------|------------|----------------|
| msg_section (instruction echo) | 63 | 0 | **63** | 0% |
| json_key (API responses) | 26 | 0 | **26** | 0% |
| json_bracket | 25 | 0 | **25** | 0% |
| Claude Code artifacts | 5-6 each | 1 | 4-5 each | ~20% |
| Paths/UUIDs | 5-6 each | 0 | **5-6** | 0% |

## Root Cause Analysis

### 1. Instruction Echo (63 instances)
**Pattern:** `Current Message section` appears at the start of many responses.

**Cause:** Memory context injection prepends instructions that Claude then references in output.

**Fix:** Add to sanitiser AGGRESSIVE_PATTERNS:
```python
'instruction_echo': re.compile(r'^Current Message section\.?$|^Message section\.?$', re.MULTILINE),
```

### 2. JSON Fragments (26 instances)
**Pattern:** Raw JSON like `{"message_id": "19c2a81a5952faa7"` appearing in output.

**Cause:** API responses being echoed, often from Gmail/Calendar/HB API calls.

**Fix:** Add patterns:
```python
'json_api_response': re.compile(r'^\s*"[a-z_]+"\s*:\s*(?:null|true|false|\d+|"[^"]*")'),
'standalone_brace': re.compile(r'^\s*[{}]\s*$'),
```

### 3. Claude Code UI Artifacts (5-6 instances each)
**Patterns found:**
- `✽ Sketching✽ (49s ✽ ↓ 1.7k tokens ✽ thinking)`
- Spinner characters at line start
- `|| echo "No g✽)`

**Current state:** Some detection exists but incomplete.

**Fix:** Expand patterns:
```python
'thinking_status': re.compile(r'(?:Sketching|Thinking|Working|Concocting).*\d+s.*tokens'),
'token_stats': re.compile(r'↓\s*\d+\.?\d*k?\s*tokens|↑\s*\d+'),
'incomplete_cmd': re.compile(r'\|\|\s*echo\s*"[^"]*\?\)?$'),
```

### 4. Internal Paths (5-6 instances each)
**Patterns found:**
- `/home/chris_hadley/.claude/projects/-home-chris-hadley-peterbot/*.jsonl`
- `pi/inventory/d035e1b3-a8c4-422d-...`

**Fix:** Add/strengthen patterns:
```python
'internal_paths': re.compile(r'/home/\w+/\.claude/|\.claude/projects/'),
'jsonl_ref': re.compile(r'\*\.jsonl|\w+\.jsonl'),
'api_internal': re.compile(r'(?:pi|hb)/\w+/[a-f0-9-]{8,}'),
```

## Implementation Plan

### Phase 1: Critical Fixes (Do Now)

**File: `domains/peterbot/response/sanitiser.py`**

Add these patterns to AGGRESSIVE_PATTERNS:

```python
# Instruction echo
'instruction_echo': re.compile(r'^(?:Current |)Message section\.?$', re.MULTILINE | re.IGNORECASE),

# JSON artifacts
'json_key_value': re.compile(r'^\s*"[a-z_]+"\s*:\s*(?:null|true|false|\d+|"[^"]*")', re.MULTILINE),
'json_standalone_brace': re.compile(r'^\s*[{}]\s*$', re.MULTILINE),
'json_bracket_only': re.compile(r'^\s*[\[\]]\s*$', re.MULTILINE),

# Claude Code UI (strengthen existing)
'thinking_extended': re.compile(r'(?:Sketching|Thinking|Working|Concocting|Processing).*(?:\d+s|\d+\.?\d*k?\s*tokens|thinking)'),
'token_arrows': re.compile(r'[↓↑]\s*\d+\.?\d*k?\s*tokens?'),
'incomplete_command': re.compile(r'\|\|\s*echo\s*"[^"]*(?:\?|\))+$'),

# Internal paths (strengthen existing)
'claude_projects': re.compile(r'\.claude/projects?/[^\s]+'),
'jsonl_glob': re.compile(r'\*\.jsonl|\w+\.jsonl\b'),
'api_uuid_path': re.compile(r'(?:pi|hb)/\w+/[a-f0-9]{8}-'),
'home_chris': re.compile(r'/home/chris_hadley/'),
```

**File: `domains/peterbot/capture_parser.py`**

Add to `_detect_echo()` artifact_patterns:
```python
'Current Message section',
'Message section.',
'"message_id":',
'"event_id":',
'"session_id":',
```

### Phase 2: Structural Improvements

**Problem:** Patterns are scattered across 3 files with inconsistent coverage.

**Solution:** Centralize pattern definitions:

```python
# domains/peterbot/response/patterns.py (new file)

LEAK_PATTERNS = {
    # Category: Instruction Echo
    'instruction': [
        (r'^(?:Current |)Message section\.?$', 'Instruction echo'),
        (r'Relevant Knowledge', 'Context marker'),
        (r'Recent Conversation', 'Context marker'),
    ],

    # Category: JSON Artifacts
    'json': [
        (r'^\s*"[a-z_]+"\s*:\s*', 'JSON key'),
        (r'^\s*[{}\[\]]\s*$', 'JSON bracket'),
    ],

    # Category: Claude Code UI
    'claude_ui': [
        (r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏✻✽]', 'Spinner'),
        (r'(?:Sketching|Thinking|Working).*\d+s', 'Thinking status'),
        (r'[↓↑]\s*\d+', 'Token count'),
        (r'[⎿├└⏵]\s*(?:Read|Write|Edit|Bash)', 'Tool marker'),
    ],

    # Category: Internal Paths
    'paths': [
        (r'\.claude/', '.claude path'),
        (r'/home/\w+/', '/home path'),
        (r'\*\.jsonl', '.jsonl glob'),
        (r'(?:pi|hb)/\w+/[a-f0-9-]{8,}', 'API with UUID'),
    ],

    # Category: Command Artifacts
    'commands': [
        (r'\|\|\s*echo', 'Pipe echo'),
        (r'&&\s*curl', 'Chained curl'),
        (r'"\s*\\$', 'Line continuation'),
        (r'curl\s+-[sSfH]', 'Curl flags'),
    ],
}
```

### Phase 3: Detection vs Sanitisation Split

**Current:** Detection (capture_parser.py) and sanitisation (sanitiser.py) have overlapping but different patterns.

**Problem:** Detection doesn't flag, so sanitiser never runs aggressive mode.

**Solution:** Align detection thresholds with actual leak patterns:

1. **Detection** should flag conservatively (high sensitivity)
2. **Sanitisation** should clean aggressively when flagged

Update `capture_parser.py` `_detect_echo()`:
- Lower the fuzzy match threshold from 0.6 to 0.5
- Add all LEAK_PATTERNS as triggers
- Return True if ANY pattern matches

### Phase 4: Testing Infrastructure

Create `tests/test_leakage_patterns.py`:

```python
KNOWN_LEAKAGE_SAMPLES = [
    # From today's analysis
    'Current Message section.\n\nAnswer: ...',
    '{"message_id": "19c2a81a5952faa7"',
    '|| echo "No g✽)',
    '/home/chris_hadley/.claude/projects/...',
    '✽ Sketching✽ (49s ✽ ↓ 1.7k tokens ✽ thinking)',
]

def test_all_known_leakage_detected():
    for sample in KNOWN_LEAKAGE_SAMPLES:
        assert detect_echo(sample) or detect_ansi(sample)

def test_all_known_leakage_sanitised():
    for sample in KNOWN_LEAKAGE_SAMPLES:
        cleaned = sanitise(sample, aggressive=True)
        assert cleaned != sample  # Something was removed
```

## Priority Order

1. **IMMEDIATE**: Add instruction_echo pattern to sanitiser (63 undetected)
2. **HIGH**: Add JSON patterns (26 undetected)
3. **MEDIUM**: Strengthen Claude Code UI patterns
4. **MEDIUM**: Add path patterns
5. **LOW**: Centralize patterns (refactoring)
6. **LOW**: Add test infrastructure

## Metrics to Track

After implementing:
- Rerun `scripts/analyze_leakage.py`
- Target: <5% undetected leakage rate (down from current ~90%)
- Monitor false positives (legitimate content being removed)

## Success Criteria

- [ ] Instruction echo ("Current Message section") detected in 100% of cases
- [ ] JSON fragments detected in 100% of cases
- [ ] Claude Code UI artifacts detected in 100% of cases
- [ ] Internal paths detected in 100% of cases
- [ ] False positive rate <1%

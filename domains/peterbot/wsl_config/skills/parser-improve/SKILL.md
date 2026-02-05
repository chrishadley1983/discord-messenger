---
name: parser-improve
description: Nightly parser improvement cycle
trigger: []
scheduled: true
schedule: "0 2 0 * * *"
conversational: false
---

# Parser Improvement Cycle

Nightly automated improvement of the response parser based on captures, fixtures, and human feedback.

## Process

1. **Review** - Analyze 24h captures, fixture failures, and pending feedback
2. **Plan** - Identify worst-performing stage and create targeted change plan
3. **Implement** - Apply scoped changes (currently disabled for safety)
4. **Validate** - Run full regression suite
5. **Commit/Rollback** - Commit if improved, rollback if regressed
6. **Report** - Post summary to #peter-heartbeat

## Guardrails

- One stage per cycle
- No architecture changes
- Zero regressions policy
- Maximum 100 lines of diff
- Human review after every 5 cycles

## Target Stages

| Stage | File | Description |
|-------|------|-------------|
| strip_ansi | parser.py | ANSI escape removal |
| extract_response | parser.py | Screen diff extraction |
| remove_echo | parser.py | Instruction echo removal |
| dedupe_lines | parser.py | Duplicate line removal |
| trim_whitespace | parser.py | Whitespace normalization |

## Output

Posts improvement report to #peter-heartbeat including:
- Review findings (captures, failures, feedback)
- Target stage and rationale
- Baseline score
- Result (committed/rolled back)

## CLI

```bash
# Run improvement cycle
python -m domains.peterbot.parser_improver run

# Run review only (no changes)
python -m domains.peterbot.parser_improver review

# Check human review status
python -m domains.peterbot.parser_improver status

# Mark review complete
python -m domains.peterbot.parser_improver mark-reviewed
```

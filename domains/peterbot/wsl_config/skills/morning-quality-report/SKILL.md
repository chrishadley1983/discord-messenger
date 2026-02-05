---
name: morning-quality-report
description: Daily parser quality and feedback summary
trigger: []
scheduled: true
schedule: "0 6 45 * * *"
conversational: false
---

# Morning Quality Report

Daily summary of parser health, format drift, and pending feedback delivered at 06:45 UK before the morning briefing.

## Data Required

- **Parser regression stats**: Pass rate, failures, regressions from last 24h
- **Format drift alerts**: Skills with format drift detected
- **Pending feedback**: Human feedback awaiting processing
- **Improvement cycle results**: What was fixed overnight

## Format

```markdown
## Parser Quality Report

**Overall Health:** [healthy|warning|critical]

### Regression Summary
- Pass rate: X/Y (Z%)
- Regressions: N (skills affected)
- Improvements: N

### Format Drift
- [skill-name]: [drift description]

### Pending Feedback
- X items awaiting review
- High priority: Y

### Last Improvement Cycle
- Ran at: [time]
- Changes: [summary]
```

## Thresholds

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| Pass rate | >= 95% | >= 85% | < 85% |
| Regressions | 0 | 1-2 | > 2 |
| Drift alerts | 0 | 1-2 | > 2 |
| Pending feedback | < 5 | 5-10 | > 10 |

## Notes

- Report is brief - meant to be scanned quickly
- Links to detailed logs if issues found
- Suppressed if everything is healthy (optional setting)

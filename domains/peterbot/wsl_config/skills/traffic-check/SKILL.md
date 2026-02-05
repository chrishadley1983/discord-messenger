# Traffic Check

## Purpose
Check current traffic conditions for the school run.

## Triggers
- "traffic", "how's the traffic", "is there traffic"
- "school run traffic", "how long to school"
- "should I leave now"

## Schedule
- Part of `school-run` skill (07:30 UK)
- Part of `school-pickup` skill (14:30 UK)

## Data Source
Hadley API: `curl http://172.19.64.1:8100/traffic/school`

## Output Format

**Quick Check:**
```
🚗 **Traffic to School**
⏱️ {duration_mins} mins (usually {typical_mins})
{traffic_icon} {traffic_level} traffic

Leave by {leave_time} to arrive on time.
```

**Traffic Indicators:**
- 🟢 Light (at or below typical)
- 🟡 Moderate (+1-5 mins)
- 🔴 Heavy (+5-15 mins)
- ⚠️ Severe (+15 mins)

## Guidelines
- **Never show raw JSON** - only present the formatted human-readable output
- Compare to typical time, not just absolute
- Include departure time recommendation
- Note if there are significant delays

## Conversational
Yes - follow-ups:
- "What about the back roads?"
- "When should I leave?"

# Ring Doorbell Status

## Purpose
Check Ring doorbell status and recent activity.

## Triggers
- "ring doorbell", "is anyone at the door", "doorbell status"
- "who rang the doorbell", "any visitors", "door activity"
- "ring battery", "doorbell battery"

## Schedule
None (conversational only)

## Data Source
Hadley API: `curl http://172.19.64.1:8100/ring/status`

## Output Format

**Online with recent activity:**
```
🔔 **Ring Doorbell**
Status: Online
🔋 Battery: {battery_level}%

**Recent Activity:**
- {time}: {type} ({answered/missed})
```

**Offline:**
```
🔔 **Ring Doorbell**
⚠️ Status: Offline
Last battery: {battery_level}%
```

**No activity:**
```
🔔 **Ring Doorbell**
Status: Online
No recent activity
```

## Guidelines
- **Never show raw JSON** - only present the formatted human-readable output
- Include battery level if available
- Show up to 3 most recent events
- Note if doorbell is offline

## Conversational
Yes - follow-ups:
- "Who was it?"
- "Was it the postman?"

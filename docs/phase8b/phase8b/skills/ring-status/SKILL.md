# Ring Status

## Purpose
Check Ring doorbell and security camera status, recent events, and alerts.

## Triggers
- "ring", "doorbell", "front door"
- "any visitors", "who came to the door"
- "check the cameras", "security"
- "any motion", "any alerts"
- "is anyone at the door"

## Schedule
None (conversational + alert-driven)

## Data Source
Ring API (unofficial - ring-client-api)
- Auth: Email/password + 2FA token
- Note: Ring doesn't have official API, use community library

## Pre-fetcher
`get_ring_status_data()` - fetches:
- Device status (online/offline, battery level)
- Recent events (last 24h): motion, dings, answered/missed
- Last snapshot/thumbnail (if available)

## Output Format

**Status Check:**
```
🔔 **Ring Doorbell**
📶 Status: Online
🔋 Battery: 78%

**Recent Activity (last 24h):**
• 14:32 - Motion detected (front garden)
• 11:15 - Doorbell ring (answered)
• 09:45 - Motion detected (delivery van)
• 08:20 - Doorbell ring (missed)

No alerts requiring attention.
```

**When Someone at Door:**
```
🔔 **Doorbell Ring!**
⏰ Just now
📹 Live view available in Ring app

Recent context: Motion detected 30 seconds before ring.
```

**Alert Summary:**
```
🔔 **4 Ring Events Today**

🚶 Motion: 3 events
🔔 Doorbell: 1 ring (answered)

Nothing unusual - mostly delivery activity.
```

## Event Types
- `ding` - Doorbell pressed
- `motion` - Motion detected
- `on_demand` - Live view accessed
- `answered` - Call answered (via app or Alexa)

## Guidelines
- Focus on notable events, not every motion
- Note patterns ("delivery window 10-11am")
- Battery warning if <20%
- Don't show video/images in Discord (privacy) - just describe

## Conversational
Yes - follow-ups:
- "What time was the delivery?"
- "Show me the last motion event"
- "Any activity while we were out?"
- "Is the doorbell battery OK?"

## Privacy Notes
- Ring footage is private - only describe, don't share
- Peter should NOT proactively share Ring events unless asked
- For scheduled alerts, only report if unusual activity

## Integration with Other Skills
- "Was there a delivery today?" → Ring (motion/ding) + Gmail (delivery confirmation)
- "Who was at the door when I was out?" → Ring events during calendar busy time

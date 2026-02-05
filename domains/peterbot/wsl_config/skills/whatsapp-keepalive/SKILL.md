---
name: whatsapp-keepalive
description: Keep WhatsApp sandbox session alive
trigger: []
scheduled: true
conversational: false
channel: #peterbot
---

# WhatsApp Keepalive

## Purpose

Sends a ping to keep the Twilio WhatsApp sandbox session active.

**Schedule:** Twice daily at 06:00 and 22:00 UK (max 16 hours between pings, well within 72-hour sandbox expiry).

**Recipient:** Chris only (+447855620978) - Abby receives school run messages but not keepalives.

## Pre-fetched Data

The data fetcher sends the WhatsApp message directly.

**Success:**
```json
{
  "sent": true,
  "recipient": "+447855620978",
  "sid": "SM..."
}
```

**Failure:**
```json
{
  "sent": false,
  "error": "Error message here"
}
```

## Output Rules

**If `sent: true`:**
Return `NO_REPLY` - the WhatsApp was sent successfully.

**If `sent: false`:**
Report the error so it's visible:

```
⚠️ **WhatsApp Keepalive Failed**

Error: {error from pre-fetched data}

The sandbox may expire. To reactivate:
1. Send "join <phrase>" to +1 415 523 8886
2. Check Twilio console for current join phrase
```

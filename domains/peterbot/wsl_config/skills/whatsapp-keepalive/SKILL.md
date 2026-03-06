---
name: whatsapp-health
description: Check Evolution API WhatsApp connection health
trigger: []
scheduled: true
conversational: false
channel: #peter-heartbeat
---

# WhatsApp Health Check

## Purpose

Checks that the Evolution API WhatsApp instance is connected and ready to send/receive messages.

**Schedule:** Twice daily at 08:00 and 20:00 UK.

## Pre-fetched Data

The data fetcher checks the Evolution API connection state.

**Connected:**
```json
{
  "connected": true,
  "state": "open"
}
```

**Disconnected:**
```json
{
  "connected": false,
  "state": "close"
}
```

## Output Rules

**If `connected: true`:**
Return `NO_REPLY` - everything is fine.

**If `connected: false`:**
Report the issue:

```
WhatsApp Disconnected

Evolution API instance state: {state}

To reconnect:
1. Run: python scripts/whatsapp/evolution_setup.py
2. Scan the QR code with the second phone (+447784072956)
```

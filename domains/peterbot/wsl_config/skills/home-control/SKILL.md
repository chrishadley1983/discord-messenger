---
name: home-control
description: Control Pi-connected home devices — smart plug, the kitchen screen, and streaming/TV
trigger:
  - "turn the plug on"
  - "turn the plug off"
  - "is the plug on"
  - "switch on the {device}"
  - "put netflix on"
  - "put youtube on the screen"
  - "close netflix"
  - "wake the screen"
  - "turn the kitchen screen on"
scheduled: false
conversational: true
---

# Home Control (smart plug · screen · TV)

## Purpose

Read and control the devices wired to the kitchen dashboard Pi. Base
`http://172.19.64.1:8100`. Mutating calls need `-H "x-api-key: $HADLEY_AUTH_KEY"`.

## Smart plug (Sonoff S60ZBTPG)

| Want | Call |
|------|------|
| Is the plug on? | `GET /ihd/plug` → `{state:"ON"|"OFF", linkQuality}` |
| Turn it on/off | `POST /ihd/plug` body `{"state":"ON"}` or `{"state":"OFF"}` (x-api-key) |

After switching, confirm the returned `state`. Don't claim success without it.

## Streaming / TV on the kitchen screen

`POST /ihd/media` (x-api-key), body `{"action":"launch","app":"netflix"}` —
`app` is `netflix`, `youtube`, or `nowtv`. To stop: `{"action":"close"}`.
This launches/kills a Chromium kiosk on the Pi's screen. Examples: "put Netflix
on" → launch netflix; "turn the telly off" → close.

## Screen / display

- `GET /ihd/screen` → `{state, idle_seconds, display_on, night_mode}`.
- `POST /ihd/screen/wake` (x-api-key) — wake a dimmed display.

## If unavailable

These endpoints return 502 when the Pi dashboard (`192.168.0.110:3000`) is
offline (it drops off WiFi sometimes — same Pi as the sensors). Say so plainly;
don't pretend the device switched.

## Response style

Short + confirm state: "Plug's on now." / "Netflix is up on the kitchen screen." /
"Plug's already off." Warn before turning things off if it's ambiguous what's plugged in.

---
name: dad-jokes
description: Read or add the "Peter says..." dad jokes shown on the kids' dashboard
trigger:
  - "tell me a joke"
  - "what's today's joke"
  - "dad joke"
  - "add a joke"
  - "put a joke on the screen"
  - "tell the kids a joke"
scheduled: false
conversational: true
---

# Dad Jokes ("Peter says...")

## Purpose

The kids' dashboard shows a "Peter says..." dad-joke card. This skill lets Peter
read today's jokes or add new ones that appear on the screen. Base
`http://172.19.64.1:8100`. Adding needs `-H "x-api-key: $HADLEY_AUTH_KEY"`.

## Endpoints

| Want | Call |
|------|------|
| Today's jokes | `GET /ihd/jokes` → `{jokes:[{text}], count, date}` |
| Add a joke to the screen | `POST /ihd/jokes` body `{"text":"Why did the scarecrow win an award? He was outstanding in his field."}` (x-api-key) |

## Behaviour

- "Tell me a joke" → if the screen already has jokes today, share one; otherwise make a
  genuinely groan-worthy, kid-safe dad joke AND optionally POST it so it shows on the screen.
- "Put a joke on the screen" / "tell the kids a joke" → POST a fresh one, then confirm it's up.
- Keep jokes clean and silly — these are for Max and Emmie.

## If unavailable

502 = the Pi dashboard (`192.168.0.110:3000`) is offline. Still tell the joke in chat; just
note it couldn't go on the screen.

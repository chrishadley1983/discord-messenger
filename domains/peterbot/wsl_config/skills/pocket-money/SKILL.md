---
name: pocket-money
description: Check and adjust the kids' pocket money balances (Emmie & Max), conversationally
trigger:
  - "how much pocket money does {child} have"
  - "what's {child}'s balance"
  - "pocket money balance"
  - "add {amount} to {child}"
  - "give {child} {amount}"
  - "take {amount} off {child}"
  - "{child}'s pocket money"
  - "pocket money grid"
  - "what did the kids earn this week"
scheduled: false
conversational: true
---

# Pocket Money (Emmie & Max)

## Purpose

Check balances, log credits/debits, and read the weekly chore grid for the kids.
Data lives on the dashboard Pi; **all amounts are in PENCE**. Base
`http://172.19.64.1:8100`. Mutating calls need `-H "x-api-key: $HADLEY_AUTH_KEY"`.

The Sunday *calculation* job is the `pocket-money-weekly` skill — this skill is
the everyday conversational view + ad-hoc adjustments.

## Endpoints

| Want | Call |
|------|------|
| Both balances (quick) | `GET /ihd/pocket-money` → `{summary, emmie:{balance,formatted}, max:{...}}` |
| Balances + recent transactions | `GET /ihd/pocket-money?full=true` |
| Add / remove money | `POST /ihd/pocket-money` body `{"child":"max","amount_pence":200,"description":"helping in the garden"}` (x-api-key) |
| This week's chore grid | `GET /ihd/pocket-money/grid` |
| Computed weekly total from the grid | `GET /ihd/pocket-money/calculate` → `{message, emmie, max}` |

`child` must be `emmie` or `max`. `amount_pence`: **positive = credit, negative = debit**.
£2 = `200`. After a POST, the response has the new `balance` (pence) — quote it back.

## Rules

- **Never say "added"/"done" without the POST succeeding** and the returned `balance` changing. If it fails, say so.
- Confirm the child + amount before debiting (taking money off): "Take £1 off Emmie — confirm?" unless Chris was explicit.
- Convert pence → £ when talking to Chris (e.g. balance 3700 → "£37.00").

## If unavailable

502 = the Pi dashboard (`192.168.0.110:3000`) is offline. Report it; don't guess balances.

## Response style

"Max has £37.00, Emmie £34.00." / "Done — added £2 to Max, he's now on £39.00." Keep it short.

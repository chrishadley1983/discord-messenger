---
name: osaka-mint-check
description: Checks Osaka Mint Bureau cherry blossom reservation status
trigger:
  - "osaka mint"
  - "cherry blossom registration"
scheduled: true
conversational: false
channel: #peterbot+WhatsApp:chris
---

# Osaka Mint Cherry Blossom Registration Check

## Purpose

Monitors the Osaka Mint Bureau website for 2026 cherry blossom (Sakura no Toorinuke) pre-registration opening. Alerts Chris when bookings become available.

## Target Dates

- **Viewing period**: April 9-15, 2026
- **Chris in Osaka**: April 6-10, so can attend April 9 or 10
- **Registration expected**: Could open any day from mid-March 2026

## Checking Process

1. Search for latest Osaka Mint cherry blossom 2026 registration news
2. Check if booking/pre-registration is open
3. If open: Alert immediately with link and instructions
4. If not open: Report "Not yet open" (this triggers NO_REPLY on normal schedule)

## Web Search Query

```
"Osaka Mint" cherry blossom 2026 reservation registration open site:mint.go.jp OR site:japancheapo.com OR site:japan-guide.com
```

## Output Format

### If registration IS open:

```
🌸 **OSAKA MINT REGISTRATION OPEN!**

Bookings now available for April 9-15, 2026.
You're in Osaka April 6-10 — **book April 9 or 10!**

📋 **Register here:** [mint.go.jp link]

Notes:
- One registration covers up to 5 people (whole family)
- Weekday slots less crowded than weekend

⏰ Act fast — popular slots fill quickly!
```

### If registration NOT YET open:

```
🌸 Checked Osaka Mint — registration not open yet. Will check again tomorrow.
```

## Rules

- Check daily until registration confirmed open
- When open, send ONE alert then disable the scheduled job
- Include direct link to registration page
- Remind about April 9/10 being ideal dates (weekday, less crowded)

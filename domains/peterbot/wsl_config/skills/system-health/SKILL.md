---
name: system-health
description: Daily operations report covering all scheduled jobs across Discord-Messenger and Hadley Bricks
trigger:
  - "system health"
  - "job status"
  - "what failed"
  - "ops report"
  - "job failures"
scheduled: true
conversational: true
channel: "#alerts"
---

# System Health

## Purpose

Daily operations report (06:50 UK) that checks ALL scheduled processes across both systems. Also available on-demand when Chris asks about system health or job failures.

## Pre-fetched Data

Data injected by the scheduler before execution:
- `data.system_health`: Full health summary from `GET http://172.19.64.1:8100/jobs/health`

## Data Source

If pre-fetched data is not available, fetch it directly:
```
curl -s "http://172.19.64.1:8100/jobs/health"
```

This returns a JSON object with:
- `dm` — Discord-Messenger job stats (from job_history.db)
- `hb` — Hadley Bricks job stats (from Supabase job_execution_history)
- Both include: total, success, errors, success_rate, failures[], per_job[]

## Output Format

**All green (NO_REPLY):**
If both systems have 0 errors in the last 24 hours, return just: `NO_REPLY`

**Issues found:**
```
⚙️ **System Health** — {date}

🟢 **Discord-Messenger**: {success_rate}% ({success}/{total} jobs)
🔴 **Hadley Bricks**: {success_rate}% ({success}/{total} jobs)
  ❌ full-sync — failed at 07:45: Connection timeout
  ❌ amazon-pricing — failed at 02:15: Keepa rate limit

💡 **Action**: [brief recommendation if pattern is clear]
```

**Status indicators:**
- 🟢 100% success rate, no issues
- 🟡 95-99% success rate, minor issues
- 🔴 Below 95% success rate, or any critical job failed

**Critical jobs** (always flag if failed, even once):
- DM: energy_daily_sync, incremental_seed, school_daily_sync
- HB: full-sync, amazon-pricing, ebay-pricing, email-purchases

## Rules

- Keep under 2000 chars — this goes to #alerts
- Only show detail on failures, not successes
- If a job has been failing repeatedly (>2 times), flag it as "recurring"
- If HB API is unreachable, report that as an issue itself
- Include the time window: "Last 24 hours" for scheduled, or custom if asked
- When conversational, provide more detail if asked ("what's been failing?")
- `NO_REPLY` when everything is healthy (don't spam #alerts with "all good")

## Examples

**Scheduled (all green):**
```
NO_REPLY
```

**Scheduled (issues):**
```
⚙️ **System Health** — Mon 10 Mar

🟢 **Discord-Messenger**: 100% (47/47 jobs)
🔴 **Hadley Bricks**: 92% (23/25 jobs)
  ❌ amazon-pricing — failed at 02:15 (recurring, 3rd day)
  ❌ email-purchases — failed at 02:17: IMAP timeout

💡 Amazon pricing has failed 3 days running — likely a Keepa issue
```

**Conversational:**
```
Chris: "what's been failing?"
Peter: Here's the last 24h breakdown...
[more detailed per-job table with success rates]
```

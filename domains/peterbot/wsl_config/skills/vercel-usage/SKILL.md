---
name: vercel-usage
description: Daily Vercel usage check — track limits, trends, and flag risks before projects get paused
trigger:
  - "vercel usage"
  - "vercel limits"
  - "vercel status"
scheduled: true
conversational: true
channel: #api-costs
---

# Vercel Usage Monitor

## Purpose

Daily check of Vercel usage for **chrishadley1983s-projects** (Hobby/free tier). The main risk is exceeding free tier limits which causes **automatic project pausing**. Primary concerns are **Fluid Active CPU** and **Fluid Provisioned Memory**.

## Context

- **Project:** hadley-bricks-inventory-management (Next.js app)
- **Team:** chrishadley1983s-projects
- **Plan:** Hobby (free tier)
- **Dashboard:** `https://vercel.com/chrishadley1983s-projects/~/usage`
- **Metrics are ROLLING 30-DAY totals** (not calendar-month). They lag changes by up to 30 days: after a load reduction the number keeps reading high until the heavy days roll out of the window. Always report the slope (rising/falling vs previous days), not just the level.

### Key Limits (Hobby Tier)

| Metric key | Limit | Notes |
|------------|-------|-------|
| `vercel_fluid_active_cpu` | 14,400 seconds (4h) | CRITICAL — breached Jun–Jul 2026, falling since 1 Jul |
| `vercel_fluid_provisioned_memory` | 360 GB-Hrs | HIGH — watch burn rate |
| `vercel_function_invocations` | 1,000,000 | Low |
| `vercel_fast_data_transfer` | 100 GB | Low |
| `vercel_edge_requests` | 1,000,000 | Low |

### Optimisation history (why CPU was over, and what was already done)

- **12 Jun 2026:** 6 heavy cron jobs moved from GCP-→Vercel to the local bot (`jobs/hb_crons.py`).
- **26 Jun 2026:** client polling slowed + 6 GCP schedules cut; ebay-pricing/auctions/bin-partout/keepa moved to local Windows Scheduled Tasks. See HB repo `docs/vercel-cpu-reduction-2026-06-26.md`.
- **10 Jul 2026:** `amazon-pricing` (last big Vercel cron) moved to local Windows task `HadleyBricks-Amazon-Pricing-Local`; GCP `amazon-pricing-sync` paused.
- Rolling-30d CPU peaked 201% (26 Jun) and has fallen daily since 1 Jul. The window is fully post-reduction ~26 Jul — if still >14,400s then, the next candidate is `spapi-buybox-overlay` (~80 wall-s/day). **Do NOT recommend "move heavy crons off Vercel" as a new idea — it is done; only reference the remaining candidates above.**

## Data Collection

### Step 1: Query vercel_usage_history in Supabase (PRIMARY SOURCE)

The HB cron `/api/cron/vercel-usage` (06:00 UTC daily) pulls the Vercel API and stores every metric here. Use the supabase MCP (project `modjoikyuhqzouxvieua`):

```sql
-- Today's snapshot
SELECT key, value, unit FROM vercel_usage_history
WHERE scrape_date = (SELECT max(scrape_date) FROM vercel_usage_history)
ORDER BY key;

-- 14-day trend for the critical metrics
SELECT scrape_date, key, value FROM vercel_usage_history
WHERE key IN ('vercel_fluid_active_cpu','vercel_fluid_provisioned_memory')
  AND scrape_date >= CURRENT_DATE - 14
ORDER BY scrape_date, key;
```

If `max(scrape_date)` is older than yesterday, the HB cron has stopped — flag that as its own alert.

### Step 2: Check Gmail for Vercel native alerts (SUPPLEMENTARY)

```
from:notifications@vercel.com newer_than:7d
```

These fire at 50% and 100% thresholds. Note which metrics triggered and when.

### Step 3: Usage report email (SUPPLEMENTARY)

The custom report from `onboarding@resend.dev` (subject "Vercel usage") duplicates the table data. It is delivered to **chris@hadleybricks.co.uk only** (Resend's unverified test sender can only deliver to the account owner — a second gmail recipient silently killed this email for weeks until PR #557, 10 Jul 2026). If your Gmail access is the personal account, you may not see it — that is expected, not data loss; the Supabase table is authoritative.

### Step 4: Save today's snapshot to Second Brain (optional, for cross-referencing)

```
POST /brain/save
{
  "source": "Vercel Usage Snapshot - YYYY-MM-DD\nFluid Active CPU: X s / 14400 = XX.X% (rolling 30d)\nFluid Provisioned Memory: XXX.X GB-Hrs / 360 = XX.X%\nFunction Invocations: XX,XXX / 1,000,000\nFast Data Transfer: X.X GB / 100 GB\n\nSlope: CPU falling/rising X s/day over last 7d\nNotes: <changes, optimisation impact>",
  "note": "Vercel daily usage snapshot",
  "tags": "vercel,usage,monitoring,snapshot"
}
```

Trend comparison should come from the `vercel_usage_history` table (Step 1), not Second Brain search.

## Analysis

Calculate and report:

1. **Current usage** — value and % of limit for each key metric
2. **Slope** — change per day over the last 7 days from the trend query (falling = reductions rolling in; rising = new burn)
3. **Projected clear/breach date** — extrapolate the 7-day slope
4. **Anomalies** — any single-day jump (like the 2–3 Jul amazon-pricing timeout storm) worth calling out

## Output Format

```
**Vercel Usage** — DD Mon (rolling 30d)

🔴 Fluid CPU: Xh Xm / 4h (XXX%) — falling ~Xs/day, projected under limit ~DD Mon
🟡 Fluid Memory: XXX.X / 360 GB-Hrs (XX.X%)
🟢 Functions: XX,XXX / 1M (X.X%)
🟢 Bandwidth: X.X / 100 GB (X.X%)

Trend: [improving/stable/worsening] vs last 7 days
[anomalies / recommendations if needed]
```

### Status indicators:

- 🟢 GREEN: Under 50%
- 🟡 AMBER: 50-75% — include burn rate and projection
- 🔴 RED: Over 75% or already exceeded — but if the slope is FALLING, say so; over-limit-and-falling is recovering, not an emergency
- For any metric over 100%: flag as **OVER LIMIT** and note consequences

### If a metric is genuinely rising toward its limit:

1. **Fluid Active CPU:** the remaining Vercel workloads are `spapi-buybox-overlay` (migration candidate, ~80 wall-s/day), ~25 small GCP pollers/dailies, page/API traffic, and the keepa webhook. Name the specific candidate, don't say "move crons off Vercel" generically.
2. **Fluid Provisioned Memory:** consolidate cron schedules so fewer routes stay warm.
3. **Last resort:** Vercel Pro ($20/mo).

## Rules

- The `vercel_usage_history` Supabase table is the PRIMARY data source — always query it first
- Vercel native alert emails are supplementary context
- Metrics are rolling 30-day: always pair the level with the slope
- If the table has no row for today or yesterday, report the HB vercel-usage cron as broken
- If no data is available at all, say so clearly — don't fabricate numbers
- Keep output concise for #api-costs channel
- On conversational trigger, include more detail and recommendations

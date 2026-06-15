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

Daily check of Vercel usage for **chrishadley1983s-projects** (Hobby/free tier). The main risk is exceeding free tier limits which causes **automatic project pausing**. Primary concerns are **Fluid Active CPU** (already breached) and **Fluid Provisioned Memory** (on track to breach).

## Context

- **Project:** hadley-bricks-inventory-management (Next.js app with Vercel Crons)
- **Team:** chrishadley1983s-projects
- **Plan:** Hobby (free tier)
- **Dashboard:** `https://vercel.com/chrishadley1983s-projects/~/usage`
- **Billing period:** Rolling monthly — currently 13 May – 12 Jun 2026 (NOT 1st of month)
- **Usage report email:** Sent from `onboarding@resend.dev` with subject containing "Vercel usage" — this is a custom report from the hadley-bricks app with full metric breakdown

### Key Limits (Hobby Tier)

| Metric | Limit | Risk Level |
|--------|-------|------------|
| Fluid Provisioned Memory | 360 GB-Hrs | HIGH — main cost driver |
| Fluid Active CPU | 4h 0m | CRITICAL — already exceeded |
| Function Invocations | 1,000,000 | Low |
| Fast Data Transfer | 100 GB | Low |
| Build Minutes | 100h | Low |

### What is Fluid Compute?

Vercel Fluid replaces traditional serverless with always-warm instances. Two meters:
- **Provisioned Memory (GB Hrs):** Memory reserved while instances exist (even idle). Cron jobs keeping instances warm burns this even between invocations.
- **Active CPU (vCPU Hrs):** CPU time when actively processing requests. Limit is only 4 hours on Hobby.

### Optimisation History

- **2026-05-21:** PR #407 reduced Fluid Active CPU for `amazon-sync` and `full-sync` crons
- **Note at bottom of report:** "Cron jobs have been migrated to GCP Cloud Scheduler to reduce Function Invocations"

## Data Collection

### Step 1: Check Gmail for the Hadley Bricks usage report (PRIMARY SOURCE)

This is the best data source — a custom report with all metrics, percentages, and RAG status.
The report is sent to both chris@hadleybricks.co.uk and chrishadley1983@gmail.com.

```
from:onboarding@resend.dev subject:"Vercel usage" newer_than:7d
```

Get the full thread content — it contains a table with every metric, current value, limit, used %, and status (GREEN/AMBER/RED).

### Step 2: Check Gmail for Vercel native alerts (SUPPLEMENTARY)

```
from:notifications@vercel.com newer_than:7d
```

These fire at 50% and 100% thresholds. Note which metrics triggered and when.

### Step 3: Search Second Brain for previous snapshots

```
search_knowledge("vercel usage snapshot")
```

Compare today's numbers to the last snapshot to identify trends (burn rate change, impact of optimisations).

### Step 4: Save today's snapshot

Save a snapshot to Second Brain for trend tracking:
```
POST /brain/save
{
  "source": "Vercel Usage Snapshot - YYYY-MM-DD\nBilling period: DD Mon - DD Mon YYYY\nDays elapsed: N of M\n\nFluid Provisioned Memory: XXX.X GB-Hrs / 360 = XX.X%\nFluid Active CPU: Xh Xm / 4h = XX.X%\nFunction Invocations: XX,XXX / 1,000,000 = X.X%\nFast Data Transfer: X.X GB / 100 GB = X.X%\n\nMemory burn rate: X.X%/day → projected: XX%\nCPU burn rate: X.X%/day → projected: XX%\n\nNotes: <changes, optimisation impact, recommendations>",
  "note": "Vercel daily usage snapshot",
  "tags": "vercel,usage,monitoring,snapshot"
}
```

## Analysis

Calculate and report:

1. **Current usage** — actual values and % for each key metric
2. **Burn rate** — % per day = current% / days elapsed in billing period
3. **Projected period-end** — burn rate * total days in billing period
4. **Days until limit** — (100% - current%) / daily burn rate
5. **Trend** — compare to yesterday's snapshot: improving, stable, or worsening
6. **Optimisation impact** — has the burn rate decreased since PR #407 or other changes?

## Output Format

```
**Vercel Usage** — DD Mon (day N of billing cycle)

🔴 Fluid CPU: Xh Xm / 4h (XXX.X%) — OVER LIMIT
🟡 Fluid Memory: XXX.X / 360 GB-Hrs (XX.X%, burn ~X.X%/day, proj ~XX% EOP)
🟢 Functions: XX,XXX / 1M (X.X%)
🟢 Bandwidth: X.X / 100 GB (X.X%)

Trend: [improving/stable/worsening] vs yesterday
Days until memory limit: ~NN

[recommendations if needed]
```

### Status indicators:

- 🟢 GREEN: Under 50%
- 🟡 AMBER: 50-75% — include burn rate and projection
- 🔴 RED: Over 75% or already exceeded — recommend immediate action
- For any metric already over 100%: flag as **OVER LIMIT** and note consequences

### If approaching or exceeding limits, suggest mitigations:

1. **Fluid Active CPU (most urgent):** Reduce cron frequency, lower `maxDuration`, move heavy crons to Hadley API/GCP Cloud Scheduler
2. **Fluid Provisioned Memory:** Reduce number of warm instances, consolidate cron schedules so fewer routes stay warm, consider `memory` config in vercel.json
3. **General:** Review which API routes use Node vs Edge Runtime, batch cron work into fewer invocations
4. **Last resort:** Upgrade to Pro ($20/mo) for higher limits and pay-as-you-go overflow

## Rules

- The Hadley Bricks usage report email (from resend.dev) is the PRIMARY data source — always check this first
- Vercel native alert emails are supplementary context
- Save a snapshot every run for trend tracking
- If no data is available (no emails found), say so clearly — don't fabricate numbers
- If any metric is RED or over 100%, flag it prominently
- Keep output concise for #api-costs channel
- On conversational trigger, include more detail and recommendations

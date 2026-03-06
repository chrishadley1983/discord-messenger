---
name: security-monitor
description: Proactive security monitoring across Supabase, Google, and Vercel — flags issues and offers to help
trigger:
  - "security check"
  - "any security issues"
  - "security alerts"
  - "check security"
  - "security status"
scheduled: true
conversational: true
channel: "#alerts"
whatsapp: false
---

# Security Monitor

## Purpose

Proactive security watchdog that runs every 4 hours. Checks Supabase, Google, and Vercel for security issues, flags them to Chris, and offers actionable next steps.

## Data Sources

### 1. Supabase — Security Vulnerability Emails

Search Gmail for recent Supabase security emails:

```bash
curl -s "http://172.19.64.1:8100/gmail/search?q=from:noreply@supabase.com+subject:security+newer_than:7d&limit=3"
```

Then fetch full body of the most recent:

```bash
curl -s "http://172.19.64.1:8100/gmail/get?id={message_id}"
```

Extract: project name, number of errors, link to security advisor.

### 2. Supabase — Auth Audit (Login Monitoring)

Query auth admin API for recent users and sign-in activity:

```bash
curl -s "https://modjoikyuhqzouxvieua.supabase.co/auth/v1/admin/users?page=1&per_page=20" \
  -H "apikey: ${SUPABASE_KEY}" \
  -H "Authorization: Bearer ${SUPABASE_KEY}"
```

Check for:
- **New user registrations** since last check (unexpected accounts)
- **Sign-ins from unknown emails** (only expected: chris@hadleybricks.co.uk, chrishadley1983@gmail.com, tomfreeman1983@gmail.com, contact@gainaiservices.co.uk)
- **Users who haven't signed in for 30+ days** (stale accounts)

### 3. Google — Security Alert Emails

Search Gmail for recent Google security alerts:

```bash
curl -s "http://172.19.64.1:8100/gmail/search?q=from:no-reply@accounts.google.com+subject:security+newer_than:1d&limit=10"
```

Check for:
- **New sign-ins** — flag unfamiliar devices/locations
- **App passwords created** — flag if unexpected
- **OAuth access granted** — flag unknown apps
- **Password changes** — always flag
- **Recovery changes** — always flag (high severity)

### 4. eBay — Password Resets & Security Codes

Search Gmail:

```bash
curl -s "http://172.19.64.1:8100/gmail/search?q=(from:ebay@ebay.com+OR+from:no.reply@ebay.com)+(subject:security+OR+subject:password)+newer_than:1d&limit=10"
```

Check for:
- **Password resets** you didn't initiate (high frequency = possible brute force)
- **Security codes** — multiple in a short window suggests someone trying to access the account
- **Pattern**: 3+ security codes in one day = RED alert

### 5. Shopify — Suspicious Login

Search Gmail:

```bash
curl -s "http://172.19.64.1:8100/gmail/search?q=from:mailer@shopify.com+(subject:suspicious+OR+subject:security)+newer_than:1d&limit=5"
```

### 6. Amazon — Password Recovery

Search Gmail:

```bash
curl -s "http://172.19.64.1:8100/gmail/search?q=from:account-update@amazon.co.uk+(subject:password+OR+subject:security)+newer_than:1d&limit=5"
```

### 7. GitHub — Security Advisories

Search Gmail:

```bash
curl -s "http://172.19.64.1:8100/gmail/search?q=from:github.com+(subject:security+OR+subject:vulnerability+OR+subject:dependabot)+newer_than:7d&limit=5"
```

### 8. Vercel — Deployment & Security Status

```bash
# Requires VERCEL_API_TOKEN env var
curl -s "https://api.vercel.com/v6/deployments?projectId={project_id}&limit=5&state=ERROR" \
  -H "Authorization: Bearer ${VERCEL_API_TOKEN}"
```

**Note**: If VERCEL_API_TOKEN is not set, skip Vercel checks and note it in the output.

## Schedule

Every 4 hours: 02:00, 06:00, 10:00, 14:00, 18:00, 22:00 UK.

Only post if there are findings. If everything is clean, stay silent (NO_REPLY).

## Output Format — Issues Found

```
SECURITY MONITOR — {time}

SUPABASE
  36 security advisor warnings (unchanged since last week)
  Link: https://supabase.com/dashboard/project/modjoikyuhqzouxvieua/database/security-advisor
  Want me to review the specific issues and suggest fixes?

GOOGLE
  New sign-in detected: Windows device, 2:41 PM yesterday
  This looks like your normal machine — no action needed.

  App password created for "Cowork-final" on 28 Feb
  Was this you? If not, revoke it at myaccount.google.com/apppasswords

VERCEL
  All clear — no failed deployments
```

## Output Format — All Clear

Return `NO_REPLY` — don't post when everything is fine. Only alert on changes or issues.

## Output Format — Conversational

When asked "any security issues?" or "security check":

```
SECURITY STATUS

Supabase: 36 DB security warnings (RLS/policies) — ongoing, same as last week
Google: 2 security alerts in last 7 days (both normal sign-ins)
Vercel: Skipped (no API token configured)

Overall: AMBER — Supabase warnings need attention
Want me to walk through the Supabase security advisor findings?
```

## Logic

### Severity Levels

- **RED** (post immediately + WhatsApp):
  - Unknown user registered in Supabase
  - Google password or recovery change
  - Google sign-in from unknown location/device
  - Shopify suspicious login detected
  - Amazon password recovery you didn't request
  - 3+ eBay security codes in one day (brute force attempt)

- **AMBER** (include in scheduled post):
  - Supabase security warnings (ongoing or count changed)
  - New Google app password created
  - New Google OAuth access granted
  - eBay password reset (single occurrence)
  - GitHub security advisory / Dependabot alert
  - Failed Vercel deployments

- **GREEN** (suppress / NO_REPLY):
  - Known sign-ins from expected devices
  - Normal deployment activity
  - No new issues since last check
  - eBay security code (single, likely your own login)

### Deduplication

- Track what was reported in the last post (use Second Brain or in-memory)
- Don't repeat the same Supabase "36 errors" every 4 hours
- Only re-alert if the count changes or a new email arrives
- Google alerts: only flag emails newer than last check

### Offering Help

When flagging issues, always offer actionable next steps:
- Supabase RLS warnings: "Want me to review the specific tables and suggest RLS policies?"
- Unknown sign-in: "Should I revoke this session? Here's the link..."
- Failed deployment: "Want me to check the build logs?"
- App password: "Was this you? If not I can help revoke it."

## Known Expected State

- **Supabase users**: chris@hadleybricks.co.uk, chrishadley1983@gmail.com, tomfreeman1983@gmail.com, contact@gainaiservices.co.uk
- **Google account**: chrishadley1983@gmail.com
- **Vercel project**: hadley-bricks-inventory-management

## Rules

- Only post when there are findings (NO_REPLY otherwise)
- RED severity: also send via WhatsApp to Chris
- Be concise but actionable — what's the issue, what should Chris do
- Always offer to help fix rather than just reporting
- Don't nag about the same issue repeatedly

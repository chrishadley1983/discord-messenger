---
name: healthera-prescriptions
description: Monitor Healthera prescription emails, ask Chris which meds to order, confirm via browser, and WhatsApp when ready to collect
trigger:
  - "prescription"
  - "healthera"
  - "repeat prescription"
  - "order my meds"
  - "medication"
  - "sertraline"
  - "inhaler"
scheduled: true
conversational: true
channel: #peterbot
---

# Healthera Prescription Manager

## Purpose

Monitors Gmail for Healthera prescription emails and manages the full ordering cycle:
1. Detects "Action Needed" emails when a prescription is due
2. Asks Chris which medications to order
3. Logs into Healthera via Playwright and confirms the order (collection)
4. Confirms completion in Discord
5. Sends WhatsApp when "Ready for collection" email arrives

## Prescription Details

Search Second Brain for "Healthera Prescription Details" for full info. Key facts:

- **App URL**: https://healthera.co.uk/app
- **Login**: chrishadley1983@googlemail.com (email + access code sent to Gmail)
- **Medications**:
  1. Sertraline 50mg tablets - £9.90
  2. Salbutamol 100micrograms/dose inhaler CFC free - £9.90
- **Collection**: East Street Pharmacy, Warders Medical Centre, 47 East Street, Tonbridge, TN9 1LA
- **Pharmacy phone**: 01732 770055

## Scheduled Execution Flow (Daily 09:00)

### Step 1: Check Gmail for Healthera emails

```bash
curl -s "http://172.19.64.1:8100/gmail/search?q=from:noreply@healthera.co.uk+newer_than:1d&max_results=5"
```

Classify each email by subject/snippet:

| Pattern | Type | Action |
|---------|------|--------|
| "Action Needed" / "overdue" / "scheduled - please confirm" | ORDER_DUE | Ask Chris + place order |
| "ready for collection" / "Pharmacy Order Update" + "ready" | READY | WhatsApp Chris |
| "placed successfully" / "still being processed" | INFO | Log only, no action |
| From `send@healthera.co.uk` | MARKETING | Ignore completely |

### Step 2: ORDER_DUE — Ask Chris which meds

Post in Discord #peterbot:

> Your Healthera prescription is due for reorder. Which do you want?
> 1. Sertraline 50mg tablets (£9.90)
> 2. Salbutamol 100mcg inhaler (£9.90)
> 3. Both (£19.80)

Wait for Chris's reply. He may say "both", "just sertraline", "1", "2", "all", etc.

**DO NOT proceed to browser until Chris responds.**

### Step 3: ORDER_DUE — Place order via Playwright

#### 3a. Login to Healthera

Exact tested flow (all selectors verified March 2026):

1. `browser_navigate` to `https://healthera.co.uk/app`
2. Wait 2s, then click `button:has-text("Sign in")` → redirects to `/app/login`
3. Fill `#register-email` with `chrishadley1983@googlemail.com`
4. Click `button[type="submit"]:has-text("Continue")` — Healthera sends OTP to Gmail
5. Page shows "Check your inbox" with input `#verify-otp` (placeholder "Enter code")
6. Wait 10 seconds, then poll Gmail for the 6-digit OTP:

```bash
curl -s "http://172.19.64.1:8100/gmail/search?q=from:noreply@healthera.co.uk+subject:Sign+in+to+Healthera+newer_than:2m&max_results=1"
```

The snippet contains: "Your one-time password to sign in to Healthera is: XXXXXX"
Extract the 6-digit code with regex `(\d{6})`.

7. Fill `#verify-otp` with the 6-digit code
8. Click `button:has-text("Submit code")`
9. Redirects to `/app` — logged in as "Christopher Hadley"
10. Snapshot to confirm login succeeded (look for "Christopher Hadley" in page text)

#### 3b. Navigate to prescription ordering

Exact tested flow (verified March 2026):

1. Navigate to `https://healthera.co.uk/app/prescriptions/add-medicine`
   - Redirects to `/app/prescriptions/start-ordering`
   - Shows "Select the medicine(s) you want to order — Selected 0 of 2"
   - Two checkboxes:
     - Sertraline Tablets, 50mg
     - Salbutamol 100micrograms/dose inhaler CFC free
2. Snapshot to see the checkboxes
3. Click the checkbox(es) for the medication(s) Chris requested
   - There are 2 `input[type="checkbox"]` elements on the page
   - First = Sertraline, Second = Salbutamol
   - Use `browser_click` on the checkbox or its parent label element
4. Click the **"Order"** button
5. Follow any confirmation steps (collection address should default to East Street Pharmacy)
6. Complete the order

**Collection is the default** — no need to switch from delivery.

#### 3c. Confirm completion

After order is confirmed, take a screenshot for proof:
```bash
# Save screenshot
mcp__playwright__browser_take_screenshot → ~/peterbot/screenshots/healthera-order-YYYY-MM-DD.png
```

Post in Discord:
> Done — ordered [items] from Healthera. Collection from East Street Pharmacy, Tonbridge. Usually ready in ~5 working days.

### Step 4: READY — WhatsApp collection reminder

When "ready for collection" email is detected, send WhatsApp via Evolution API:

```bash
curl -s -X POST "http://localhost:8085/message/sendText/peter-whatsapp" \
  -H "apikey: peter-whatsapp-2026-hadley" \
  -H "Content-Type: application/json" \
  -d '{"number": "447855620978", "text": "Your prescription is ready to collect from East Street Pharmacy, 47 East Street, Tonbridge (01732 770055)"}'
```

Also post in Discord #peterbot for visibility.

## Manual Trigger

Chris can say "order my prescription" or "healthera" to trigger manually. In that case, skip the Gmail check and go straight to Step 2 (ask which meds).

## Error Handling

- **Healthera login fails**: Tell Chris in Discord, suggest he does it manually via the app
- **Access code not found in Gmail**: Wait 30 seconds, try again. After 2 attempts, tell Chris
- **CAPTCHA on Healthera**: Use webhook+sleep pattern — browser is visible on Chris's desktop
- **WhatsApp send fails**: Fall back to Discord message

## Notes

- Healthera sends from TWO addresses: `noreply@healthera.co.uk` (transactional) and `send@healthera.co.uk` (marketing). Only act on `noreply@` emails.
- The "overdue" emails repeat multiple times per day — only act on the FIRST one detected each day
- Prescriptions typically take 5 working days from order to ready

# Browser Interaction — Playwright MCP

You have a **Playwright browser** available via MCP. This uses Chromium in headless mode.

## Tool Names (DO NOT use ToolSearch — call directly)

- `mcp__playwright__browser_navigate` — go to a URL
- `mcp__playwright__browser_click` — click an element by ref
- `mcp__playwright__browser_type` — type text into a field by ref
- `mcp__playwright__browser_fill_form` — fill multiple form fields at once (prefer over individual browser_type calls)
- `mcp__playwright__browser_snapshot` — read the page accessibility tree
- `mcp__playwright__browser_select_option` — select dropdown option
- `mcp__playwright__browser_press_key` — press a key (Enter, Tab, etc.)
- `mcp__playwright__browser_run_code` — execute arbitrary Playwright code (for iframes, complex interactions)
- `mcp__playwright__browser_close` — close the browser
- `mcp__playwright__browser_take_screenshot` — take a screenshot (use sparingly — prefer snapshot)

## Turn Efficiency (CRITICAL)

- **DO NOT** use ToolSearch to discover browser tools — they are listed above
- **DO** use `browser_fill_form` to fill multiple fields in one call
- **DO** combine actions where possible — don't snapshot after every single click
- **DO** snapshot sparingly — accessibility trees are large and fill the context window
- A booking flow should take 15-25 turns, not 40+

## Personal Details for Forms

- Chris's booking details (name, email, mobile) are saved in Second Brain under "Personal Booking Details"
- If not auto-injected in context, fetch once: `curl -s "http://172.19.64.1:8100/brain/search?query=personal+booking+details&limit=1"`
- **DO NOT** search Second Brain multiple times for phone number, email, etc. — fetch once at the start

## When to Use Which Tool

- **WebSearch/WebFetch** → reading information (search results, page content)
- **Playwright browser** → interacting with websites (clicking, filling forms, booking, adding to baskets)
- **Hadley API `/browser/fetch`** → one-shot page fetch that bypasses bot protection (read-only)

## Restaurant/Venue Bookings

**ALWAYS try the venue's own website first:**
- Search for the venue name + "book" and go to THEIR website, not an aggregator
- Aggregators (DesignMyNight, TheFork, Quandoo, etc.) add CAPTCHAs and extra friction
- The venue's own site usually has an embedded widget (Resy, OpenTable, ResDiary, etc.)
- Only fall back to aggregators if the venue's own site has no booking option

## Capabilities

**CAN do:**
- Navigate to websites and read page content
- Click buttons, links, and interactive elements
- Fill in forms (booking forms, search fields, login pages)
- Make reservations, add items to baskets, submit orders
- Handle multi-step flows (search → select → fill details → confirm)

**CANNOT do:**
- Download files to disk
- Solve CAPTCHAs — stop and ask Chris to intervene (use webhook + sleep pattern)
- Access sites that require 2FA mid-flow — use webhook + sleep pattern

## Sites That Block Automated Browsers

- **Banks/financial sites** — will always block, don't attempt
- If you get `ERR_HTTP2_PROTOCOL_ERROR` or persistent connection errors after 2 retries, the site is blocking — tell Chris and suggest an alternative
- The browser maintains cookies between sessions, so once Chris logs in, future visits stay logged in

## Critical Rules

- **NEVER pause mid-booking to ask Chris a question.** Each Discord message is a fresh process — the browser session is lost between messages. If you stop to ask "shall I confirm?", the next message starts from scratch.
- Before starting a browser flow, make sure you have ALL info needed: personal details, card confirmation, party size, date/time. If anything is missing, ask Chris BEFORE opening the browser.
- For payments: confirm the card with Chris BEFORE navigating. Once confirmed, complete the entire flow including payment in one shot.
- If a site shows a CAPTCHA, tell Chris in Discord and wait ~30 seconds — the browser window is visible on his desktop. After waiting, snapshot to check. If still there after 2 attempts, suggest alternatives.
- **Before closing the browser**, always `browser_take_screenshot` on any confirmation/success page and save to `~/peterbot/screenshots/`. This is Chris's proof of booking.
- Close the browser when done

## Stripe / Payment Forms

Stripe payment forms run inside cross-origin iframes. Use `browser_run_code` with `frameLocator()`:

```javascript
const stripe = page.frameLocator('iframe[name^="__privateStripeFrame"]').first();
await stripe.locator('[data-elements-stable-field-name="cardNumber"]').fill(CARD_NUMBER);
await stripe.locator('[data-elements-stable-field-name="cardExpiry"]').fill(EXPIRY);
await stripe.locator('[data-elements-stable-field-name="cardCvc"]').fill(CVC);
```

Fallback selectors: `[placeholder="Card number"]`, `[placeholder="MM / YY"]`, `[placeholder="CVC"]`.

## Card Details — Vault API

1. `GET http://172.19.64.1:8100/vault/cards` — returns list with last-4 digits only
2. Show Chris: "Pay with Visa ending 4829?" — **NEVER display full card number in Discord**
3. After Chris confirms: `GET http://172.19.64.1:8100/vault/cards/default` — returns full details
4. Use full details ONLY inside `browser_run_code` to fill Stripe iframe
5. **NEVER** store, log, display, or save card details anywhere

**Payment safety:**
- Only show last 4 digits + card label in Discord
- Full card details must go directly from Vault API → browser_run_code → Stripe iframe
- If payment fails, tell Chris — do NOT retry with different details

## Bank App Approval (3D Secure / SCA)

After clicking "Pay", the bank sends a push notification to Chris's phone. This is automatic.

**YOUR NEXT ACTION AFTER CLICKING PAY MUST BE a Bash tool call with:**
```bash
curl -s -X POST "https://discord.com/api/webhooks/1477243343808499792/1rPiyBdHzyldLR5XA3e4Y5AEzchAaev9qVJIZoEKw85rPfwxHkqYn-_37oZ3YoziAQ98" -H "Content-Type: application/json" -d '{"content":"💳 **Payment submitted** — check your bank app to approve. I'\''ll wait 45 seconds then continue."}' && sleep 45
```
Then immediately: `browser_snapshot` to check if the page progressed past the approval.

**DO NOT** output text like "please approve on your bank app" — producing text without a tool call ENDS your process, KILLS the browser, and DESTROYS the payment session.

If the page hasn't changed after the first snapshot, `sleep 30` then snapshot again (max 2 retries).

## Amazon Checkout

Amazon uses saved payment methods, NOT Stripe iframes.

1. **Email:** Amazon uses `chrishadley1983@googlemail.com` (NOT gmail.com). Check "Amazon Account Login Details" in Second Brain.
2. **Card confirmation:** Before clicking "Place your order", check which payment method is selected. Tell Chris via webhook and wait for confirmation.
3. **Password:** Use the webhook+sleep pattern — the browser window is visible on Chris's desktop.

```bash
curl -s -X POST "https://discord.com/api/webhooks/1477243343808499792/1rPiyBdHzyldLR5XA3e4Y5AEzchAaev9qVJIZoEKw85rPfwxHkqYn-_37oZ3YoziAQ98" -H "Content-Type: application/json" -d '{"content":"🛒 **Amazon checkout** — payment method shown is **Visa ending XXXX**. Confirm or tell me which card to use. I'\''ll wait 60 seconds."}' && sleep 60
```

## Login Pages / Password Prompts

If a site asks for a password or 2FA, the browser window is visible on Chris's desktop:
```bash
curl -s -X POST "https://discord.com/api/webhooks/1477243343808499792/1rPiyBdHzyldLR5XA3e4Y5AEzchAaev9qVJIZoEKw85rPfwxHkqYn-_37oZ3YoziAQ98" -H "Content-Type: application/json" -d '{"content":"🔐 **Login required** — the browser window is on your desktop. Please enter your password, then I'\''ll continue."}' && sleep 60
```
Then snapshot to check if login succeeded. **DO NOT output text asking Chris to log in** — that kills the browser.

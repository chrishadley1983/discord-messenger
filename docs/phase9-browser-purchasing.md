# Phase 9: Browser-Based Purchasing for Peter

## Overview

Enable Peter to make purchases on websites without APIs (Amazon UK, eBay UK) using browser automation with Claude vision, secured by spending limits and Discord confirmation flows.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DISCORD                                         │
│                                                                              │
│  User: "Order bubble wrap from Amazon"                                       │
│                              │                                               │
│                              ▼                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        CONFIRMATION FLOW                              │   │
│  │  🛒 Purchase Confirmation Required                                    │   │
│  │  Item: Bubble Wrap 50m Roll                                          │   │
│  │  Price: £12.99                                                        │   │
│  │  [Screenshot]                                                         │   │
│  │  React ✅ to confirm, ❌ to cancel                                    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PETERBOT (WSL/tmux)                               │
│                                                                              │
│  Claude Code receives message → Detects "purchase" skill trigger            │
│  → Reads SKILL.md instructions                                              │
│  → Calls Hadley API /browser/* endpoints                                    │
│  → Uses vision to understand screenshots                                    │
│  → Outputs [PURCHASE_CONFIRMATION] for Discord flow                         │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HADLEY API (port 8100)                             │
│                                                                              │
│  /browser/session/start    ──────►  Start Playwright session                │
│  /browser/screenshot       ──────►  Capture current page (base64)           │
│  /browser/action           ──────►  Click, type, scroll, navigate           │
│  /browser/limits           ──────►  Check spending limits                   │
│  /browser/session/end      ──────►  Close browser session                   │
│                                                                              │
│  Security Middleware:                                                        │
│  ├── Domain allowlist enforcement                                           │
│  ├── Spending limit checks                                                   │
│  ├── Audit logging (every action)                                           │
│  └── Rate limiting                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       BROWSER AGENT (Playwright)                            │
│                                                                              │
│  • Dedicated Chrome profile (isolated from personal browser)                │
│  • Pre-authenticated sessions via stored cookies                            │
│  • Headless operation                                                        │
│  • Screenshot capture at every action                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TARGET SITES                                       │
│                                                                              │
│  ┌─────────────────┐              ┌─────────────────┐                       │
│  │  amazon.co.uk   │              │   ebay.co.uk    │                       │
│  │  (allowlisted)  │              │  (allowlisted)  │                       │
│  └─────────────────┘              └─────────────────┘                       │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SUPABASE                                           │
│                                                                              │
│  purchase_limits     ──────►  Per-order, daily, weekly limits               │
│  purchase_log        ──────►  Transaction history                           │
│  browser_action_log  ──────►  Screenshot audit trail                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Security Model

### Layer 1: Domain Allowlist

Only these domains can be accessed:

| Domain | Purpose | Max Order |
|--------|---------|-----------|
| amazon.co.uk | Packing supplies, business items | £50 |
| ebay.co.uk | Packing supplies, LEGO parts | £50 |

Any navigation outside these domains immediately aborts the session.

### Layer 2: Spending Limits

| Limit Type | Default | Description |
|------------|---------|-------------|
| Per-order | £50 | Maximum single purchase |
| Daily | £100 | Maximum per 24 hours |
| Weekly | £250 | Maximum per 7 days |

Limits are checked before checkout. Exceeded limits block the purchase.

### Layer 3: Discord Confirmation

Every purchase requires explicit user confirmation via Discord reaction:
- ✅ = Confirm and complete purchase
- ❌ = Cancel purchase
- No reaction within 5 minutes = Automatic cancellation

### Layer 4: Audit Trail

Every browser action is logged:
- Screenshot before action
- Action details (click coordinates, typed text, URL)
- Screenshot after action
- Timestamp and session ID

90-day retention in Supabase.

### Layer 5: Session Isolation

- Dedicated browser profile: `data/browser_sessions/{domain}_profile/`
- Cookies stored separately from personal browser
- One active session at a time
- No access to saved passwords - pre-authenticated only

---

## Data Flow: Complete Purchase

```
1. USER MESSAGE
   "Peter, order some bubble wrap from Amazon"

2. SKILL DETECTION
   router.py detects triggers: "order", "amazon"
   → Loads skills/purchase/SKILL.md

3. LIMIT CHECK
   Claude calls: GET /browser/limits
   → Returns: {per_order: 50, daily_remaining: 87.01, weekly_remaining: 237.01}

4. SESSION START
   Claude calls: POST /browser/session/start?domain=amazon.co.uk
   → Playwright launches with stored Amazon cookies
   → Returns: {session_id: "abc123", authenticated: true}

5. BROWSE & SEARCH (Agent Loop)

   a) GET /browser/screenshot
      → Claude SEES Amazon homepage
      → Claude reasons: "I need to search for bubble wrap"

   b) POST /browser/action {type: "click", x: 450, y: 65}
      → Clicks search box

   c) POST /browser/action {type: "type", text: "bubble wrap 50m roll"}
      → Types search query

   d) POST /browser/action {type: "click", x: 520, y: 65}
      → Clicks search button

   e) GET /browser/screenshot
      → Claude SEES search results
      → Claude reasons: "Found good option at £12.99"

   f) POST /browser/action {type: "click", x: 300, y: 280}
      → Clicks product

   g) GET /browser/screenshot
      → Claude SEES product page

   h) POST /browser/action {type: "click", x: 850, y: 420}
      → Clicks "Add to Basket"

   i) Navigate to cart, verify total

6. CONFIRMATION REQUEST
   Claude outputs special block:

   [PURCHASE_CONFIRMATION]
   {
     "item": "Bubble Wrap Roll 50m x 300mm",
     "price": 12.99,
     "domain": "amazon.co.uk",
     "delivery": "Tomorrow by 9pm",
     "screenshot_base64": "..."
   }
   [/PURCHASE_CONFIRMATION]

7. DISCORD CONFIRMATION
   bot.py detects [PURCHASE_CONFIRMATION]
   → Sends embed with screenshot to Discord
   → Adds ✅ and ❌ reactions
   → Waits up to 5 minutes for user reaction

8. USER CONFIRMS (✅)

9. CHECKOUT COMPLETION
   Claude receives: "User confirmed purchase"
   → POST /browser/action to complete checkout
   → Captures order confirmation screenshot

10. AUDIT & CLEANUP
    → Log transaction to purchase_log
    → Save final screenshots
    → POST /browser/session/end

11. RESPONSE
    "Done! Ordered Bubble Wrap Roll 50m for £12.99.
     Order #123-456-789. Arriving tomorrow by 9pm."
```

---

## File Structure

```
Discord-Messenger/
├── browser_agent/                      # NEW: Browser automation package
│   ├── __init__.py
│   ├── service.py                      # Main BrowserService class
│   ├── session_manager.py              # Cookie/session handling
│   ├── domain_allowlist.py             # Security: allowed domains
│   ├── actions.py                      # Click, type, scroll, navigate
│   ├── limits.py                       # Spending limit checks
│   └── config.py                       # Constants and settings
│
├── data/
│   └── browser_sessions/               # NEW: Browser session storage
│       ├── amazon.json                 # Amazon cookies/state
│       ├── amazon_profile/             # Amazon Chrome profile
│       ├── ebay.json                   # eBay cookies/state
│       └── ebay_profile/               # eBay Chrome profile
│
├── domains/peterbot/
│   ├── purchase_confirmation.py        # NEW: Discord confirmation flow
│   └── wsl_config/skills/
│       ├── purchase/                   # NEW: Purchase skill
│       │   └── SKILL.md
│       └── manifest.json               # UPDATE: Add purchase triggers
│
├── hadley_api/
│   ├── main.py                         # UPDATE: Add /browser/* endpoints
│   └── browser_routes.py               # NEW: Browser endpoint handlers
│
├── migrations/
│   └── 003_create_purchase_tables.sql  # NEW: Supabase schema
│
└── scripts/
    └── setup_browser_session.py        # NEW: Manual auth helper
```

---

## Database Schema

```sql
-- migrations/003_create_purchase_tables.sql

-- Spending limits configuration
CREATE TABLE purchase_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    limit_type TEXT NOT NULL CHECK (limit_type IN ('per_order', 'daily', 'weekly')),
    amount_gbp DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(limit_type)
);

-- Default limits
INSERT INTO purchase_limits (limit_type, amount_gbp) VALUES
    ('per_order', 50.00),
    ('daily', 100.00),
    ('weekly', 250.00);

-- Purchase transaction log
CREATE TABLE purchase_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    url TEXT,
    item_description TEXT,
    amount_gbp DECIMAL(10,2),
    currency TEXT DEFAULT 'GBP',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'awaiting_confirmation', 'confirmed',
                          'completed', 'cancelled', 'failed')),
    confirmation_message_id TEXT,
    user_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    order_reference TEXT,
    confirmed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Browser action audit log
CREATE TABLE browser_action_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_id UUID REFERENCES purchase_log(id),
    session_id TEXT NOT NULL,
    action_type TEXT NOT NULL,  -- navigate, click, type, scroll, screenshot
    action_data JSONB,          -- {x, y, text, url, direction}
    screenshot_before TEXT,     -- base64 or storage URL
    screenshot_after TEXT,
    page_url TEXT,
    page_title TEXT,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_purchase_log_status ON purchase_log(status);
CREATE INDEX idx_purchase_log_created ON purchase_log(created_at);
CREATE INDEX idx_purchase_log_domain ON purchase_log(domain);
CREATE INDEX idx_action_log_session ON browser_action_log(session_id);
CREATE INDEX idx_action_log_purchase ON browser_action_log(purchase_id);
CREATE INDEX idx_action_log_created ON browser_action_log(created_at);

-- RLS (service role bypasses)
ALTER TABLE purchase_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE browser_action_log ENABLE ROW LEVEL SECURITY;
```

---

## API Endpoints

### POST /browser/session/start

Start a browser session for an allowed domain.

**Request:**
```json
{
    "domain": "amazon.co.uk"
}
```

**Response:**
```json
{
    "session_id": "sess_abc123",
    "domain": "amazon.co.uk",
    "authenticated": true,
    "viewport": {"width": 1280, "height": 800}
}
```

**Errors:**
- 403: Domain not in allowlist
- 409: Session already active
- 500: Browser failed to start

---

### GET /browser/screenshot

Capture current page as base64 PNG.

**Query params:**
- `session_id` (required)
- `full_page` (optional, default false)

**Response:**
```json
{
    "screenshot": "data:image/png;base64,iVBORw0KGgo...",
    "url": "https://www.amazon.co.uk/...",
    "title": "Amazon.co.uk: bubble wrap"
}
```

---

### POST /browser/action

Execute a browser action.

**Request:**
```json
{
    "session_id": "sess_abc123",
    "action": "click",
    "params": {
        "x": 450,
        "y": 120
    }
}
```

**Action types:**

| Action | Params | Description |
|--------|--------|-------------|
| `navigate` | `{url: string}` | Go to URL (allowlist enforced) |
| `click` | `{x: int, y: int}` | Click at coordinates |
| `type` | `{text: string}` | Type into focused element |
| `scroll` | `{direction: "up"\|"down", amount?: int}` | Scroll page |
| `press` | `{key: string}` | Press key (Enter, Tab, etc.) |
| `wait` | `{ms: int}` | Wait for page to settle |

**Response:**
```json
{
    "success": true,
    "url": "https://www.amazon.co.uk/s?k=bubble+wrap",
    "message": "Clicked at (450, 120)"
}
```

**Errors:**
- 400: Invalid action or params
- 403: Navigation outside allowlist
- 404: Session not found
- 500: Action failed

---

### GET /browser/limits

Get current spending limits and usage.

**Response:**
```json
{
    "limits": {
        "per_order": 50.00,
        "daily": 100.00,
        "weekly": 250.00
    },
    "usage": {
        "today": 12.99,
        "this_week": 45.98
    },
    "remaining": {
        "per_order": 50.00,
        "daily": 87.01,
        "weekly": 204.02
    }
}
```

---

### POST /browser/session/end

Close browser session and cleanup.

**Request:**
```json
{
    "session_id": "sess_abc123",
    "save_session": true
}
```

**Response:**
```json
{
    "success": true,
    "actions_logged": 15,
    "session_duration_seconds": 45
}
```

---

## Purchase Skill

```markdown
# skills/purchase/SKILL.md

---
name: purchase
description: Make browser-based purchases on approved e-commerce sites
triggers:
  - "buy"
  - "purchase"
  - "order from amazon"
  - "order from ebay"
  - "order packing"
  - "get bubble wrap"
  - "buy packaging"
scheduled: false
conversational: true
---

# Purchase Skill

You can make purchases on approved websites (Amazon UK, eBay UK) using
browser automation with vision.

## Security Rules (MUST FOLLOW)

1. **Check limits first** - Always call GET /browser/limits before proceeding
2. **Only allowed domains** - amazon.co.uk and ebay.co.uk only
3. **Confirmation required** - Output [PURCHASE_CONFIRMATION] before checkout
4. **Never enter payment details** - Use saved payment methods only
5. **Abort on anything suspicious** - Close session if redirected unexpectedly

## Workflow

### 1. Check Limits
```bash
curl -s http://localhost:8100/browser/limits -H "X-API-Key: $HADLEY_API_KEY"
```

If insufficient limits, tell the user and stop.

### 2. Start Session
```bash
curl -X POST "http://localhost:8100/browser/session/start" \
  -H "X-API-Key: $HADLEY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"domain": "amazon.co.uk"}'
```

### 3. Browse with Vision

Use screenshot + action loop:

```bash
# Get screenshot (returns base64 image you can see)
curl -s "http://localhost:8100/browser/screenshot?session_id=SESSION_ID" \
  -H "X-API-Key: $HADLEY_API_KEY"

# Click at coordinates
curl -X POST "http://localhost:8100/browser/action" \
  -H "X-API-Key: $HADLEY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "SESSION_ID", "action": "click", "params": {"x": 450, "y": 120}}'

# Type text
curl -X POST "http://localhost:8100/browser/action" \
  -H "X-API-Key: $HADLEY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "SESSION_ID", "action": "type", "params": {"text": "bubble wrap"}}'
```

### 4. Request Confirmation

When cart is ready, output this EXACT format:

```
[PURCHASE_CONFIRMATION]
{
  "item": "Product name here",
  "price": 12.99,
  "domain": "amazon.co.uk",
  "delivery": "Tomorrow by 9pm",
  "session_id": "SESSION_ID"
}
[/PURCHASE_CONFIRMATION]

I found what you're looking for. Please confirm the purchase above.
```

Then STOP and wait. The system will handle Discord confirmation.

### 5. Complete or Cancel

You'll receive either:
- "User confirmed purchase, proceed with checkout"
- "User cancelled purchase"

Act accordingly.

### 6. Close Session

Always close the session when done:
```bash
curl -X POST "http://localhost:8100/browser/session/end" \
  -H "X-API-Key: $HADLEY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "SESSION_ID"}'
```

## Tips for Vision Navigation

- Search boxes are usually at the top of the page
- "Add to Cart/Basket" buttons are typically orange/yellow on Amazon
- Always take a screenshot after each action to verify the result
- If a page looks like a login prompt, STOP - session may have expired
- Look for the cart total before requesting confirmation

## Error Handling

- If redirected outside allowed domain: Close session immediately
- If login required: Tell user "Session expired, please re-authenticate"
- If item out of stock: Inform user and suggest alternatives
- If price exceeds limits: Inform user of the limit
```

---

## Discord Confirmation Handler

```python
# domains/peterbot/purchase_confirmation.py

import discord
import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
import aiohttp

CONFIRM_EMOJI = "✅"
CANCEL_EMOJI = "❌"
CONFIRMATION_TIMEOUT = 300  # 5 minutes

# Store pending confirmations
pending_confirmations: dict[str, dict] = {}


def extract_confirmation_data(response: str) -> Optional[dict]:
    """Extract [PURCHASE_CONFIRMATION] block from response."""
    pattern = r'\[PURCHASE_CONFIRMATION\]\s*(\{.*?\})\s*\[/PURCHASE_CONFIRMATION\]'
    match = re.search(pattern, response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def remove_confirmation_block(response: str) -> str:
    """Remove the confirmation block from response text."""
    pattern = r'\[PURCHASE_CONFIRMATION\].*?\[/PURCHASE_CONFIRMATION\]\s*'
    return re.sub(pattern, '', response, flags=re.DOTALL).strip()


async def request_purchase_confirmation(
    channel: discord.TextChannel,
    user_id: int,
    confirmation_data: dict,
    bot: discord.Client
) -> Tuple[bool, str]:
    """
    Send purchase confirmation embed and wait for user reaction.

    Returns:
        (confirmed: bool, reason: str)
    """

    # Build embed
    embed = discord.Embed(
        title="🛒 Purchase Confirmation Required",
        color=discord.Color.orange(),
        timestamp=datetime.utcnow()
    )

    embed.add_field(
        name="Item",
        value=confirmation_data.get("item", "Unknown item"),
        inline=False
    )
    embed.add_field(
        name="Price",
        value=f"£{confirmation_data.get('price', 0):.2f}",
        inline=True
    )
    embed.add_field(
        name="Site",
        value=confirmation_data.get("domain", "Unknown"),
        inline=True
    )

    if delivery := confirmation_data.get("delivery"):
        embed.add_field(name="Delivery", value=delivery, inline=True)

    embed.set_footer(
        text=f"React {CONFIRM_EMOJI} to confirm, {CANCEL_EMOJI} to cancel • Expires in 5 minutes"
    )

    # Send message
    msg = await channel.send(embed=embed)
    await msg.add_reaction(CONFIRM_EMOJI)
    await msg.add_reaction(CANCEL_EMOJI)

    # Store pending confirmation
    session_id = confirmation_data.get("session_id", "unknown")
    pending_confirmations[str(msg.id)] = {
        "session_id": session_id,
        "user_id": user_id,
        "data": confirmation_data,
        "expires": datetime.utcnow() + timedelta(seconds=CONFIRMATION_TIMEOUT)
    }

    # Wait for reaction
    def check(reaction: discord.Reaction, user: discord.User) -> bool:
        return (
            user.id == user_id
            and reaction.message.id == msg.id
            and str(reaction.emoji) in [CONFIRM_EMOJI, CANCEL_EMOJI]
        )

    try:
        reaction, user = await bot.wait_for(
            'reaction_add',
            timeout=CONFIRMATION_TIMEOUT,
            check=check
        )

        # Clean up
        del pending_confirmations[str(msg.id)]

        if str(reaction.emoji) == CONFIRM_EMOJI:
            # Update embed to confirmed
            embed.color = discord.Color.green()
            embed.set_footer(text="✅ Confirmed - Processing purchase...")
            await msg.edit(embed=embed)
            return True, "User confirmed purchase"
        else:
            # Update embed to cancelled
            embed.color = discord.Color.red()
            embed.set_footer(text="❌ Cancelled by user")
            await msg.edit(embed=embed)
            return False, "User cancelled purchase"

    except asyncio.TimeoutError:
        # Clean up
        if str(msg.id) in pending_confirmations:
            del pending_confirmations[str(msg.id)]

        # Update embed to expired
        embed.color = discord.Color.greyple()
        embed.set_footer(text="⏰ Expired - No response received")
        await msg.edit(embed=embed)
        return False, "Confirmation timeout - no response within 5 minutes"


async def handle_purchase_response(
    channel: discord.TextChannel,
    user_id: int,
    response: str,
    bot: discord.Client
) -> Tuple[str, Optional[str]]:
    """
    Check if response contains purchase confirmation request.
    If so, handle the confirmation flow.

    Returns:
        (cleaned_response, follow_up_instruction)
        - cleaned_response: Response with confirmation block removed
        - follow_up_instruction: Instruction to send to Claude if confirmed/cancelled
    """

    confirmation_data = extract_confirmation_data(response)

    if not confirmation_data:
        return response, None

    # Remove the confirmation block from visible response
    cleaned_response = remove_confirmation_block(response)

    # Run confirmation flow
    confirmed, reason = await request_purchase_confirmation(
        channel=channel,
        user_id=user_id,
        confirmation_data=confirmation_data,
        bot=bot
    )

    if confirmed:
        return cleaned_response, "User confirmed purchase. Proceed with checkout and complete the order."
    else:
        return cleaned_response, f"User cancelled purchase. Reason: {reason}. Close the browser session."
```

---

## Implementation Phases

### Phase 1: Foundation
- [ ] Create `browser_agent/` package structure
- [ ] Implement domain allowlist
- [ ] Create Supabase migration for purchase tables
- [ ] Create `setup_browser_session.py` script
- [ ] Manually authenticate Amazon and eBay

### Phase 2: Browser Service
- [ ] Implement `BrowserService` class with Playwright
- [ ] Implement session manager with cookie persistence
- [ ] Implement action handlers (click, type, scroll, navigate)
- [ ] Implement screenshot capture

### Phase 3: API Layer
- [ ] Add `/browser/*` routes to Hadley API
- [ ] Implement spending limit checks
- [ ] Implement audit logging
- [ ] Add rate limiting

### Phase 4: Discord Integration
- [ ] Create `purchase_confirmation.py`
- [ ] Integrate confirmation detection into response pipeline
- [ ] Handle reaction-based confirmation flow
- [ ] Test end-to-end confirmation

### Phase 5: Skill & Testing
- [ ] Create `skills/purchase/SKILL.md`
- [ ] Update `manifest.json` with triggers
- [ ] Test with Amazon (bubble wrap)
- [ ] Test with eBay (packing supplies)

---

## Test Cases

### Happy Path: Amazon Purchase
1. "Peter, order some bubble wrap from Amazon"
2. Peter checks limits → OK
3. Peter starts browser session
4. Peter searches, finds product, adds to cart
5. Peter outputs confirmation request
6. User reacts ✅
7. Peter completes checkout
8. User receives confirmation with order number

### Cancellation Flow
1. "Peter, buy packing tape from Amazon"
2. Peter finds product, requests confirmation
3. User reacts ❌
4. Peter cancels, closes session
5. User sees "Purchase cancelled"

### Limit Exceeded
1. "Peter, order a £75 item from Amazon"
2. Peter checks limits → Exceeds per-order limit
3. Peter responds: "That exceeds the £50 per-order limit. Would you like me to find a cheaper alternative?"

### Session Expired
1. "Peter, order from Amazon"
2. Peter starts session
3. Amazon shows login page (cookies expired)
4. Peter detects login requirement
5. Peter responds: "Amazon session expired. Please run the auth script to re-authenticate."

---

## Monitoring & Alerts

### Metrics to Track
- Purchases per day/week
- Confirmation success rate
- Session duration
- Actions per session
- Domain violations (should be 0)

### Alerts
- Domain violation attempt → Immediate Discord alert
- Daily limit approaching (>80%) → Notification
- Multiple failed sessions → Check auth status
- Unusual purchase pattern → Review audit log

---

## Future Enhancements

1. **More sites**: Add approved retailers as needed
2. **Price comparison**: Check multiple sites before purchasing
3. **Reorder common items**: "Order the usual bubble wrap"
4. **Receipt parsing**: Extract order details from confirmation emails
5. **Spending reports**: Weekly/monthly purchase summaries

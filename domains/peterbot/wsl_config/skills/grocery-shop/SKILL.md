---
name: grocery-shop
description: Add shopping list to Sainsbury's trolley and book delivery slot
trigger:
  - "do the shopping"
  - "add shopping list to sainsburys"
  - "sainsburys order"
  - "grocery shop"
  - "add to trolley"
  - "book a delivery"
  - "book a slot"
  - "do the sainsburys"
  - "sainsburys shop"
scheduled: false
conversational: true
channel: null
---

# Grocery Shop

## Purpose

Take the current shopping list (from meal plan or explicit), add items to the Sainsbury's trolley, resolve ambiguous matches, and optionally book a delivery slot. Fully conversational with Chris making choices for unclear items.

## Pre-fetched Data

Data fetcher: `grocery-shop` — pulls:

- `data.shopping_list` — Current shopping list items (from meal plan ingredients)
- `data.trolley` — Current Sainsbury's trolley contents (for dedup)
- `data.login_status` — Whether Chris is logged in to Sainsbury's
- `data.store` — Store name (currently always "sainsburys")

## Workflow

### Step 1: Check Login

If `data.login_status.logged_in` is false:
```
You're not logged into Sainsbury's. Pop over to Chrome and log in here:
https://www.sainsburys.co.uk/gol-ui/groceries

Let me know when you're done and I'll retry.
```
Then respond with `NO_REPLY` — wait for Chris to come back.

### Step 2: Add Shopping List to Trolley

Call `POST http://172.19.64.1:8100/grocery/sainsburys/trolley/add-list` with the shopping list:
```json
{"items": [{"name": "chicken breast", "quantity": "500g"}, {"name": "rice", "quantity": "300g"}, ...]}
```

If Chris says "do the shopping" without a specific list, use `data.shopping_list` from the current meal plan.
If Chris provides a specific list, use that instead.

### Step 3: Report Results

Present results in three buckets:

```
🛒 **Sainsbury's Trolley Update**

✅ **Added** (12 items)
- Chicken Breast 500g — £4.50
- Basmati Rice 1kg — £1.85
- Broccoli — £0.69
...

❓ **Need your pick** (3 items)
1. **Black beans** — which one?
   a) Sainsbury's Black Beans 400g — £0.65
   b) Goya Black Beans 425g — £1.20
   c) Mr Organic Black Beans 400g — £1.40

2. **Hot sauce** — which one?
   a) Cholula Hot Sauce 150ml — £2.00
   b) Frank's RedHot 148ml — £1.75
   c) Encona Hot Pepper Sauce 142ml — £1.20

3. **Yoghurt** — which one?
   a) Sainsbury's Greek Yoghurt 500g — £1.50
   b) Fage Total 500g — £2.00
   c) Yeo Valley Natural 500g — £1.80

❌ **Not found** (1 item)
- Gochujang paste — no matches. Add manually or try a different search?

Reply with your picks like "1a, 2b, 3a" or tell me to skip any.
```

### Step 4: Resolve Choices

When Chris replies with choices (e.g., "1a, 2b, 3a" or "a, b, a" or "first one, frank's, skip 3"):

For each choice, call:
```
POST http://172.19.64.1:8100/grocery/sainsburys/trolley/resolve
{"item_name": "Black beans", "product_uid": "chosen_product_uid_here", "quantity": 1}
```

Report the results:
```
✅ Added: Black Beans (Sainsbury's), Frank's RedHot, Greek Yoghurt (Sainsbury's)
```

### Step 5: Trolley Summary & Slot Booking

After all items resolved:
```
🛒 **Trolley total: £47.83** (28 items)
Minimum spend: ✅ (£25.00)

Want me to book a delivery slot? I'll find the cheapest saver slots for the next few days.
```

If Chris says yes, call `GET http://172.19.64.1:8100/grocery/sainsburys/slots?prefer=saver` and present:

```
📦 **Cheapest Saver Slots**

1. Tue 10 Mar, 14:00-15:00 — £1.00
2. Wed 11 Mar, 19:00-20:00 — £1.00
3. Thu 12 Mar, 10:00-11:00 — £1.50
4. Sat 14 Mar, 07:00-08:00 — £2.00

Pick a number, or "no" to skip slot booking.
```

When Chris picks, call:
```
POST http://172.19.64.1:8100/grocery/sainsburys/slots/book
{"booking_key": "the_booking_key_from_slot"}
```

Confirm:
```
✅ **Slot booked** — Tue 10 Mar, 14:00-15:00 (£1.00)
You've got 2 hours to finalise the order on the Sainsbury's site.
```

## Hadley API Endpoints

- `GET /grocery/sainsburys/login-check` — Check login status
- `GET /grocery/sainsburys/search?q=...&limit=10` — Search products
- `POST /grocery/sainsburys/trolley/add-list` — Add shopping list (body: `{items: [{name, quantity?, unit?}]}`)
- `POST /grocery/sainsburys/trolley/resolve` — Resolve ambiguous item (body: `{item_name, product_uid, quantity?}`)
- `GET /grocery/sainsburys/trolley` — View trolley contents
- `GET /grocery/sainsburys/slots?prefer=saver` — Get delivery slots
- `POST /grocery/sainsburys/slots/book` — Book a slot (body: `{booking_key}`)
- `POST /meal-plan/shopping-list/to-trolley?store=sainsburys` — One-click meal plan → trolley

## Rules

- Always check login first — if not logged in, don't attempt any trolley operations
- Present prices on all items (Chris wants to see what he's paying)
- Default to Sainsbury's own-brand for ambiguous staples unless Chris has a preference
- If Chris says "skip" for a not-found item, move on — don't keep retrying
- Keep the resolve flow compact — "1a, 2b, 3a" format, not one-by-one questions
- Show running trolley total after resolving ambiguous items
- For slot booking, prefer saver slots (£1-2) over standard (£4-6.50)
- Minimum order is £25 — warn if trolley is below this before booking a slot
- UK English, casual tone
- If Chrome isn't running or CDP connection fails, tell Chris: "Chrome doesn't seem to be running — make sure it's open with remote debugging enabled."

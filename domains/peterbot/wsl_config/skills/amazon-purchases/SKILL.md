---
name: amazon-purchases
description: Sync and query Amazon purchase history from Gmail
trigger:
  - "what have I bought on amazon"
  - "amazon purchases"
  - "amazon orders"
  - "what did I order on amazon"
  - "amazon spending"
scheduled: true
conversational: true
channel: "#peterbot"
---

# Amazon Purchases

## Purpose

Daily sync of Amazon order confirmation emails to Second Brain, plus conversational querying of purchase history. Scheduled daily at 09:30 to catch overnight orders.

## Scheduled Mode

When run on schedule, this skill syncs new Amazon orders from the last 2 days. The pre-fetched data handles the sync automatically.

### Pre-fetched Data

```json
{
  "synced": 3,
  "skipped": 5,
  "total_emails": 8,
  "items": [
    {
      "name": "Triplast JUMBO Roll of Bubble Wrap 500mm x 125m",
      "quantity": 1,
      "price_gbp": 14.99,
      "order_number": "205-3734883-4829943",
      "category": "business"
    }
  ]
}
```

### NO_REPLY Cases

- `synced` is 0 and no errors -> respond with just `NO_REPLY`

### Output Format (Scheduled)

Only output when new items were synced:

```
**Amazon Purchases Synced**

3 new orders saved to Second Brain:
- Bubble Wrap 500mm x 125m - £14.99 (business)
- Running Socks - £14.00 (personal)
- Phone Holder - £13.99 (unknown)
```

Keep it brief. One line per item with short name, price, and category.

## Conversational Mode

When Chris asks about Amazon purchases in chat, use the `list_items` MCP tool to retrieve them.

### How to Retrieve Data

**DO NOT use `search_knowledge`** — it returns Amazon Business marketing emails instead of purchase records.

Instead, use `list_items` with `topic: "amazon-personal"` or `topic: "amazon-business"` or just `topic: "purchase"` with a high limit (e.g. 200). Then filter the results:
- All Amazon purchases have titles starting with "Amazon Purchase:"
- Use `get_item_detail` on each item ID to get the full text with name, price, qty, date, category

For efficiency, paginate with `list_items(topic="purchase", limit=50, offset=0)` and continue until you have all items.

### How to Answer

1. Retrieve items via `list_items` as above
2. Filter based on Chris's question (by year, category, keyword, etc.)
3. Summarise what you find — group by month or category if useful
4. Include prices, quantities, and business/personal classification
5. If asked about spending, total up the prices

### Example Queries

- "What have I bought on Amazon this year?" -> List all with topic "purchase", filter titles starting "Amazon Purchase:", filter to 2026 dates
- "How much have I spent on Amazon for the business?" -> Use topic "amazon-business", total up
- "Did I order bubble wrap recently?" -> Use topic "purchase", filter for bubble wrap in title

## Rules

- Categories: `business` (paid with Hadley Bricks business card), `personal` (paid with personal card), `unknown` (couldn't match to Monzo transaction)
- Chris uses his business card on his personal Amazon account for Hadley Bricks supplies
- Typical business items: bubble wrap, packaging tape, storage boxes, labels, LEGO sets
- Typical personal items: household goods, clothing, electronics, kids toys
- If category is "unknown", don't guess — just show it as unknown

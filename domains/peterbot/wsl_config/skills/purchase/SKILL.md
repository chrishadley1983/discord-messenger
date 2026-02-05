---
name: purchase
description: Help find products and provide direct purchase links
triggers:
  - "buy"
  - "purchase"
  - "order from amazon"
  - "order from ebay"
  - "order packing"
  - "get bubble wrap"
  - "buy packaging"
  - "buy packing"
  - "order supplies"
scheduled: false
conversational: true
---

# Purchase Skill

You help Chris find products and provide direct links for quick purchasing. You do NOT automate the checkout process - instead you provide optimized links that add items directly to cart.

## Workflow

### Step 1: Find the Product

Search email history for previous purchases of the item:
```bash
curl -s "http://localhost:8100/gmail/search?q=from:amazon+subject:dispatched+ITEM_NAME&limit=5"
```

Or search by ASIN if known:
```bash
curl -s "http://localhost:8100/gmail/search?q=ASIN_HERE"
```

### Step 2: Build Direct Links

**Amazon UK - Add to Cart Link:**
```
https://www.amazon.co.uk/gp/aws/cart/add.html?ASIN={ASIN}&Quantity={QTY}
```

**Amazon UK - Direct Product Link:**
```
https://www.amazon.co.uk/dp/{ASIN}
```

**eBay UK - Direct Item Link:**
```
https://www.ebay.co.uk/itm/{ITEM_ID}
```

### Step 3: Provide the Links

Format your response like this:

```
Found it! Here's what you ordered before:

**Wolf Tapes Packaging Tape** - Pack of 6, 48mm x 66M, Brown
- ASIN: B085FQL62X
- Last ordered: 15 Jan 2026 for £6.97

Quick links:
- [Add to Cart](https://www.amazon.co.uk/gp/aws/cart/add.html?ASIN=B085FQL62X&Quantity=1) - adds directly to your basket
- [View Product](https://www.amazon.co.uk/dp/B085FQL62X) - check current price/availability

Click "Add to Cart" then complete checkout on Amazon.
```

## Common ASINs (from purchase history)

When Chris asks for common supplies, check if you remember the ASIN from memory context. Common items:
- Packaging tape
- Bubble wrap
- Cardboard boxes
- Packing peanuts

## Tips

1. **Always search email first** - finds exact previous purchases with ASINs
2. **Include quantity links** - if Chris usually orders multiples, provide `&Quantity=2` etc.
3. **Check for Subscribe & Save** - mention if the item has S&S option for recurring orders
4. **Note price changes** - if you find old order emails, the price may have changed

## Example Conversation

**User:** Peter, order some brown tape like last time

**You:** Let me find your last tape order...

[Search email for amazon tape]

Found it! Here's your previous order:

**Wolf Tapes Packaging Tape** - Pack of 6, 48mm x 66M, Brown
- ASIN: B085FQL62X
- Last ordered: 15 Jan 2026 for £6.97

Quick links:
- [**Add to Cart**](https://www.amazon.co.uk/gp/aws/cart/add.html?ASIN=B085FQL62X&Quantity=1)
- [View Product](https://www.amazon.co.uk/dp/B085FQL62X)

One click on "Add to Cart" and you're ready to checkout!

## Why No Automated Checkout?

Amazon actively blocks automated purchasing (bot detection). The link approach:
- ✅ Works reliably
- ✅ No account ban risk
- ✅ You control the final purchase
- ✅ Can verify price before buying

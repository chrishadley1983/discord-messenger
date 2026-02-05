---
name: hb-add-purchase
description: Record a new LEGO purchase in Hadley Bricks with ASIN lookup and optimal pricing
trigger:
  - "log purchase"
  - "bought"
  - "add purchase"
  - "record purchase"
  - "just bought"
  - "add this purchase"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks Add Purchase

## Purpose

Records a LEGO purchase in Hadley Bricks with full enrichment: ASIN lookup, competitive pricing, and optimal list price calculation. Creates BOTH purchase record AND inventory item in one operation.

**Uses the same batch-import flow as the automated email scanner.**

## Input Types

User can provide purchase info via:
1. **Text**: "Just bought 75192 for £480 from Vinted"
2. **Historical email**: "Add this purchase" (with email content/screenshot)
3. **Screenshot/image**: Vinted confirmation, eBay order, etc.

Extract from any input:
- Set number (required)
- Cost paid (required)
- Source: Vinted, eBay, FB Marketplace, etc.
- Seller/reference (optional)
- Date (optional, defaults to today)
- Condition (optional, defaults to New for Vinted)

## API Endpoints (via Hadley API)

**Base URL**: `http://172.19.64.1:8100`

### Step 1: Look up ASIN

```
GET http://172.19.64.1:8100/hb/lookup-asin?set_number=40448
```

Response:
```json
{
  "setNumber": "40448",
  "asin": "B08XY1234Z",
  "source": "catalog"
}
```

### Step 2: Get Competitive Pricing

```
GET http://172.19.64.1:8100/hb/competitive-pricing?asin=B08XY1234Z
```

Response:
```json
{
  "B08XY1234Z": {
    "buyBoxPrice": 24.99,
    "lowestNewPrice": 22.99,
    "salesRank": 1234
  }
}
```

### Step 3: Calculate List Price

Use `lowestNewPrice` or `buyBoxPrice` (whichever available):
- Subtract £0.01 to be just below competition
- Round DOWN to nearest .49 or .99

Examples:
- Buy box £54.99 → list at £54.49
- Buy box £54.50 → list at £53.99
- Buy box £55.20 → list at £54.99

### Step 4: Batch Import (Creates Purchase + Inventory)

```
POST http://172.19.64.1:8100/hb/batch-import
Content-Type: application/json

{
  "items": [
    {
      "source": "Vinted",
      "order_reference": "niciarab",
      "set_number": "40448",
      "set_name": "Vintage Car",
      "cost": 0.01,
      "purchase_date": "2026-01-25",
      "condition": "New",
      "payment_method": "Monzo Card",
      "amazon_asin": "B08XY1234Z",
      "list_price": 22.49
    }
  ],
  "automated": false,
  "storage_location": "TBC"
}
```

**Note**: `batch-import` creates BOTH the purchase record AND inventory item automatically. The `email_id` field is auto-generated for manual imports.

## Condition Rules

| Source | Condition | Rule |
|--------|-----------|------|
| Vinted | Always "New" | Vinted purchases treated as sealed |
| eBay | "New" if sealed keywords | Check for "sealed", "bnib", "new", "unopened", "misb" |
| eBay | "Used" otherwise | Default for eBay without sealed keywords |
| FB Marketplace | Ask user | Varies widely |

## Payment Method Defaults

| Source | Payment Method |
|--------|---------------|
| Vinted | Monzo Card |
| eBay | PayPal |
| FB Marketplace | Cash |
| LEGO Store | Credit Card |

## Execution Flow

1. **Parse input** - Extract set number, cost, source, date, seller
2. **Look up ASIN** - `GET /hb/lookup-asin?set_number=X`
3. **Get pricing** - `GET /hb/competitive-pricing?asin=X`
4. **Calculate list price** - Apply rounding rules
5. **Show confirmation** with ROI calculation
6. **On confirm** - `POST /hb/batch-import`

## Confirmation Format

```
📝 **Log Purchase?**

**Item:**
• 40448 Vintage Car - New
  Cost: £0.01 | Source: Vinted (niciarab)
  Date: 25 Jan 2026

**Enrichment:**
ASIN: B08XY1234Z
Buy box: £24.99
List price: £24.49

**Profit Analysis:**
Est. profit: £17.50 (1750% ROI) after fees

Create purchase + inventory?
```

## Success Format

```
✅ **Purchase Logged!**

• 40448 Vintage Car - £0.01 (Vinted)
  Date: 25 Jan 2026

**Inventory Created:**
ASIN: B08XY1234Z
List price: £24.49
Storage: TBC

💡 Remember to photograph and update storage location!
```

## Error Handling

**ASIN not found:**
```
📝 **Log Purchase?**

• 40448 Vintage Car - £0.01 (Vinted)

⚠️ No ASIN found - item will be created without Amazon listing price.
You can add ASIN manually later.

Continue?
```

**Pricing unavailable:**
```
📝 **Log Purchase?**

• 40448 Vintage Car - £0.01 (Vinted)
  ASIN: B08XY1234Z

⚠️ Could not fetch buy box price - will need manual pricing.

Continue?
```

**API error:**
```
⚠️ Could not reach Hadley Bricks API.

Details to log manually:
• 40448 Vintage Car - £0.01 - Vinted - 25 Jan 2026
```

## Multiple Items (Lot Purchase)

For lots, process each item through the enrichment flow:

```
📝 **Log Lot Purchase?**

**Items (3):**
• 21330 Home Alone - £155 → List £214.99 (39% ROI)
• 10497 Galaxy Explorer - £80 → List £119.49 (49% ROI)
• 40567 Forest Hideout - £25 → List £34.99 (40% ROI)

**Source:** Facebook Marketplace
**Total:** £260 for 3 items

**Combined Analysis:**
Est. revenue: £369.47
Est. profit: £52.30 (20% avg ROI)

Log all 3 items?
```

## Examples

**From text:**
User: "Just bought 10300 for £95 from Vinted"
→ Extract: set=10300, cost=95, source=Vinted, date=today

**From email screenshot:**
User: [image of Vinted confirmation]
→ OCR/parse: set number from title, cost, seller name, date

**Historical email:**
User: "Add this purchase from last week's email about the DeLorean"
→ Search context/memory for email details, extract purchase info

**Refunded item:**
User: "Log the 40448 I got for free - Vinted refunded but I kept it"
→ Extract: set=40448, cost=0, source=Vinted, note="refunded but kept"

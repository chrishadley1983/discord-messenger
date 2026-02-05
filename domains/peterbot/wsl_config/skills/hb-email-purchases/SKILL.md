---
name: hb-email-purchases
description: Automated import of LEGO purchases from email confirmations (Vinted, eBay)
trigger:
  - "import purchases from email"
  - "scan purchase emails"
  - "check for new purchases"
  - "email purchase import"
scheduled: true
conversational: true
channel: #ai-briefings
---

# Hadley Bricks Email Purchase Import

## Purpose

Automatically scans Gmail for Vinted and eBay purchase confirmation emails, then creates purchase + inventory records in Hadley Bricks with optimal pricing.

**Scheduled**: Runs at 02:17 UK daily (quiet hours - no user notification)
**Report to**: #ai-briefings (morning summary of overnight imports)

## API Endpoints

All endpoints require the Hadley Bricks service API key (`HADLEY_BRICKS_API_KEY` env var).

**Base URL**: `https://hadley-bricks-inventory-management.vercel.app`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/service/purchases/scan-emails` | GET | Scan Gmail for purchase emails |
| `/api/service/inventory/lookup-asin` | GET | Find Amazon ASIN for a set |
| `/api/service/amazon/competitive-summary` | GET | Get buy box / competitive pricing |
| `/api/service/purchases/batch-import` | POST | Create purchase + inventory records |

## Safety: First-Run Protection

**HARDCODED CUTOFF DATE: 1st February 2026**

The scan-emails endpoint will **only process emails dated after 1st Feb 2026**. This prevents accidentally importing all historical purchases on first run.

Emails before this date are silently ignored - they won't appear as candidates and won't be marked as processed.

## Execution Flow

### 1. Scan for New Purchases

```bash
curl -s -X GET "${HADLEY_BRICKS_URL}/api/service/purchases/scan-emails?days=7" \
  -H "x-api-key: ${HADLEY_BRICKS_API_KEY}"
```

Response includes candidates with:
- `source`: "Vinted" or "eBay"
- `order_reference`: Unique order ID
- `set_number`: Extracted from item name (may be null)
- `set_name`: Item name from email
- `cost`: Purchase price
- `purchase_date`: Date of purchase
- `suggested_condition`: "New" (Vinted) or "New"/"Used" (eBay based on keywords)
- `already_imported`: Boolean - skip if true

### 2. Enrich Each Candidate

For each candidate with `already_imported: false`:

**a) Validate/lookup set number if missing:**
If `set_number` is null, try to extract from `set_name` pattern matching.

**b) Look up ASIN:**
```bash
curl -s -X GET "${HADLEY_BRICKS_URL}/api/service/inventory/lookup-asin?setNumber=${SET_NUMBER}" \
  -H "x-api-key: ${HADLEY_BRICKS_API_KEY}"
```

**c) Get buy box pricing:**
```bash
curl -s -X GET "${HADLEY_BRICKS_URL}/api/service/amazon/competitive-summary?asins=${ASIN}" \
  -H "x-api-key: ${HADLEY_BRICKS_API_KEY}"
```

**d) Calculate list price:**
- Use `lowestNewPrice` or `buyBoxPrice` (whichever is available)
- Subtract £0.01 to be just below
- Round DOWN to nearest .49 or .99

Example: Buy box £54.99 → list at £54.49
Example: Buy box £54.50 → list at £53.99
Example: Buy box £55.20 → list at £54.99

### 3. Batch Import

```bash
curl -s -X POST "${HADLEY_BRICKS_URL}/api/service/purchases/batch-import" \
  -H "x-api-key: ${HADLEY_BRICKS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "source": "Vinted",
        "order_reference": "12345",
        "email_id": "abc123def456",
        "email_subject": "You bought LEGO Wildflower Bouquet",
        "email_date": "2026-02-03T10:30:00Z",
        "set_number": "10313",
        "set_name": "Wildflower Bouquet",
        "cost": 25.00,
        "purchase_date": "2026-02-03",
        "condition": "New",
        "payment_method": "Monzo Card",
        "amazon_asin": "B00BLHX6J8",
        "list_price": 44.99
      }
    ],
    "skip_items": [
      {
        "email_id": "xyz789",
        "source": "eBay",
        "email_subject": "Order confirmed: Mixed LEGO lot",
        "item_name": "Mixed LEGO lot",
        "cost": 45.00,
        "skip_reason": "no_set_number"
      }
    ],
    "automated": true,
    "storage_location": "TBC"
  }'
```

**Note:** The `email_id` field is **required** for deduplication. Items without valid set numbers should be passed via `skip_items` to prevent them from appearing in future scans.

## Condition Rules

| Source | Condition | Rule |
|--------|-----------|------|
| Vinted | Always "New" | Vinted purchases are treated as sealed |
| eBay | "New" if sealed keywords | Check for "sealed", "bnib", "new", "unopened", "misb" |
| eBay | "Used" otherwise | Default for eBay without sealed keywords |

## Payment Method Defaults

| Source | Payment Method |
|--------|---------------|
| Vinted | Monzo Card |
| eBay | PayPal |

## Output Format

### Scheduled Run (No Activity)
```
NO_REPLY
```

### Scheduled Run (Imports Found)
```
**Overnight Purchase Import** - 3 Feb 2026

Scanned 7 days of emails. Imported 3 new purchases:

**Imported:**
• 10313 Wildflower Bouquet - £25.00 → List £44.99 (80% ROI)
• 75337 AT-TE Walker - £89.00 → List £134.49 (51% ROI)
• 21330 Home Alone - £155.00 → List £214.99 (39% ROI)

**Summary:**
Total invested: £269.00
Expected revenue: £394.47
Est. profit: £68.30 (25% avg ROI)

All items added to inventory with storage: TBC
```

### Scheduled Run (Errors)
```
**Overnight Purchase Import** - 3 Feb 2026

**Imported:** 2 items (£144.00 invested)

**Failed:**
• Order #67890 - Could not determine set number from "LEGO bundle mixed parts"
• Order #12345 - No ASIN found for set 99999

Review failed items manually in Gmail.
```

### Conversational Trigger
```
**Email Purchase Scan** - 3 Feb 2026

Found 2 new purchases in last 7 days:

**Ready to import:**
• 10313 Wildflower Bouquet (Vinted) - £25.00
  ASIN: B00BLHX6J8 | List price: £44.99

• 75337 AT-TE Walker (Vinted) - £89.00
  ASIN: B09RD3FGF3 | List price: £134.49

Import these purchases? (yes/no)
```

## Error Handling

- **API unreachable**: Log error, skip import, report in morning
- **ASIN not found**: Still create purchase, skip list_price
- **Set number unclear**: Skip item, list in failed report
- **Duplicate order_reference**: API returns already_imported: true, skip

## Environment Variables Required

```bash
HADLEY_BRICKS_API_KEY=hb_sk_...  # Service API key with write permission
HADLEY_BRICKS_URL=https://hadley-bricks-inventory-management.vercel.app
```

## Testing

Manual trigger: "import purchases from email" or "scan purchase emails"

This will show candidates and ask for confirmation before importing.

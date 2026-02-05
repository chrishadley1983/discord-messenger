---
name: hb-add-inventory
description: Add inventory item WITHOUT a purchase record (received items, gifts, samples)
trigger:
  - "add inventory"
  - "add stock"
  - "add to inventory"
  - "new inventory"
  - "received"
  - "got given"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks Add Inventory (No Purchase)

## Purpose

Adds inventory items that DON'T have an associated purchase record:
- Items received from suppliers (not yet invoiced)
- Gifts or samples
- Items from existing stock not in system
- Transfers from personal collection

**For normal purchases, use `hb-add-purchase` instead** - it creates both purchase AND inventory via batch-import.

## When to Use This Skill

| Scenario | Use This Skill? |
|----------|----------------|
| Bought something | ❌ No - use hb-add-purchase |
| Received from supplier, invoice pending | ✅ Yes |
| Gift / sample / freebie | ✅ Yes |
| Found in storage, not in system | ✅ Yes |
| Personal collection → business | ✅ Yes |

## API Endpoints

**Base URL**: `https://hadley-bricks-inventory-management.vercel.app`

### Step 1: Look up ASIN (optional)

```bash
GET /api/service/inventory/lookup-asin?setNumber=75192
```

### Step 2: Get Competitive Pricing (optional)

```bash
GET /api/service/amazon/competitive-summary?asins=B0XXXXXX
```

### Step 3: Create Inventory Item

```bash
POST /api/inventory
Content-Type: application/json
x-api-key: ${HADLEY_BRICKS_API_KEY}

{
  "set_number": "75192",
  "item_name": "Millennium Falcon",
  "condition": "New",
  "status": "BACKLOG",
  "source": "Gift",
  "cost": 0,
  "amazon_asin": "B0XXXXXX",
  "listing_value": 599.99,
  "storage_location": "A1-B2",
  "notes": "Birthday gift from Sarah"
}
```

**Required fields:**
- `set_number` - LEGO set number

**Optional fields:**
- `item_name` - Auto-populated from set if blank
- `condition` - "New" or "Used" (default: New)
- `status` - BACKLOG, LISTED, NOT YET RECEIVED (default: BACKLOG)
- `source` - Where it came from (Gift, Sample, Personal, etc.)
- `cost` - Cost basis (0 for gifts)
- `amazon_asin` - For Amazon listing
- `listing_value` - Target list price
- `storage_location` - Storage code
- `notes` - Additional notes

## Execution Flow

1. **Parse input** - Extract set number, source, any notes
2. **Look up ASIN** (if listing planned)
3. **Get pricing** (if listing planned)
4. **Show confirmation**
5. **Create inventory** via POST /api/inventory

## Output Format

**Confirmation:**
```
📦 **Add to Inventory?**

**Item:**
• 75192 Millennium Falcon - New
  Source: Gift (Birthday from Sarah)
  Cost basis: £0

**Enrichment:**
ASIN: B075SDMMMV
Suggested list price: £599.99

**Current Stock:**
Already have 0 of this set

Add to inventory?
```

**Success:**
```
✅ **Added to Inventory!**

• 75192 Millennium Falcon - New
  Source: Gift | Cost: £0
  ASIN: B075SDMMMV
  List price: £599.99
  Storage: TBC

📸 Remember to photograph before listing!
```

## Examples

**Gift:**
User: "Got given a 75192 for my birthday"
→ set=75192, source=Gift, cost=0

**Supplier shipment:**
User: "Received 3x 10300 from BrickLink seller, invoice coming"
→ set=10300, qty=3, source=BrickLink, status=NOT YET RECEIVED

**Personal collection:**
User: "Add my personal 21330 to business inventory, I paid £180 for it"
→ set=21330, source=Personal Collection, cost=180

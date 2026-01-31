# Hadley Bricks Inventory Skill - Complete Documentation & Code

**Skill Name:** hadley-bricks-inventory  
**Location:** `/root/clawd/skills/hadley-bricks-inventory/`  
**Purpose:** Add Lego purchases and inventory items to Hadley Bricks Supabase database  
**Created:** January 2026  
**Status:** Active

---

## 📋 Skill Overview

This skill automates the process of logging Lego purchases and inventory into the Hadley Bricks application database. It handles:

1. ✅ **Purchase logging** - Record purchase details (cost, source, date, payment method)
2. ✅ **Inventory tracking** - Add items with set numbers, conditions, costs, and statuses
3. ✅ **Image uploads** - Store photos of purchases in Supabase storage
4. ✅ **Mileage tracking** - Calculate and log travel expenses (HMRC compliant)
5. ✅ **Cost allocation** - Distribute purchase cost across multiple items
6. ✅ **Pricing research** - Look up Amazon ASINs and profitability via SellerAmp

---

## 🚀 When to Use This Skill

**Trigger phrases from Chris:**
- "I bought some Lego..."
- "Adding inventory..."
- "Picked up a bundle at Facebook Marketplace..."
- "Found these sets on Vinted..."
- "I need to log a purchase..."
- "Track mileage for pickup..."

**Key indicators:**
- Lego purchase mentioned with quantity/sets
- Items to add to inventory
- Photos of items provided
- Cost and source information given

---

## 🛠️ Core Workflow

### STEP 1: Gather Information

**Required:**
- Item details (set numbers, names, condition)
- Total purchase cost
- Purchase date (⚠️ **ALWAYS verify year with `date` command!**)

**Optional:**
- Source (Facebook Marketplace, eBay, Vinted, Car Boot)
- Payment method (Cash, Card, PayPal)
- Pickup postcode (for mileage calculation)
- Photos of items
- Target listing platform (Amazon/eBay/BrickLink)
- Amazon ASIN (if listing on Amazon)

### STEP 2: Identify Sets from Photos

When photos provided:
1. Look at box art, instructions, distinctive parts
2. Identify Lego set numbers
3. Present findings for confirmation
4. **Never assume** — ask for clarification if unsure

### STEP 3: Look Up Pricing (If Amazon)

Use **SellerAmp SAS** for Amazon profitability analysis:

**Steps:**
1. Go to https://sas.selleramp.com/
2. Search by set number (e.g., "40487")
3. Record:
   - ASIN (e.g., B09BRFBR36)
   - Buy Box price (current selling price)
   - Max Cost (50% of net after fees)
   - Est. Sales/month

**Analysis:**
```
COG% (Cost of Goods %) = Our Cost ÷ Buy Box × 100
- 40-44% = healthy margin ✅
- 50%+ = tight/breakeven ⚠️
```

### STEP 4: Allocate Costs (Multi-Item)

For bundles, split cost proportionally by estimated resale value:

```
| Set   | Name              | Est Value | % Share | Allocated Cost |
| ----- | ----------------- | --------- | ------- | -------------- |
| 42056 | Porsche 911 GT3   | £180      | 42%     | £50            |
| 75105 | Millennium Falcon | £70       | 16%     | £28            |
| Total | -                 | £420      | 100%    | £120           |
```

### STEP 5: Create Database Records

**Order matters:** Purchase → Mileage → Inventory Items → Images

Then **screenshot in UI** to confirm.

---

## 🗄️ Database Schema

### Key Constants
```
User ID: 4b6e94b4-661c-4462-9d14-b21df7d51e5b
Supabase Project: modjoikyuhqzouxvieua
Storage Bucket: images
HMRC Mileage Rate: £0.45/mile
```

### purchases Table

```sql
CREATE TABLE purchases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,  -- Always: 4b6e94b4-661c-4462-9d14-b21df7d51e5b
  purchase_date DATE NOT NULL,
  short_description TEXT NOT NULL,  -- Brief title, e.g., "Lego Bundle RH11"
  cost NUMERIC(10,2) NOT NULL,      -- Total cost in £
  source TEXT,                      -- Facebook Marketplace, eBay, Vinted, etc.
  payment_method TEXT,              -- Cash, Card, PayPal
  description TEXT,                 -- Detailed notes
  image_url TEXT,                   -- ⚠️ NOT USED! Use purchase_images table instead
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Insert Example:**
```sql
INSERT INTO purchases (
  user_id, purchase_date, short_description, cost, source, payment_method, description
) VALUES (
  '4b6e94b4-661c-4462-9d14-b21df7d51e5b',
  '2026-01-27',
  'Lego Bundle Facebook Marketplace',
  120.00,
  'Facebook Marketplace',
  'Cash',
  'Mixed bundle - Technic and Star Wars sets'
) RETURNING id;
```

### inventory_items Table

```sql
CREATE TABLE inventory_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  set_number TEXT NOT NULL,         -- Lego set number or 'BULK'
  item_name TEXT,                   -- Set name, e.g., "Technic Porsche 911 GT3"
  condition TEXT,                   -- **MUST be 'New' or 'Used'**
  cost NUMERIC(10,2),               -- Allocated purchase cost
  status TEXT DEFAULT 'BACKLOG',    -- Status (see below)
  purchase_id UUID,                 -- **ALWAYS link to purchase!**
  listing_platform TEXT,            -- amazon, ebay, bricklink, or NULL
  listing_value NUMERIC(10,2),      -- Expected sale price
  amazon_asin TEXT,                 -- **REQUIRED if listing_platform = 'amazon'**
  storage_location TEXT,            -- Where stored
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Valid Status Values:**
- `BACKLOG` ← **Use this for new purchases**
- `NOT YET RECEIVED` (default)
- `IN_PROGRESS`
- `LISTED`
- `SOLD`
- `RETURNED`

**Insert Examples:**

Standard (no listing yet):
```sql
INSERT INTO inventory_items (
  user_id, set_number, item_name, condition, cost, status, purchase_id
) VALUES (
  '4b6e94b4-661c-4462-9d14-b21df7d51e5b',
  '42056',
  'Technic Porsche 911 GT3 RS',
  'Used',
  50.00,
  'BACKLOG',
  '<purchase_id>'
);
```

Amazon listing (MUST include ASIN):
```sql
INSERT INTO inventory_items (
  user_id, set_number, item_name, condition, cost, status,
  listing_platform, listing_value, amazon_asin, purchase_id
) VALUES (
  '4b6e94b4-661c-4462-9d14-b21df7d51e5b',
  '40487',
  'Ideas Sailboat Adventure',
  'New',
  15.55,
  'BACKLOG',
  'amazon',
  36.99,
  'B09BRFBR36',
  '<purchase_id>'
);
```

Bulk lot (no set number):
```sql
INSERT INTO inventory_items (
  user_id, set_number, item_name, condition, cost, status, listing_value
) VALUES (
  '4b6e94b4-661c-4462-9d14-b21df7d51e5b',
  'BULK',
  'Mixed Lego Lot - Various',
  'Used',
  30.00,
  'BACKLOG',
  75.00
);
```

### mileage_tracking Table

```sql
CREATE TABLE mileage_tracking (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  purchase_id UUID,                 -- FK to purchase (optional)
  tracking_date DATE NOT NULL,
  destination_postcode TEXT NOT NULL,  -- Pickup location
  miles_travelled NUMERIC(6,1) NOT NULL,  -- Round trip
  amount_claimed NUMERIC(10,2) NOT NULL,  -- miles × £0.45
  reason TEXT NOT NULL,             -- Purpose of trip
  expense_type TEXT DEFAULT 'mileage',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Insert Example:**
```sql
INSERT INTO mileage_tracking (
  user_id, purchase_id, tracking_date, destination_postcode,
  miles_travelled, amount_claimed, reason, expense_type
) VALUES (
  '4b6e94b4-661c-4462-9d14-b21df7d51e5b',
  '<purchase_id>',
  '2026-01-27',
  'RH11 7BZ',
  56,
  25.20,
  'Collecting Lego Bundle from Crawley',
  'mileage'
);
```

### purchase_images Table

⚠️ **This is how the app displays photos — NOT the `image_url` field!**

```sql
CREATE TABLE purchase_images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  purchase_id UUID NOT NULL,        -- FK to purchases
  storage_path TEXT NOT NULL,       -- Path in Supabase storage
  public_url TEXT NOT NULL,         -- Full public URL
  filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,          -- image/jpeg, image/png
  file_size INTEGER,                -- Bytes
  caption TEXT,                     -- Optional description
  sort_order INTEGER DEFAULT 0,     -- Display order
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Storage Path Format:**
```
images/purchases/{purchase_id}/{filename}
```

**Public URL Format:**
```
https://modjoikyuhqzouxvieua.supabase.co/storage/v1/object/public/images/purchases/{purchase_id}/{filename}
```

**Insert Example:**
```sql
INSERT INTO purchase_images (
  user_id, purchase_id, storage_path, public_url, filename, mime_type
) VALUES (
  '4b6e94b4-661c-4462-9d14-b21df7d51e5b',
  '<purchase_id>',
  'images/purchases/<purchase_id>/bundle-photo.jpg',
  'https://modjoikyuhqzouxvieua.supabase.co/storage/v1/object/public/images/purchases/<purchase_id>/bundle-photo.jpg',
  'bundle-photo.jpg',
  'image/jpeg'
);
```

---

## 📝 Complete Insert Sequence Example

```sql
-- STEP 1: Create Purchase Record
INSERT INTO purchases (
  user_id, purchase_date, short_description, cost, source, payment_method, description
) VALUES (
  '4b6e94b4-661c-4462-9d14-b21df7d51e5b',
  '2026-01-27',
  'Facebook Marketplace Lego Bundle',
  120.00,
  'Facebook Marketplace',
  'Cash',
  'Mixed bundle: Technic Porsche, Star Wars, Ideas Sailboat'
) RETURNING id;
-- Returns: <purchase_id>

-- STEP 2: Create Mileage Record (if applicable)
INSERT INTO mileage_tracking (
  user_id, purchase_id, tracking_date, destination_postcode,
  miles_travelled, amount_claimed, reason, expense_type
) VALUES (
  '4b6e94b4-661c-4462-9d14-b21df7d51e5b',
  '<purchase_id>',
  '2026-01-27',
  'RH11 7BZ',
  56,
  25.20,
  'Collecting Lego Bundle',
  'mileage'
);

-- STEP 3: Create Inventory Items
INSERT INTO inventory_items (
  user_id, set_number, item_name, condition, cost, status, purchase_id
) VALUES
  ('4b6e94b4-661c-4462-9d14-b21df7d51e5b', '42056', 'Technic Porsche 911 GT3', 'Used', 50.00, 'BACKLOG', '<purchase_id>'),
  ('4b6e94b4-661c-4462-9d14-b21df7d51e5b', '75105', 'Star Wars Millennium Falcon', 'Used', 35.00, 'BACKLOG', '<purchase_id>'),
  ('4b6e94b4-661c-4462-9d14-b21df7d51e5b', '40487', 'Ideas Sailboat Adventure', 'New', 35.00, 'BACKLOG', '<purchase_id>');

-- STEP 4: Upload Image to Storage
-- curl -X POST "https://modjoikyuhqzouxvieua.supabase.co/storage/v1/object/images/purchases/<purchase_id>/photo.jpg" \
--   -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
--   -H "Content-Type: image/jpeg" \
--   --data-binary @photo.jpg

-- STEP 5: Create Image Record
INSERT INTO purchase_images (
  user_id, purchase_id, storage_path, public_url, filename, mime_type
) VALUES (
  '4b6e94b4-661c-4462-9d14-b21df7d51e5b',
  '<purchase_id>',
  'images/purchases/<purchase_id>/bundle-photo.jpg',
  'https://modjoikyuhqzouxvieua.supabase.co/storage/v1/object/public/images/purchases/<purchase_id>/bundle-photo.jpg',
  'bundle-photo.jpg',
  'image/jpeg'
);
```

---

## 🎯 Usage Patterns

### Pattern 1: Single Item Purchase

One set, one purchase. Simple.

```sql
INSERT INTO purchases (...) VALUES (...) RETURNING id;  -- Purchase
INSERT INTO inventory_items (...) VALUES (...);         -- 1 item
-- Optional: mileage + images
```

### Pattern 2: Multi-Item Bundle

Multiple sets in one purchase. **Allocate costs proportionally.**

```
Total Cost: £120
Allocated:
- Set A (est. £80): £60 (50%)
- Set B (est. £40): £30 (25%)
- Set C (est. £40): £30 (25%)
```

```sql
INSERT INTO purchases (...) VALUES (...) RETURNING id;
INSERT INTO mileage_tracking (...) VALUES (...);  -- If pickup
INSERT INTO inventory_items (...) VALUES         -- 3 items
  (..., cost=60, ...), 
  (..., cost=30, ...),
  (..., cost=30, ...);
INSERT INTO purchase_images (...) VALUES (...);
```

### Pattern 3: Vinted/eBay Multiple Transactions

**Each transaction is a separate purchase** (different costs/dates/sellers):

```
Item 1 from Seller A: £15 (separate purchase record)
Item 2 from Seller B: £20 (separate purchase record)
Item 3 from Seller C: £25 (separate purchase record)
```

```sql
-- Purchase 1
INSERT INTO purchases (..., cost=15, ...) RETURNING id;  -- id_1
INSERT INTO inventory_items (..., purchase_id=id_1, cost=15, ...);

-- Purchase 2
INSERT INTO purchases (..., cost=20, ...) RETURNING id;  -- id_2
INSERT INTO inventory_items (..., purchase_id=id_2, cost=20, ...);

-- Purchase 3
INSERT INTO purchases (..., cost=25, ...) RETURNING id;  -- id_3
INSERT INTO inventory_items (..., purchase_id=id_3, cost=25, ...);
```

### Pattern 4: Bulk Lot (No Set Numbers)

Mixed items without individual set numbers:

```sql
INSERT INTO inventory_items (
  ..., set_number='BULK', item_name='Mixed Lego Lot',
  listing_value=100.00, ...
);
```

### Pattern 5: Amazon FBA Items

When listing on Amazon:

1. ✅ Look up ASIN in SellerAmp
2. ✅ Verify profitability (COG% < 50%)
3. ✅ Set `listing_platform = 'amazon'`
4. ✅ Set `amazon_asin` (REQUIRED!)
5. ✅ Set `listing_value` to target price

```sql
INSERT INTO inventory_items (
  ...,
  set_number='40487',
  item_name='Ideas Sailboat Adventure',
  condition='New',
  cost=15.55,
  status='BACKLOG',
  listing_platform='amazon',
  listing_value=36.99,
  amazon_asin='B09BRFBR36',
  purchase_id='<purchase_id>'
);
```

---

## ⚠️ Common Mistakes to Avoid

### 1. Wrong Year in Date
❌ Insert '2026-01-27' when it's actually 2025
✅ **Always run `date` before inserting any date!**

### 2. Missing BACKLOG Status
❌ Leave status as default 'NOT YET RECEIVED'
✅ **Always set `status = 'BACKLOG'` for new purchases**

### 3. Images in Wrong Table
❌ Try to set `image_url` field
✅ **Use `purchase_images` table + Supabase storage**

### 4. Missing purchase_id Link
❌ Create inventory items without linking to purchase
✅ **Always set `purchase_id` to the purchase record**

### 5. Condition Typo
❌ Use 'New', 'Used', 'new', 'USED'
✅ **Exactly 'New' or 'Used'** (capital N/U)

### 6. Missing ASIN for Amazon
❌ Set `listing_platform = 'amazon'` but forget `amazon_asin`
✅ **`amazon_asin` is REQUIRED if `listing_platform = 'amazon'`**

### 7. Column Name Mismatch
❌ Use `name` or `purchase_cost` or `image_url`
✅ **Correct columns:**
- `item_name` (not `name`)
- `cost` (not `purchase_cost`)
- `purchase_images` table (not `image_url` field)

### 8. Mileage Calculation
❌ Insert miles as one-way
✅ **Always round-trip miles** and multiply by £0.45

---

## 📊 SellerAmp SAS Pricing Analysis

**When to use:** Every Amazon FBA listing

**Steps:**
1. Go to https://sas.selleramp.com/
2. Search set number (e.g., "40487")
3. Extract:
   - **ASIN** → `amazon_asin` column
   - **Buy Box** → `listing_value`
   - **Max Cost** → Verify our cost fits (should be < 50% of Buy Box)

**Example Table:**
```
| Set   | Name               | ASIN       | Our Cost | Buy Box | Max Cost | COG% | Status |
|-------|--------------------|------------|----------|---------|----------|------|--------|
| 40487 | Sailboat Adventure | B09BRFBR36 | £15.55   | £36.66  | £18.33   | 42%  | ✅     |
| 60239 | Police Patrol Car  | B07FNW8PHF | £9.93    | £24.56  | £12.28   | 40%  | ✅     |
| 75105 | Millennium Falcon  | B00NIQLZGQ | £55.00   | £95.00  | £47.50   | 58%  | ⚠️     |
```

**Healthy COG%:** 40-44% = good margin  
**Tight COG%:** 50%+ = breakeven/loss

---

## 🔐 Environment & Credentials

**Setup:**
```bash
source /etc/profile.d/supabase.sh
```

**Env Variables:**
```
SUPABASE_DB_HOST=modjoikyuhqzouxvieua.supabase.co
SUPABASE_DB_PASSWORD=<service-role-key>
SUPABASE_SERVICE_KEY=<service-role-key>
```

---

## ✅ Verification Checklist

After inserting records, verify in the app UI:

- [ ] Purchase shows with correct date and cost
- [ ] All items linked and display under purchase
- [ ] Item statuses all show "BACKLOG"
- [ ] Images visible in "Photos & Receipts" section
- [ ] Mileage shows in expense tracking (if applicable)
- [ ] Costs correctly allocated across items
- [ ] Amazon ASIN displays (if applicable)

---

## 📚 Files & References

**Skill Location:** `/root/clawd/skills/hadley-bricks-inventory/`

**Files:**
- `SKILL.md` - This skill documentation
- `references/schema.md` - Full database schema reference

**Related:**
- App: https://hadley-bricks-inventory-management.vercel.app/
- Supabase Project: https://app.supabase.com/
- SellerAmp SAS: https://sas.selleramp.com/

---

**Last Updated:** 2026-01-28  
**Maintained by:** Peter (AI Assistant)  
**Status:** Active & Tested

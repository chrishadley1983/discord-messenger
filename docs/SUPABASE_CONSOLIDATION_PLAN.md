# Supabase Project Consolidation Plan

## Executive Summary

**Goal:** Reduce Supabase costs from ~$45/month to $25/month by consolidating three active projects into one database using separate schemas.

**Current State:**
| Project | Status | Monthly Cost | Row Count |
|---------|--------|--------------|-----------|
| Inventory Management App | Active | ~$5.24 | ~170,000 |
| japan-travel-planner | Active (unused) | ~$5.24 | 0 |
| finance-tracker | Active | ~$5.24 | ~7,000 |
| family-meal-planner | Paused | $0 | N/A |
| familyfuel-prod | Paused | $0 | N/A |

**Target State:**
- Single "Inventory Management App" project with 3 schemas: `public`, `finance`, `peterbot`
- japan-travel-planner: Paused (can delete later if not needed)
- **Projected savings:** ~$10.48/month → total ~$30/month (with Pro Plan base)

---

## Pre-Migration Checklist

### 1. Full Data Backups (CRITICAL)

Before any migration work:

```bash
# Export from finance-tracker
pg_dump "postgresql://postgres.[project-ref]:[password]@aws-0-eu-central-2.pooler.supabase.com:6543/postgres" \
  --schema=public \
  --no-owner \
  --no-privileges \
  -f finance_tracker_backup_$(date +%Y%m%d).sql

# Export from Inventory Management App (current state)
pg_dump "postgresql://postgres.[project-ref]:[password]@aws-0-eu-west-1.pooler.supabase.com:6543/postgres" \
  --schema=public \
  --no-owner \
  --no-privileges \
  -f inventory_app_backup_$(date +%Y%m%d).sql
```

Store backups in:
- Local drive
- Google Drive / OneDrive
- Git repo (excluding sensitive data)

---

## Phase 1: Pause japan-travel-planner (Immediate Cost Savings)

**Estimated savings:** ~$5.24/month

### Steps:
1. Verify no active usage:
   - Check `auth.users` count (currently 0)
   - Verify no recent API calls in logs

2. Pause the project via Supabase Dashboard or API:
   ```
   Project: nvsjlktgtvhzmmirieel
   Action: Pause
   ```

3. **Verification:**
   - Confirm project status shows "INACTIVE"
   - Billing page shows $0 compute for this project

---

## Phase 2: Create New Schemas in Target Database

**Target Project:** `modjoikyuhqzouxvieua` (Inventory Management App)

### 2.1 Create Finance Schema

```sql
-- Migration: 001_create_finance_schema.sql
-- Create dedicated schema for finance tracker
CREATE SCHEMA IF NOT EXISTS finance;

-- Grant permissions to authenticated users
GRANT USAGE ON SCHEMA finance TO authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA finance TO authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA finance TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA finance GRANT ALL ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA finance GRANT ALL ON SEQUENCES TO authenticated;

-- Also allow service_role full access
GRANT ALL ON SCHEMA finance TO service_role;
```

### 2.2 Create Peterbot Schema

The Discord-Messenger/Peterbot tables are already in the `public` schema of the Inventory Management App, so they can stay there OR be moved to a dedicated schema for cleaner separation.

**Recommendation:** Keep Peterbot tables in `public` schema since they're already there and integrated.

Current Peterbot tables in Inventory Management App:
- `reminders` (10 rows)
- `nutrition_logs` (83 rows)
- `knowledge_items` (2,835 rows)
- `knowledge_chunks` (2,882 rows)
- `knowledge_connections` (0 rows)
- `purchase_limits` (3 rows)
- `purchase_log` (0 rows)
- `browser_action_log` (0 rows)
- `browser_sessions` (0 rows)
- `garmin_daily_summary` (10 rows)
- `garmin_sleep` (9 rows)
- `weight_readings` (9 rows)
- `meal_favourites` (4 rows)
- `meal_presets` (3 rows)
- `youtube_shown_videos` (30 rows)

**No migration needed for Peterbot** - already in target database!

---

## Phase 3: Migrate Finance Tracker Data

### 3.1 Schema Translation

The Finance Tracker tables need to be recreated in the `finance` schema:

#### Core Tables to Migrate:

| Source Table (public) | Target Table (finance) | Rows |
|-----------------------|------------------------|------|
| accounts | finance.accounts | 14 |
| categories | finance.categories | 40 |
| category_groups | finance.category_groups | 12 |
| category_mappings | finance.category_mappings | 31 |
| transactions | finance.transactions | 2,790 |
| budgets | finance.budgets | 2,148 |
| wealth_snapshots | finance.wealth_snapshots | 768 |
| imported_transaction_hashes | finance.imported_transaction_hashes | 1,095 |
| import_sessions | finance.import_sessions | 22 |
| import_formats | finance.import_formats | 5 |
| fire_parameters | finance.fire_parameters | 4 |
| fire_scenarios | finance.fire_scenarios | 4 |
| fire_inputs | finance.fire_inputs | 1 |
| planning_sections | finance.planning_sections | 5 |
| planning_notes | finance.planning_notes | 20 |
| ai_mapping_cache | finance.ai_mapping_cache | 1 |
| ai_usage_tracking | finance.ai_usage_tracking | 7 |
| category_corrections | finance.category_corrections | 0 |
| investment_valuations | finance.investment_valuations | 0 |
| home_costs | finance.home_costs | 0 |
| home_costs_settings | finance.home_costs_settings | 0 |
| mtd_export_history | finance.mtd_export_history | 0 |

### 3.2 Migration Script

```sql
-- Migration: 002_migrate_finance_tables.sql
-- Run this on the TARGET database (Inventory Management App)

-- First, create the ENUM types in finance schema
CREATE TYPE finance.account_type AS ENUM ('current', 'savings', 'pension', 'isa', 'investment', 'property', 'credit', 'other', 'tracking');
CREATE TYPE finance.match_type AS ENUM ('exact', 'contains', 'regex');
CREATE TYPE finance.categorisation_source AS ENUM ('manual', 'rule', 'ai', 'import');
CREATE TYPE finance.import_status AS ENUM ('pending', 'processing', 'completed', 'failed');

-- Create category_groups first (no dependencies)
CREATE TABLE finance.category_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    display_order INTEGER DEFAULT 0,
    colour TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Create accounts
CREATE TABLE finance.accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    type finance.account_type NOT NULL,
    provider TEXT NOT NULL,
    hsbc_account_id TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    investment_provider TEXT,
    investment_type TEXT,
    notes TEXT,
    icon TEXT,
    color TEXT,
    sort_order INTEGER DEFAULT 0,
    is_archived BOOLEAN DEFAULT false,
    include_in_net_worth BOOLEAN DEFAULT true,
    last_import_at TIMESTAMPTZ,
    opening_balance NUMERIC DEFAULT 0,
    exclude_from_snapshots BOOLEAN DEFAULT false
);

-- Create categories
CREATE TABLE finance.categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    group_name TEXT NOT NULL,
    is_income BOOLEAN DEFAULT false,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    exclude_from_totals BOOLEAN DEFAULT false,
    group_id UUID REFERENCES finance.category_groups(id),
    colour TEXT
);

-- Create category_mappings
CREATE TABLE finance.category_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern TEXT NOT NULL,
    category_id UUID REFERENCES finance.categories(id),
    match_type finance.match_type DEFAULT 'exact',
    confidence NUMERIC DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT now(),
    is_system BOOLEAN DEFAULT false,
    notes TEXT
);

-- Create transactions
CREATE TABLE finance.transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES finance.accounts(id),
    date DATE NOT NULL,
    amount NUMERIC NOT NULL,
    description TEXT NOT NULL,
    category_id UUID REFERENCES finance.categories(id),
    categorisation_source finance.categorisation_source DEFAULT 'manual',
    hsbc_transaction_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    needs_review BOOLEAN DEFAULT false,
    is_validated BOOLEAN DEFAULT false
);

-- Create budgets
CREATE TABLE finance.budgets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id UUID REFERENCES finance.categories(id),
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    amount NUMERIC NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Create wealth_snapshots
CREATE TABLE finance.wealth_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    account_id UUID REFERENCES finance.accounts(id),
    balance NUMERIC NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Create import_formats
CREATE TABLE finance.import_formats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    is_system BOOLEAN DEFAULT false,
    column_mapping JSONB NOT NULL,
    date_format TEXT DEFAULT 'DD/MM/YYYY',
    decimal_separator TEXT DEFAULT '.' CHECK (decimal_separator IN ('.', ',')),
    has_header BOOLEAN DEFAULT true,
    skip_rows INTEGER DEFAULT 0,
    amount_in_single_column BOOLEAN DEFAULT true,
    amount_column TEXT,
    debit_column TEXT,
    credit_column TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    use_count INTEGER DEFAULT 0,
    sample_headers JSONB
);

-- Create import_sessions
CREATE TABLE finance.import_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    format_id UUID REFERENCES finance.import_formats(id),
    account_id UUID REFERENCES finance.accounts(id),
    status finance.import_status DEFAULT 'pending',
    total_rows INTEGER DEFAULT 0,
    imported_count INTEGER DEFAULT 0,
    duplicate_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    error_details JSONB,
    raw_data JSONB,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Create imported_transaction_hashes
CREATE TABLE finance.imported_transaction_hashes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID REFERENCES finance.transactions(id),
    hash TEXT NOT NULL,
    import_session_id UUID REFERENCES finance.import_sessions(id),
    source_row JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Create fire_parameters
CREATE TABLE finance.fire_parameters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_name TEXT UNIQUE NOT NULL,
    annual_spend NUMERIC NOT NULL,
    withdrawal_rate NUMERIC NOT NULL,
    expected_return NUMERIC NOT NULL,
    retirement_age INTEGER NOT NULL,
    state_pension_age INTEGER NOT NULL,
    state_pension_amount NUMERIC NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Create fire_scenarios
CREATE TABLE finance.fire_scenarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    annual_spend NUMERIC NOT NULL,
    withdrawal_rate NUMERIC DEFAULT 4.00,
    expected_return NUMERIC DEFAULT 7.00,
    inflation_rate NUMERIC DEFAULT 2.50,
    retirement_age INTEGER,
    state_pension_age INTEGER DEFAULT 67,
    state_pension_annual NUMERIC DEFAULT 11500,
    is_default BOOLEAN DEFAULT false,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Create fire_inputs
CREATE TABLE finance.fire_inputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    current_age INTEGER NOT NULL,
    target_retirement_age INTEGER,
    current_portfolio_value NUMERIC,
    annual_income NUMERIC,
    annual_savings NUMERIC,
    include_state_pension BOOLEAN DEFAULT true,
    partner_state_pension BOOLEAN DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT now(),
    exclude_property_from_fire BOOLEAN DEFAULT true,
    annual_spend NUMERIC DEFAULT 50000,
    withdrawal_rate NUMERIC DEFAULT 4,
    expected_return NUMERIC DEFAULT 7,
    date_of_birth DATE,
    normal_fire_spend NUMERIC DEFAULT 55000,
    fat_fire_spend NUMERIC DEFAULT 65000
);

-- Create planning_sections
CREATE TABLE finance.planning_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    year_label TEXT,
    colour TEXT DEFAULT '#6366f1',
    icon TEXT,
    display_order INTEGER DEFAULT 0,
    is_archived BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Create planning_notes
CREATE TABLE finance.planning_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id UUID REFERENCES finance.planning_sections(id),
    content TEXT NOT NULL,
    display_order INTEGER DEFAULT 0,
    is_pinned BOOLEAN DEFAULT false,
    tags TEXT[],
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Create ai_mapping_cache
CREATE TABLE finance.ai_mapping_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    headers_hash TEXT UNIQUE NOT NULL,
    headers JSONB NOT NULL,
    result JSONB NOT NULL,
    confidence NUMERIC NOT NULL,
    hits INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_used_at TIMESTAMPTZ DEFAULT now()
);

-- Create ai_usage_tracking
CREATE TABLE finance.ai_usage_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE DEFAULT CURRENT_DATE,
    usage_type TEXT NOT NULL,
    count INTEGER DEFAULT 0
);

-- Create category_corrections
CREATE TABLE finance.category_corrections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description TEXT NOT NULL,
    original_category_id UUID REFERENCES finance.categories(id),
    corrected_category_id UUID REFERENCES finance.categories(id),
    original_source TEXT,
    import_session_id UUID REFERENCES finance.import_sessions(id),
    created_rule_id UUID REFERENCES finance.category_mappings(id),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Create investment_valuations
CREATE TABLE finance.investment_valuations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES finance.accounts(id),
    date DATE NOT NULL,
    value NUMERIC NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Note: home_costs, home_costs_settings, mtd_export_history reference auth.users
-- These will need special handling if user auth is required
-- For now, creating without FK to auth.users since Finance Tracker is local-only

CREATE TABLE finance.home_costs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID, -- No FK, local only
    cost_type TEXT CHECK (cost_type IN ('use_of_home', 'phone_broadband', 'insurance')),
    description TEXT,
    start_date DATE NOT NULL,
    end_date DATE,
    hours_per_month TEXT CHECK (hours_per_month IN ('25-50', '51-100', '101+') OR hours_per_month IS NULL),
    monthly_cost NUMERIC,
    business_percent INTEGER CHECK (business_percent IS NULL OR (business_percent >= 1 AND business_percent <= 100)),
    annual_premium NUMERIC,
    business_stock_value NUMERIC,
    total_contents_value NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE finance.home_costs_settings (
    user_id UUID PRIMARY KEY,
    display_mode TEXT DEFAULT 'separate' CHECK (display_mode IN ('separate', 'consolidated')),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE finance.mtd_export_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    month TEXT NOT NULL,
    export_type TEXT CHECK (export_type IN ('csv', 'quickfile')),
    entries_count INTEGER DEFAULT 0,
    quickfile_response JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Create indexes
CREATE INDEX idx_finance_transactions_date ON finance.transactions(date);
CREATE INDEX idx_finance_transactions_account ON finance.transactions(account_id);
CREATE INDEX idx_finance_transactions_category ON finance.transactions(category_id);
CREATE INDEX idx_finance_budgets_year_month ON finance.budgets(year, month);
CREATE INDEX idx_finance_wealth_snapshots_date ON finance.wealth_snapshots(date);
CREATE INDEX idx_finance_wealth_snapshots_account ON finance.wealth_snapshots(account_id);

-- Enable RLS on all tables (even for local-only, good practice)
ALTER TABLE finance.accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.category_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.category_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.wealth_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.import_formats ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.import_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.imported_transaction_hashes ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.fire_parameters ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.fire_scenarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.fire_inputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.planning_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.planning_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.ai_mapping_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.ai_usage_tracking ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.category_corrections ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.investment_valuations ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.home_costs ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.home_costs_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.mtd_export_history ENABLE ROW LEVEL SECURITY;

-- Create permissive policies for service_role
CREATE POLICY "service_role_all" ON finance.accounts FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.categories FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.category_groups FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.category_mappings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.transactions FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.budgets FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.wealth_snapshots FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.import_formats FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.import_sessions FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.imported_transaction_hashes FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.fire_parameters FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.fire_scenarios FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.fire_inputs FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.planning_sections FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.planning_notes FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.ai_mapping_cache FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.ai_usage_tracking FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.category_corrections FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.investment_valuations FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.home_costs FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.home_costs_settings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON finance.mtd_export_history FOR ALL TO service_role USING (true) WITH CHECK (true);
```

### 3.3 Data Migration Script

```sql
-- Migration: 003_import_finance_data.sql
-- This must be run AFTER the schema is created
-- Data will be imported via pg_dump/pg_restore or INSERT statements

-- Step 1: Export data from finance-tracker using pg_dump with --data-only
-- Step 2: Modify the dump to target finance.* instead of public.*
-- Step 3: Import the modified dump

-- Alternatively, use Supabase's built-in database export/import features
-- Or use a Python script with psycopg2 to copy data between databases
```

### 3.4 Python Data Migration Script

Create this script to safely copy data:

```python
# scripts/migrate_finance_data.py
import os
import asyncio
from supabase import create_client, Client
import httpx

# Source: finance-tracker
SOURCE_URL = os.environ['FINANCE_TRACKER_SUPABASE_URL']
SOURCE_KEY = os.environ['FINANCE_TRACKER_SUPABASE_KEY']

# Target: inventory-management-app
TARGET_URL = os.environ['INVENTORY_SUPABASE_URL']
TARGET_KEY = os.environ['INVENTORY_SUPABASE_KEY']

# Tables in migration order (respecting foreign keys)
MIGRATION_ORDER = [
    'category_groups',
    'accounts',
    'categories',
    'category_mappings',
    'import_formats',
    'import_sessions',
    'transactions',
    'imported_transaction_hashes',
    'budgets',
    'wealth_snapshots',
    'fire_parameters',
    'fire_scenarios',
    'fire_inputs',
    'planning_sections',
    'planning_notes',
    'ai_mapping_cache',
    'ai_usage_tracking',
    'category_corrections',
    'investment_valuations',
    'home_costs',
    'home_costs_settings',
    'mtd_export_history'
]

async def migrate_table(table_name: str, source: Client, target_url: str, target_key: str):
    """Migrate a single table from source to target."""
    print(f"Migrating {table_name}...")

    # Fetch all data from source
    response = source.table(table_name).select('*').execute()
    data = response.data

    if not data:
        print(f"  No data in {table_name}")
        return 0

    # Insert into target (finance schema)
    # Using httpx directly since Supabase client doesn't support custom schemas easily
    async with httpx.AsyncClient() as client:
        headers = {
            'apikey': target_key,
            'Authorization': f'Bearer {target_key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal'
        }

        # Insert in batches of 100
        batch_size = 100
        inserted = 0
        for i in range(0, len(data), batch_size):
            batch = data[i:i+batch_size]
            resp = await client.post(
                f"{target_url}/rest/v1/finance/{table_name}",
                headers=headers,
                json=batch
            )
            if resp.status_code in (200, 201):
                inserted += len(batch)
            else:
                print(f"  Error inserting batch: {resp.status_code} - {resp.text}")

        print(f"  Migrated {inserted}/{len(data)} rows")
        return inserted

async def main():
    source = create_client(SOURCE_URL, SOURCE_KEY)

    total = 0
    for table in MIGRATION_ORDER:
        count = await migrate_table(table, source, TARGET_URL, TARGET_KEY)
        total += count

    print(f"\nTotal rows migrated: {total}")

if __name__ == '__main__':
    asyncio.run(main())
```

---

## Phase 4: Update Application Configurations

### 4.1 Finance Tracker App Changes

**Location:** `hadley-bricks-inventory-management/apps/web/` (Finance Tracker Next.js app)

#### Environment Variables Update:

```env
# .env.local (Finance Tracker)
# OLD
NEXT_PUBLIC_SUPABASE_URL=https://vkezoyhjoufvsjopjbrr.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...

# NEW - Point to Inventory Management App
NEXT_PUBLIC_SUPABASE_URL=https://modjoikyuhqzouxvieua.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
```

#### Supabase Client Update:

All Supabase queries need to target the `finance` schema. Update the client initialization:

```typescript
// lib/supabase.ts
import { createClient } from '@supabase/supabase-js'

export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  {
    db: {
      schema: 'finance'  // <-- ADD THIS
    }
  }
)
```

**OR** if you need to access multiple schemas, use schema parameter per query:

```typescript
// For finance schema
const { data } = await supabase
  .schema('finance')
  .from('transactions')
  .select('*')

// For public schema (inventory)
const { data } = await supabase
  .from('inventory_items')  // defaults to public
  .select('*')
```

### 4.2 Discord-Messenger / Peterbot Changes

**NO CHANGES REQUIRED!**

The Peterbot tables are already in the `public` schema of the Inventory Management App. All existing code will continue to work.

Verify these environment variables remain unchanged:
```env
# .env (Discord-Messenger)
SUPABASE_URL=https://modjoikyuhqzouxvieua.supabase.co
SUPABASE_KEY=eyJ...  # service_role key
```

### 4.3 Hadley Bricks Inventory Management Changes

**NO CHANGES REQUIRED!**

This app already uses the target database. All tables remain in the `public` schema.

---

## Phase 5: Regression Testing

### 5.1 Finance Tracker Test Plan

#### Pre-Migration Baseline (Record Current State):

```sql
-- Run on finance-tracker BEFORE migration
SELECT
  'transactions' as table_name,
  COUNT(*) as count,
  SUM(amount) as total_amount
FROM transactions
UNION ALL
SELECT
  'budgets',
  COUNT(*),
  SUM(amount)
FROM budgets
UNION ALL
SELECT
  'wealth_snapshots',
  COUNT(*),
  SUM(balance)
FROM wealth_snapshots;
```

#### Post-Migration Verification:

```sql
-- Run on inventory-management-app AFTER migration
SELECT
  'finance.transactions' as table_name,
  COUNT(*) as count,
  SUM(amount) as total_amount
FROM finance.transactions
UNION ALL
SELECT
  'finance.budgets',
  COUNT(*),
  SUM(amount)
FROM finance.budgets
UNION ALL
SELECT
  'finance.wealth_snapshots',
  COUNT(*),
  SUM(balance)
FROM finance.wealth_snapshots;
```

#### Functional Tests:

| Test Case | Steps | Expected Result |
|-----------|-------|-----------------|
| Load dashboard | Open Finance Tracker app | Dashboard loads with correct totals |
| View transactions | Navigate to Transactions page | All 2,790 transactions visible |
| Add transaction | Create new transaction | Saves to finance.transactions |
| Category assignment | Assign category to transaction | Updates correctly |
| Budget view | Open Budgets page | All 2,148 budget entries visible |
| FIRE calculator | Open FIRE page | Calculations work correctly |
| Import CSV | Import a test bank statement | Creates import session, transactions |
| Wealth snapshot | Add new snapshot | Saves to finance.wealth_snapshots |
| Planning notes | View/edit planning notes | All 20 notes accessible |

### 5.2 Discord-Messenger / Peterbot Test Plan

| Test Case | Steps | Expected Result |
|-----------|-------|-----------------|
| Reminder creation | `/remind me in 5 minutes to test` | Reminder saved to `reminders` table |
| Reminder firing | Wait for reminder | Notification sent, `fired_at` updated |
| Nutrition logging | Log a meal via Peterbot | Entry in `nutrition_logs` |
| Nutrition summary | Request daily summary | Correct totals returned |
| Knowledge save | `!save <url>` | Item in `knowledge_items`, chunks in `knowledge_chunks` |
| Semantic search | Ask about saved topic | Returns relevant chunks |
| Garmin data | Check health data | `garmin_daily_summary` readable |
| YouTube digest | Request video digest | `youtube_shown_videos` updated |

### 5.3 Hadley Bricks Inventory Test Plan

| Test Case | Steps | Expected Result |
|-----------|-------|-----------------|
| Dashboard load | Open HB Inventory app | All metrics load |
| Inventory list | View inventory items | All 5,481 items visible |
| eBay sync | Trigger eBay sync | Transactions update |
| Amazon pricing | Check arbitrage pricing | 37,018 pricing records accessible |
| Order management | View/update orders | All 2,311 orders accessible |
| BrickLink data | Check BrickLink uploads | 158 uploads visible |

---

## Phase 6: Cleanup & Final Steps

### 6.1 Pause Finance Tracker Project

Once all tests pass:

```
Project: vkezoyhjoufvsjopjbrr
Action: Pause
```

### 6.2 Update Documentation

- Update README files with new database connection details
- Update any deployment scripts
- Update environment variable templates

### 6.3 Monitor for Issues

For 1-2 weeks after migration:
- Monitor Supabase logs for errors
- Check application error logs
- Verify all scheduled jobs work correctly

---

## Rollback Plan

If issues are found post-migration:

### Immediate Rollback (< 24 hours):

1. Restore Finance Tracker project from pause
2. Revert Finance Tracker app environment variables
3. Data in new `finance` schema can remain (no harm)

### Data Recovery:

If data corruption is suspected:
1. Restore from pg_dump backups taken in Phase 0
2. Contact Supabase support for point-in-time recovery if needed

---

## Appendix A: Table Name Conflicts

The following table names exist in BOTH the Inventory Management App and Finance Tracker:

| Table Name | Inventory App | Finance Tracker | Resolution |
|------------|---------------|-----------------|------------|
| home_costs | Exists (4 rows) | Exists (0 rows) | Keep inventory version, finance uses `finance.home_costs` |
| home_costs_settings | Exists (1 row) | Exists (0 rows) | Keep inventory version, finance uses `finance.home_costs_settings` |
| mtd_export_history | Exists (1 row) | Exists (0 rows) | Keep inventory version, finance uses `finance.mtd_export_history` |

These tables exist in both because they were created for the same MTD/home office expense tracking feature. The `finance` schema versions will be used by the Finance Tracker app.

---

## Appendix B: Cost Comparison

### Before Consolidation:
| Item | Cost |
|------|------|
| Pro Plan Base | $25.00 |
| Inventory Management App Compute (390 hrs) | $5.24 |
| japan-travel-planner Compute (390 hrs) | $5.24 |
| finance-tracker Compute (390 hrs) | $5.24 |
| Compute Credits | -$10.00 |
| **Total** | **$30.72** |

### After Consolidation:
| Item | Cost |
|------|------|
| Pro Plan Base | $25.00 |
| Inventory Management App Compute (390 hrs) | $5.24 |
| Compute Credits | -$10.00 |
| **Total** | **$20.24** |

**Monthly Savings: $10.48**
**Annual Savings: $125.76**

---

## Appendix C: Migration Timeline

| Phase | Task | Duration |
|-------|------|----------|
| 0 | Backups | 30 mins |
| 1 | Pause japan-travel-planner | 5 mins |
| 2 | Create finance schema | 15 mins |
| 3a | Create finance tables | 30 mins |
| 3b | Migrate finance data | 30 mins |
| 4 | Update app configurations | 30 mins |
| 5 | Regression testing | 2-3 hours |
| 6 | Pause finance-tracker | 5 mins |
| **Total** | | **~5 hours** |

---

## Appendix D: Files to Update

### Finance Tracker (hadley-bricks-inventory-management/apps/web)

1. `.env.local` - Update Supabase credentials
2. `lib/supabase.ts` or equivalent - Add schema config
3. Any direct SQL queries that don't use the client

### Discord-Messenger

No files need updating - already using target database.

### Hadley Bricks Inventory Management

No files need updating - this IS the target database.

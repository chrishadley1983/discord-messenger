"""
Finance Tracker Data Migration Script
Migrates data from finance-tracker project to finance schema in inventory-management-app
"""
import os
import json
import httpx
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Source: finance-tracker
SOURCE_URL = "https://vkezoyhjoufvsjopjbrr.supabase.co"
SOURCE_KEY = os.environ.get('FINANCE_TRACKER_SERVICE_KEY')

# Target: inventory-management-app
TARGET_URL = "https://modjoikyuhqzouxvieua.supabase.co"
TARGET_KEY = os.environ.get('SUPABASE_KEY')

if not SOURCE_KEY:
    raise ValueError("FINANCE_TRACKER_SERVICE_KEY environment variable not set")
if not TARGET_KEY:
    raise ValueError("SUPABASE_KEY environment variable not set")

# Tables in migration order (respecting foreign keys)
MIGRATION_ORDER = [
    'category_groups',
    'accounts',
    'categories',
    'category_mappings',
    'import_formats',
    'fire_parameters',
    'fire_scenarios',
    'fire_inputs',
    'planning_sections',
    'planning_notes',
    'ai_mapping_cache',
    'ai_usage_tracking',
    'import_sessions',
    'transactions',
    'imported_transaction_hashes',
    'budgets',
    'wealth_snapshots',
    'category_corrections',
    'investment_valuations',
    'home_costs',
    'home_costs_settings',
    'mtd_export_history'
]


async def fetch_all_data(client: httpx.AsyncClient, table: str) -> list:
    """Fetch all data from source table with pagination."""
    headers = {
        'apikey': SOURCE_KEY,
        'Authorization': f'Bearer {SOURCE_KEY}',
    }

    all_data = []
    offset = 0
    limit = 1000

    while True:
        url = f"{SOURCE_URL}/rest/v1/{table}?select=*&offset={offset}&limit={limit}"
        resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            print(f"  Error fetching {table}: {resp.status_code} - {resp.text}")
            break

        data = resp.json()
        if not data:
            break

        all_data.extend(data)
        offset += limit

        if len(data) < limit:
            break

    return all_data


async def insert_data(client: httpx.AsyncClient, table: str, data: list) -> int:
    """Insert data into target finance schema."""
    if not data:
        return 0

    headers = {
        'apikey': TARGET_KEY,
        'Authorization': f'Bearer {TARGET_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }

    # Insert in batches of 100
    batch_size = 100
    inserted = 0

    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]

        # Target the finance schema
        url = f"{TARGET_URL}/rest/v1/{table}"

        # Add schema header for finance schema
        batch_headers = {**headers, 'Accept-Profile': 'finance', 'Content-Profile': 'finance'}

        resp = await client.post(url, headers=batch_headers, json=batch)

        if resp.status_code in (200, 201):
            inserted += len(batch)
        else:
            print(f"  Error inserting batch into {table}: {resp.status_code}")
            print(f"  Response: {resp.text[:500]}")
            # Try inserting one by one to find problematic records
            for record in batch:
                single_resp = await client.post(url, headers=batch_headers, json=[record])
                if single_resp.status_code in (200, 201):
                    inserted += 1
                else:
                    print(f"  Failed record: {json.dumps(record)[:200]}")

    return inserted


async def migrate_table(client: httpx.AsyncClient, table: str) -> tuple[int, int]:
    """Migrate a single table from source to target."""
    print(f"\nMigrating {table}...")

    # Fetch all data from source
    data = await fetch_all_data(client, table)
    source_count = len(data)

    if not data:
        print(f"  No data in {table}")
        return 0, 0

    print(f"  Fetched {source_count} rows from source")

    # Insert into target
    inserted = await insert_data(client, table, data)

    print(f"  Migrated {inserted}/{source_count} rows")
    return source_count, inserted


async def verify_migration(client: httpx.AsyncClient, table: str, expected: int) -> bool:
    """Verify the migration by counting rows in target."""
    headers = {
        'apikey': TARGET_KEY,
        'Authorization': f'Bearer {TARGET_KEY}',
        'Accept-Profile': 'finance',
        'Prefer': 'count=exact'
    }

    url = f"{TARGET_URL}/rest/v1/{table}?select=*"
    resp = await client.head(url, headers=headers)

    if 'content-range' in resp.headers:
        # Parse count from content-range header (e.g., "0-99/150")
        range_header = resp.headers['content-range']
        if '/' in range_header:
            count = int(range_header.split('/')[1])
            return count == expected

    return False


async def main():
    print("=" * 60)
    print("Finance Tracker Data Migration")
    print("=" * 60)
    print(f"Source: {SOURCE_URL}")
    print(f"Target: {TARGET_URL} (finance schema)")
    print("=" * 60)

    results = {}

    async with httpx.AsyncClient(timeout=60.0) as client:
        for table in MIGRATION_ORDER:
            source_count, inserted = await migrate_table(client, table)
            results[table] = {'source': source_count, 'migrated': inserted}

    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)

    total_source = 0
    total_migrated = 0

    for table, counts in results.items():
        status = "✓" if counts['source'] == counts['migrated'] else "✗"
        print(f"{status} {table}: {counts['migrated']}/{counts['source']}")
        total_source += counts['source']
        total_migrated += counts['migrated']

    print("-" * 60)
    print(f"TOTAL: {total_migrated}/{total_source} rows migrated")

    if total_source == total_migrated:
        print("\n✓ Migration completed successfully!")
    else:
        print(f"\n✗ Migration incomplete: {total_source - total_migrated} rows failed")

    return results


if __name__ == '__main__':
    asyncio.run(main())

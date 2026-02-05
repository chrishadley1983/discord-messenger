"""
Migrate large Finance Tracker tables via direct Supabase REST API
Uses anon key with service_role for both source and target
"""
import os
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Source: finance-tracker (project vkezoyhjoufvsjopjbrr)
SOURCE_URL = "https://vkezoyhjoufvsjopjbrr.supabase.co"
SOURCE_KEY = os.environ.get('SUPABASE_KEY')  # We'll need to get this

# Target: inventory-management-app (project modjoikyuhqzouxvieua)
TARGET_URL = "https://modjoikyuhqzouxvieua.supabase.co"
TARGET_KEY = os.environ.get('SUPABASE_KEY')

# Tables to migrate in order
LARGE_TABLES = [
    ('transactions', 'finance.transactions'),
    ('budgets', 'finance.budgets'),
    ('wealth_snapshots', 'finance.wealth_snapshots'),
    ('imported_transaction_hashes', 'finance.imported_transaction_hashes'),
]

async def fetch_table(client: httpx.AsyncClient, url: str, key: str, table: str) -> list:
    """Fetch all data from a table with pagination."""
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
    }

    all_data = []
    offset = 0
    page_size = 500

    while True:
        response = await client.get(
            f"{url}/rest/v1/{table}",
            headers=headers,
            params={'select': '*', 'offset': offset, 'limit': page_size}
        )

        if response.status_code != 200:
            print(f"Error fetching {table}: {response.status_code} - {response.text[:200]}")
            break

        data = response.json()
        if not data:
            break

        all_data.extend(data)
        print(f"  Fetched {len(all_data)} rows from {table}...")
        offset += page_size

        if len(data) < page_size:
            break

    return all_data


async def insert_table(client: httpx.AsyncClient, url: str, key: str, table: str, data: list, schema: str = 'public') -> int:
    """Insert data into target table in batches."""
    if not data:
        return 0

    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal',
    }

    # If schema is not public, use schema headers
    if schema != 'public':
        headers['Accept-Profile'] = schema
        headers['Content-Profile'] = schema

    # Determine actual table name (remove schema prefix for REST API)
    actual_table = table.split('.')[-1] if '.' in table else table

    batch_size = 100
    inserted = 0

    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]

        response = await client.post(
            f"{url}/rest/v1/{actual_table}",
            headers=headers,
            json=batch
        )

        if response.status_code in (200, 201):
            inserted += len(batch)
        else:
            print(f"  Error inserting batch: {response.status_code}")
            print(f"  Response: {response.text[:500]}")
            # Continue anyway

        if (i + batch_size) % 500 == 0:
            print(f"  Inserted {inserted} rows into {table}...")

    return inserted


async def main():
    print("=" * 60)
    print("Large Table Migration")
    print("=" * 60)

    # Check keys
    if not SOURCE_KEY or not TARGET_KEY:
        print("ERROR: Missing SUPABASE_KEY environment variable")
        print("Set SUPABASE_KEY to your service_role key")
        return

    async with httpx.AsyncClient(timeout=120.0) as client:
        for source_table, target_table in LARGE_TABLES:
            print(f"\n--- Migrating {source_table} ---")

            # Fetch from source
            print(f"Fetching from source...")
            data = await fetch_table(client, SOURCE_URL, SOURCE_KEY, source_table)
            print(f"Total rows fetched: {len(data)}")

            if not data:
                continue

            # Insert into target
            print(f"Inserting into target ({target_table})...")
            schema = target_table.split('.')[0] if '.' in target_table else 'public'
            inserted = await insert_table(client, TARGET_URL, TARGET_KEY, target_table, data, schema)
            print(f"Rows inserted: {inserted}/{len(data)}")

    print("\n" + "=" * 60)
    print("Migration complete!")


if __name__ == '__main__':
    asyncio.run(main())

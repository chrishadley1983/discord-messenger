"""Backfill existing Gousto recipes to 4 servings.

Re-scrapes each recipe via CDP and updates the content in Second Brain
with ingredients scaled to 4 servings (family of 4).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from dotenv import load_dotenv

load_dotenv()

from domains.second_brain.seed.adapters.scrapers.gousto import GoustoRecipeScraper

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


async def get_existing_gousto_recipes() -> list[dict]:
    """Fetch all active Gousto recipes from Second Brain."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/knowledge_items",
            headers=HEADERS,
            params={
                "topics": "cs.{gousto}",
                "status": "eq.active",
                "select": "id,title,source_url,full_text",
                "order": "created_at.desc",
                "limit": 1000,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def update_recipe_content(item_id: str, new_content: str) -> bool:
    """Update the full_text of a knowledge item."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/knowledge_items",
            headers=HEADERS,
            params={"id": f"eq.{item_id}"},
            json={"full_text": new_content},
        )
        return resp.status_code in (200, 204)


async def main():
    print("=== Gousto 4-Serving Backfill ===\n")

    # Get existing recipes
    recipes = await get_existing_gousto_recipes()
    print(f"Found {len(recipes)} Gousto recipes to backfill\n")

    if not recipes:
        return

    # Skip recipes that are already scaled to 4
    to_update = []
    already_scaled = 0
    for r in recipes:
        if r.get("full_text") and "Servings:** 4" in r["full_text"]:
            already_scaled += 1
        else:
            to_update.append(r)

    if already_scaled:
        print(f"Already at 4 servings: {already_scaled} (skipping)")
    print(f"Need re-scraping: {len(to_update)}\n")

    if not to_update:
        print("Nothing to do!")
        return

    # Set up CDP scraper
    scraper = GoustoRecipeScraper()
    await scraper.setup()

    updated = 0
    failed = 0
    skipped_404 = 0

    try:
        for i, recipe in enumerate(to_update):
            title = recipe["title"]
            source_url = recipe["source_url"]
            item_id = recipe["id"]

            print(f"[{i+1}/{len(to_update)}] {title}...", end=" ", flush=True)

            # Re-scrape with 4-serving scaling
            result = await scraper.scrape_link(None, source_url)

            if not result:
                # Recipe might be 404 now — try with email name fallback
                scraper._link_names[source_url] = title
                result = await scraper.scrape_link(None, source_url)

            if result:
                ok = await update_recipe_content(item_id, result.content)
                if ok:
                    print("UPDATED")
                    updated += 1
                else:
                    print("DB UPDATE FAILED")
                    failed += 1
            else:
                print("404/SKIP")
                skipped_404 += 1

    finally:
        await scraper.teardown()

    print(f"\n=== Results ===")
    print(f"Updated:    {updated}")
    print(f"404/Skip:   {skipped_404}")
    print(f"Failed:     {failed}")
    print(f"Already OK: {already_scaled}")
    print(f"Total:      {len(recipes)}")


if __name__ == "__main__":
    asyncio.run(main())

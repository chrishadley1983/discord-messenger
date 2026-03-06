"""Test Gousto scraper fix — exercises scrape_link against a real recipe URL.

Run from WSL with the bot's venv:
  /home/chris_hadley/Discord-Messenger/venv/bin/python tests/test_gousto_scraper.py
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use the installed Chromium (venv Playwright version may not match installed browsers)
CHROMIUM_PATH = os.path.expanduser(
    "~/.cache/ms-playwright/chromium-1212/chrome-linux64/chrome"
)

# Minimal logger stub (the real one needs Discord bot context)
import logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(message)s")
logger = logging.getLogger("test")

# Patch the logger module so gousto.py can import it
import types
logger_module = types.ModuleType("logger")
logger_module.logger = logger
sys.modules["logger"] = logger_module

# Import the scraper directly, bypassing the second_brain package __init__.py
# which pulls in unrelated dependencies (readability, etc.)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRAPERS_DIR = os.path.join(PROJECT_ROOT, "domains", "second_brain", "seed", "adapters", "scrapers")

# Create a minimal base module stub
import importlib.util

# Load base.py first (GoustoRecipeScraper depends on it)
base_spec = importlib.util.spec_from_file_location(
    "gousto_base", os.path.join(SCRAPERS_DIR, "base.py")
)
base_mod = importlib.util.module_from_spec(base_spec)
sys.modules["gousto_base"] = base_mod
base_spec.loader.exec_module(base_mod)

# Patch the relative import that gousto.py uses
fake_base = types.ModuleType("fake_scrapers_base")
fake_base.BaseEmailLinkScraper = base_mod.BaseEmailLinkScraper
fake_base.ScrapedItem = base_mod.ScrapedItem

# Load gousto.py with patched imports
gousto_source = open(os.path.join(SCRAPERS_DIR, "gousto.py")).read()
gousto_source = gousto_source.replace(
    "from .base import BaseEmailLinkScraper, ScrapedItem",
    "from gousto_base import BaseEmailLinkScraper, ScrapedItem",
)
gousto_spec = importlib.util.spec_from_loader("gousto_scraper", loader=None)
gousto_mod = importlib.util.module_from_spec(gousto_spec)
exec(compile(gousto_source, os.path.join(SCRAPERS_DIR, "gousto.py"), "exec"), gousto_mod.__dict__)
sys.modules["gousto_scraper"] = gousto_mod


async def test_scrape_real_recipe():
    """Test scraping a known Gousto recipe page directly (no tracking URL)."""
    from playwright.async_api import async_playwright

    # Use a recipe URL that still exists on Gousto
    test_url = "https://www.gousto.co.uk/cookbook/recipes/slow-cooker-beef-stroganoff-tortiglioni"

    print(f"\n=== Gousto Scraper Test ===\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROMIUM_PATH,
        )
        page = await browser.new_page()

        try:
            # Import and instantiate the scraper
            from gousto_scraper import GoustoRecipeScraper
            scraper = GoustoRecipeScraper()

            print(f"[1] Scraping: {test_url}")
            result = await scraper.scrape_link(page, test_url)

            if result is None:
                print("[FAIL] scrape_link returned None")
                return False

            print(f"[OK] Title: {result.title}")
            print(f"[OK] URL: {result.url}")
            print(f"[OK] Topics: {result.topics}")
            print(f"[OK] Metadata: {result.metadata}")
            print(f"[OK] Content length: {len(result.content)} chars")
            print(f"\n--- Content preview ---")
            print(result.content[:500])
            print("---\n")

            # Verify canonical_url was set correctly (not the fallback)
            assert "gousto.co.uk/cookbook" in result.url, f"URL should be canonical recipe URL, got: {result.url}"
            assert result.title, "Title should not be empty"
            print("[PASS] All assertions passed\n")
            return True

        except Exception as e:
            print(f"[FAIL] Exception: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await browser.close()


async def test_scrape_nonrecipe_url():
    """Test that non-recipe URLs return None gracefully."""
    from playwright.async_api import async_playwright

    test_url = "https://www.gousto.co.uk/blog"

    print(f"=== Non-recipe URL Test ===\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROMIUM_PATH,
        )
        page = await browser.new_page()

        try:
            from gousto_scraper import GoustoRecipeScraper
            scraper = GoustoRecipeScraper()

            print(f"[1] Scraping non-recipe URL: {test_url}")
            result = await scraper.scrape_link(page, test_url)

            if result is None:
                print("[PASS] Correctly returned None for non-recipe URL\n")
                return True
            else:
                print(f"[FAIL] Should have returned None, got: {result.title}\n")
                return False

        except Exception as e:
            print(f"[FAIL] Exception: {type(e).__name__}: {e}")
            return False
        finally:
            await browser.close()


async def test_canonical_url_not_unbound():
    """Verify canonical_url is never unbound — the original bug."""
    from playwright.async_api import async_playwright

    # Use a URL that will timeout or fail — this is the scenario that triggered the bug
    test_url = "https://httpstat.us/504?sleep=1000"

    print(f"=== UnboundLocalError Regression Test ===\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROMIUM_PATH,
        )
        page = await browser.new_page()

        try:
            from gousto_scraper import GoustoRecipeScraper
            scraper = GoustoRecipeScraper()

            print(f"[1] Scraping bad URL (should fail gracefully): {test_url}")
            result = await scraper.scrape_link(page, test_url)

            if result is None:
                print("[PASS] Returned None without UnboundLocalError\n")
                return True
            else:
                print(f"[WARN] Unexpectedly got a result: {result.title}\n")
                return True  # Not a failure, just unexpected

        except UnboundLocalError as e:
            print(f"[FAIL] UnboundLocalError still occurs: {e}\n")
            return False
        except Exception as e:
            # Any other exception is fine — we just care that it's not UnboundLocalError
            print(f"[PASS] Got {type(e).__name__} (not UnboundLocalError): {e}\n")
            return True
        finally:
            await browser.close()


async def test_oh_crumbs_fallback():
    """Test that 'Oh crumbs!' pages use the recipe name from the email."""
    from playwright.async_api import async_playwright

    # This recipe returns "Oh crumbs!" (removed from Gousto)
    test_url = "https://www.gousto.co.uk/cookbook/chicken-recipes/creamy-chicken-orzo"

    print(f"=== Oh Crumbs Fallback Test ===\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROMIUM_PATH,
        )
        page = await browser.new_page()

        try:
            from gousto_scraper import GoustoRecipeScraper
            scraper = GoustoRecipeScraper()

            # Simulate email name extraction (normally done in extract_links)
            scraper._link_names[test_url] = "Creamy Chicken Orzo"

            print(f"[1] Scraping 404 recipe with email name fallback: {test_url}")
            result = await scraper.scrape_link(page, test_url)

            if result is None:
                print("[FAIL] Should have returned a ScrapedItem with email name\n")
                return False

            if result.title == "Creamy Chicken Orzo":
                print(f"[OK] Title from email: {result.title}")
                print(f"[OK] Status: {result.metadata.get('status')}")
                assert "no longer available" in result.content.lower(), "Should note recipe is unavailable"
                print(f"[OK] Content includes unavailability note")
                print(f"[PASS] Oh crumbs fallback works correctly\n")
                return True
            else:
                print(f"[FAIL] Expected 'Creamy Chicken Orzo', got: {result.title}\n")
                return False

        except Exception as e:
            print(f"[FAIL] Exception: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await browser.close()


async def main():
    results = []

    results.append(("Canonical URL regression", await test_canonical_url_not_unbound()))
    results.append(("Non-recipe URL", await test_scrape_nonrecipe_url()))
    results.append(("Oh crumbs fallback", await test_oh_crumbs_fallback()))
    results.append(("Real recipe scrape", await test_scrape_real_recipe()))

    print("=" * 40)
    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  {status}: {name}")

    print("=" * 40)
    if all_pass:
        print("All tests passed!")
    else:
        print("Some tests FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

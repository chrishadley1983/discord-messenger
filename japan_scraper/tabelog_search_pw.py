"""Search Tabelog for restaurant URLs and scores using Playwright (bypasses captcha).

Uses prefecture-filtered English Tabelog search with fuzzy matching on top 5 results.
Saves results to tabelog_search_results.json for the injection script to use.
"""

import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

from rapidfuzz import fuzz

GUIDE_DIR = Path.home() / ".skills/skills/guide-creator/sites/japan-2026"
OUTPUT = Path(__file__).parent / "scrape_output" / "tabelog_search_results.json"

FOOD_GUIDES = {
    "shinjuku-eats-guide.html": "tokyo",
    "east-tokyo-eats-guide.html": "tokyo",
    "osaka-eats-guide.html": "osaka",
    "kyoto-eats-guide.html": "kyoto",
    "day-trip-eats-nara-himeji-guide.html": "nara",
    "day-trip-eats-coastal-guide.html": "kanagawa",
    "ramen-noodles-guide.html": "tokyo",
    "sushi-seafood-guide.html": "tokyo",
    "street-food-guide.html": "tokyo",
    "sweets-cafes-guide.html": "tokyo",
    "fine-dining-guide.html": "tokyo",
    "budget-eats-guide.html": "tokyo",
    "tokyo-yakitori-guide.html": "tokyo",
    "kaiten-sushi-guide.html": "tokyo",
    "bars-nightlife-guide.html": "tokyo",
}

TABELOG_BADGE = (
    '<a href="{url}" target="_blank" rel="noopener" '
    'style="display:inline-block;padding:3px 10px;background:#fff4e6;'
    'color:#d4760a;font-size:10px;font-weight:700;text-decoration:none;'
    'letter-spacing:0.5px;margin-left:6px;vertical-align:middle">'
    'TABELOG {score}</a>'
)


def norm(name):
    return re.sub(r'[^\w\s]', '', name.lower().strip())


def get_missing_venues():
    """Get all food venue names that don't have Tabelog links."""
    missing = []
    seen = set()
    for guide_name, city in FOOD_GUIDES.items():
        path = GUIDE_DIR / guide_name
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        venues = re.findall(r'class="venue-link"[^>]*>([^<]+)</a>', html)
        for v in venues:
            if v in seen:
                continue
            escaped = re.escape(v)
            pattern = rf'{escaped}</a>(.*?)(?:<div class="card|$)'
            match = re.search(pattern, html, re.DOTALL)
            if match and "tabelog" in match.group(1).lower():
                continue
            seen.add(v)
            missing.append({"name": v, "guide": guide_name, "city": city})
    return missing


def search_tabelog_batch(missing_venues):
    """Search Tabelog for each venue using Playwright."""
    from playwright.sync_api import sync_playwright

    results = {}

    # Load checkpoint
    if OUTPUT.exists():
        with open(OUTPUT, "r", encoding="utf-8") as f:
            results = json.load(f)
        print(f"  Loaded {len(results)} cached results")

    to_search = [v for v in missing_venues if v["name"] not in results]
    print(f"  {len(to_search)} venues to search ({len(missing_venues) - len(to_search)} cached)")

    if not to_search:
        return results

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
        )
        page = context.new_page()

        for i, venue in enumerate(to_search):
            name = venue["name"]
            pref = venue["city"]
            safe_name = name.encode("ascii", "replace").decode("ascii")

            # Clean name for search
            search_name = re.sub(r'^\d+\.\s*', '', name)
            search_name = re.sub(r'\s*\([^)]+\)\s*$', '', search_name)
            search_name = re.sub(r'\s*[?—]+\s*$', '', search_name)
            search_name = search_name.strip()

            if len(search_name) < 3:
                results[name] = None
                continue

            print(f"  [{i+1}/{len(to_search)}] {safe_name} ({pref})...", end=" ", flush=True)

            try:
                encoded = urllib.parse.quote(search_name)
                url = f"https://tabelog.com/en/{pref}/rstLst/?vs=1&sw={encoded}"
                page.goto(url, timeout=20000)
                page.wait_for_timeout(1200)

                name_els = page.query_selector_all(".list-rst__rst-name-target")
                rating_els = page.query_selector_all(".list-rst__rating-val")

                if not name_els:
                    print("No results")
                    results[name] = None
                else:
                    # Check top 5 results for best fuzzy match
                    best_score = 0
                    best_result = None
                    for j, el in enumerate(name_els[:5]):
                        rname = el.inner_text().strip()
                        rurl = el.get_attribute("href") or ""
                        rscore = 0
                        if j < len(rating_els):
                            try:
                                rscore = float(rating_els[j].inner_text().strip())
                            except ValueError:
                                pass

                        # Fuzzy match - use both token_sort and partial
                        ms = fuzz.token_sort_ratio(norm(search_name), norm(rname))
                        ps = fuzz.partial_ratio(norm(search_name), norm(rname))
                        combined = max(ms, ps)

                        if combined > best_score:
                            best_score = combined
                            best_result = (rname, rurl, rscore, combined)

                    if best_result and best_score >= 75:
                        rn, ru, rs, sc = best_result
                        safe_rn = rn.encode("ascii", "replace").decode("ascii")
                        print(f"Found: {safe_rn} ({rs}) match={sc:.0f}")
                        results[name] = {
                            "url": ru,
                            "score": rs,
                            "tabelog_name": rn,
                            "match_score": sc,
                        }
                    else:
                        print(f"No good match (best={best_score:.0f})")
                        results[name] = None

            except Exception as e:
                err = str(e)[:60]
                print(f"Error: {err}")
                results[name] = None

            # Save checkpoint every 25
            if (i + 1) % 25 == 0:
                with open(OUTPUT, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                print(f"  [checkpoint saved]")

            time.sleep(0.5)

        browser.close()

    # Final save
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return results


def inject_results(results):
    """Inject Tabelog badges from search results into guides."""
    total = 0
    for guide_name in FOOD_GUIDES:
        path = GUIDE_DIR / guide_name
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        injected = 0
        for name, info in results.items():
            if not info or not info.get("url"):
                continue
            url = info["url"]
            score = info.get("score", 0)
            if score == 0:
                continue

            badge = TABELOG_BADGE.format(url=url, score=score)
            escaped = re.escape(name)
            pattern = rf'(class="venue-link"[^>]*>{escaped}</a>)'
            match = re.search(pattern, html)
            if not match:
                continue

            # Don't inject if already has tabelog
            after = html[match.end():match.end() + 200]
            if "tabelog" in after.lower()[:100]:
                continue

            html = html[:match.end()] + badge + html[match.end():]
            injected += 1

        if injected > 0:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  {guide_name}: {injected} badges injected")
            total += injected

    return total


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=== Tabelog Search (Playwright) ===")
    missing = get_missing_venues()
    print(f"  Venues needing Tabelog: {len(missing)}")

    results = search_tabelog_batch(missing)
    found = sum(1 for v in results.values() if v is not None)
    print(f"\n  Total found: {found}/{len(results)}")

    print("\n=== Injecting Badges ===")
    total = inject_results(results)
    print(f"\n  Total injected: {total}")


if __name__ == "__main__":
    main()

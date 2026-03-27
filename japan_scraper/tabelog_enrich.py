"""Enrich all guide venues with Tabelog ratings and links.

Phase 1: Fuzzy match against existing tabelog_combined.json (free)
Phase 2: Search tabelog.com/en for unmatched venues (HTTP only, no tokens)
Phase 3: Inject Tabelog badges into guide HTML files
"""

import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests
from rapidfuzz import fuzz, process

TABELOG_JSON = Path("C:/Users/Chris Hadley/claude-projects/Discord-Messenger/tabelog_combined.json")
GUIDE_DIR = Path.home() / ".skills/skills/guide-creator/sites/japan-2026"
OUTPUT_DIR = Path(__file__).parent / "scrape_output"

# Known false positives from fuzzy matching
FALSE_POSITIVES = {
    ("Sushiro Shinjuku", "USHIGORO S. SHINJUKU"),
    ("% Arabica", "ARABIYA"),
    ("Tonkatsu Aoki", "Tonkatsu Saku"),
    ("Nanaya", "NARAYA CAFE"),
    ("Daikoku Ramen", "| Daikoku"),  # Pipe prefix suggests different entry
    ("Seoul", "Seoul"),  # Too generic
    ("Hong Kong", "Hong Kong"),  # Too generic
}

# Food guide files where all venues are food-related
FOOD_GUIDES = {
    "shinjuku-eats-guide.html", "east-tokyo-eats-guide.html",
    "osaka-eats-guide.html", "kyoto-eats-guide.html",
    "day-trip-eats-nara-himeji-guide.html", "day-trip-eats-coastal-guide.html",
    "ramen-noodles-guide.html", "sushi-seafood-guide.html",
    "street-food-guide.html", "sweets-cafes-guide.html",
    "fine-dining-guide.html", "budget-eats-guide.html",
    "tokyo-yakitori-guide.html", "kaiten-sushi-guide.html",
    "bars-nightlife-guide.html",
}

# City mapping for Tabelog search
GUIDE_CITY_MAP = {
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
    name = unicodedata.normalize("NFKC", name)
    name = name.lower().strip()
    name = re.sub(r'\s*(restaurant|cafe|café|bar|izakaya|ramen|shop|store)\s*$', '', name)
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()


def extract_venues_without_tabelog():
    """Extract all food venue names from guides that don't have Tabelog links."""
    venues = []
    for html_file in sorted(GUIDE_DIR.glob("*-guide.html")):
        if html_file.name not in FOOD_GUIDES:
            continue
        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()
        names = re.findall(r'class="venue-link"[^>]*>([^<]+)</a>', html)
        for v in names:
            escaped = re.escape(v)
            pattern = rf'{escaped}</a>(.*?)(?:<div class="card|$)'
            match = re.search(pattern, html, re.DOTALL)
            if match and 'tabelog' in match.group(1).lower():
                continue
            venues.append((v, html_file.name))
    return venues


def phase1_fuzzy_match(venues):
    """Match venues against existing tabelog_combined.json."""
    with open(TABELOG_JSON, "r", encoding="utf-8") as f:
        tabelog = json.load(f)

    tabelog_names = [norm(r.get("name", "")) for r in tabelog]
    matched = {}
    unmatched = []

    for v, guide in venues:
        vn = norm(v)
        if len(vn) < 3:
            unmatched.append((v, guide))
            continue

        result = process.extractOne(
            vn, tabelog_names,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=82,
        )
        if result:
            match_name, score, idx = result
            t = tabelog[idx]
            # Check false positives
            if (v, t["name"]) in FALSE_POSITIVES:
                unmatched.append((v, guide))
                continue
            matched[(v, guide)] = {
                "url": t.get("url", ""),
                "score": t.get("score", 0),
                "name": t.get("name", ""),
                "match_confidence": score,
            }
        else:
            unmatched.append((v, guide))

    return matched, unmatched


def search_tabelog(name, city="tokyo"):
    """Search Tabelog English site for a restaurant. Returns (url, score) or None."""
    search_url = "https://tabelog.com/en/rstLst/"
    params = {"vs": "1", "sw": name, "sa": city}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        resp = requests.get(search_url, params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None

        html = resp.text

        # Extract first result's URL and rating
        # Pattern: <a class="list-rst__rst-name-target" href="...">
        url_match = re.search(
            r'<a[^>]*class="list-rst__rst-name-target"[^>]*href="([^"]+)"', html
        )
        if not url_match:
            return None

        url = url_match.group(1)

        # Get the rating from near the URL
        # Pattern: <span class="list-rst__rating-val">3.65</span>
        rating_match = re.search(
            r'<span[^>]*class="list-rst__rating-val"[^>]*>([\d.]+)</span>', html
        )
        score = float(rating_match.group(1)) if rating_match else 0

        # Get the restaurant name from search result to verify match
        name_match = re.search(
            r'class="list-rst__rst-name-target"[^>]*>([^<]+)</a>', html
        )
        result_name = name_match.group(1).strip() if name_match else ""

        # Verify it's actually a match (not just random first result)
        if result_name:
            match_score = fuzz.token_sort_ratio(norm(name), norm(result_name))
            if match_score < 70:
                return None

        return {"url": url, "score": score, "result_name": result_name}

    except requests.RequestException:
        return None


def phase2_tabelog_search(unmatched):
    """Search Tabelog for unmatched venues."""
    matched = {}
    still_unmatched = []

    # Load checkpoint if exists
    checkpoint_path = OUTPUT_DIR / "tabelog_search_checkpoint.json"
    searched = {}
    if checkpoint_path.exists():
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            searched = json.load(f)
        print(f"  Resuming from checkpoint ({len(searched)} already searched)")

    for i, (v, guide) in enumerate(unmatched):
        safe_name = v.encode("ascii", "replace").decode("ascii")
        cache_key = f"{v}|{guide}"

        if cache_key in searched:
            result = searched[cache_key]
            if result:
                matched[(v, guide)] = result
            else:
                still_unmatched.append((v, guide))
            continue

        city = GUIDE_CITY_MAP.get(guide, "tokyo")
        print(f"  [{i+1}/{len(unmatched)}] {safe_name} ({city})...", end=" ")

        result = search_tabelog(v, city)
        if result:
            matched[(v, guide)] = {
                "url": result["url"],
                "score": result["score"],
                "name": result.get("result_name", ""),
                "match_confidence": 0,
            }
            safe_result = result.get("result_name", "").encode("ascii", "replace").decode("ascii")
            print(f"Found: {safe_result} ({result['score']})")
            searched[cache_key] = matched[(v, guide)]
        else:
            print("Not found")
            still_unmatched.append((v, guide))
            searched[cache_key] = None

        # Save checkpoint every 20
        if (i + 1) % 20 == 0:
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(searched, f, indent=2, ensure_ascii=False)

        time.sleep(1.0)  # Be polite

    # Final checkpoint save
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(searched, f, indent=2, ensure_ascii=False)

    return matched, still_unmatched


def phase3_inject(all_matches):
    """Inject Tabelog badges into guide HTML files."""
    # Group by guide file
    by_guide = {}
    for (venue, guide), info in all_matches.items():
        by_guide.setdefault(guide, []).append((venue, info))

    total = 0
    for guide, matches in sorted(by_guide.items()):
        path = GUIDE_DIR / guide
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()

        injected = 0
        for venue, info in matches:
            url = info.get("url", "")
            score = info.get("score", 0)
            if not url or score == 0:
                continue

            # Build badge HTML
            badge = TABELOG_BADGE.format(url=url, score=score)

            # Find the venue-link and inject badge after closing </a>
            escaped = re.escape(venue)
            pattern = rf'(class="venue-link"[^>]*>{escaped}</a>)'
            match = re.search(pattern, html)
            if not match:
                # Try compact-name pattern
                pattern = rf'(class="venue-link"[^>]*>{escaped}</a>)'
                match = re.search(pattern, html)
                if not match:
                    continue

            # Check not already injected
            after = html[match.end():match.end()+200]
            if 'tabelog' in after.lower()[:100]:
                continue

            html = html[:match.end()] + badge + html[match.end():]
            injected += 1

        if injected > 0:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  {guide}: {injected} Tabelog badges injected")
            total += injected

    return total


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=== Phase 1: Fuzzy Match Against Local Tabelog Data ===")
    venues = extract_venues_without_tabelog()
    print(f"  Food venues without Tabelog: {len(venues)}")

    p1_matched, unmatched = phase1_fuzzy_match(venues)
    print(f"  Phase 1 matched: {len(p1_matched)}")
    print(f"  Still unmatched: {len(unmatched)}")

    print("\n=== Phase 2: Tabelog Website Search ===")
    print(f"  Searching {len(unmatched)} venues on tabelog.com...")
    p2_matched, still_unmatched = phase2_tabelog_search(unmatched)
    print(f"  Phase 2 matched: {len(p2_matched)}")
    print(f"  Final unmatched: {len(still_unmatched)}")

    print("\n=== Phase 3: Inject Tabelog Badges ===")
    all_matches = {**p1_matched, **p2_matched}
    total = phase3_inject(all_matches)
    print(f"\n  Total Tabelog badges injected: {total}")

    # Summary
    print(f"\n{'='*50}")
    print(f"Phase 1 (fuzzy match): {len(p1_matched)} matches")
    print(f"Phase 2 (web search):  {len(p2_matched)} matches")
    print(f"Total injected:        {total}")
    print(f"Still unmatched:       {len(still_unmatched)}")


if __name__ == "__main__":
    main()

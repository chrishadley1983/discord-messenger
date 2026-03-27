"""Enrich area eats guides with Reddit/YouTube social proof badges."""

import json
import re
import sys
from pathlib import Path
from rapidfuzz import fuzz

SCRAPER_DATA = Path(__file__).parent / "scrape_output" / "final_recommendations.json"
GUIDE_DIR = Path.home() / ".skills/skills/guide-creator/sites/japan-2026"

# Matches to EXCLUDE (false positives from fuzzy matching)
FALSE_POSITIVES = {
    ("Tempura Ando", "Tempura Kondo"),
    ("Kitsune", "Kitsuneya"),
}

AREA_GUIDES = [
    "shinjuku-eats-guide.html",
    "east-tokyo-eats-guide.html",
    "osaka-eats-guide.html",
    "kyoto-eats-guide.html",
    "day-trip-eats-nara-himeji-guide.html",
    "day-trip-eats-coastal-guide.html",
]

CATEGORY_GUIDES = [
    "ramen-noodles-guide.html",
    "sushi-seafood-guide.html",
    "street-food-guide.html",
    "sweets-cafes-guide.html",
    "fine-dining-guide.html",
    "budget-eats-guide.html",
    "tokyo-yakitori-guide.html",
    "kaiten-sushi-guide.html",
]

# CSS for the Reddit Buzz badge
BUZZ_CSS = """
  .badge-buzz { background: linear-gradient(135deg, #ff4500 0%, #ff6b35 100%); color: white; font-size: 10px; padding: 4px 10px; border-radius: 0; display: inline-flex; align-items: center; gap: 4px; }
  .buzz-tooltip { position: relative; cursor: help; }
  .buzz-tooltip .buzz-detail { display: none; position: absolute; bottom: calc(100% + 8px); left: 0; min-width: 280px; max-width: 340px; background: white; border: 1px solid var(--border); box-shadow: 0 8px 32px rgba(0,0,0,0.12); padding: 14px 16px; z-index: 100; font-size: 13px; line-height: 1.6; color: var(--text); font-weight: 400; text-transform: none; letter-spacing: 0; }
  .buzz-tooltip:hover .buzz-detail, .buzz-tooltip:focus .buzz-detail { display: block; }
  .buzz-detail strong { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #ff4500; margin-bottom: 4px; }
  .buzz-detail .buzz-quote { font-style: italic; color: #555; }
  .buzz-detail .buzz-google { margin-top: 6px; font-size: 12px; color: var(--text-light); }
"""


def norm(name):
    name = re.sub(r'[^\w\s]', '', name.lower().strip())
    for suf in ['honten', 'hon ten', 'shinjukuten', 'tokyo', 'shinjuku', 'shibuya', 'ginza']:
        name = re.sub(rf'\s*{suf}\s*$', '', name)
    return name.strip()


def load_scraper_data():
    with open(SCRAPER_DATA, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [p for p in data if p.get("type") in ("restaurant", "cafe", "bar", "izakaya")]


def find_matches(guide_names, scraper_entries, threshold=88):
    """Find matches between guide restaurant names and scraper entries."""
    matches = {}
    for gname in guide_names:
        gn = norm(gname)
        if len(gn) < 3:
            continue

        best_score = 0
        best_match = None
        for sp in scraper_entries:
            sn = norm(sp["name"])
            if len(sn) < 3:
                continue
            score = fuzz.token_sort_ratio(gn, sn)
            if score > best_score:
                best_score = score
                best_match = sp

        if best_score >= threshold and best_match:
            # Check false positives
            if (gname, best_match["name"]) in FALSE_POSITIVES:
                continue
            ctx = best_match.get("context", "")
            if ctx:  # Only add badge if there's actual social proof
                matches[gname] = best_match

    return matches


def build_badge_html(scraper_entry):
    """Build the Reddit Buzz badge HTML for a matched restaurant."""
    ctx = scraper_entry.get("context", "")
    # Truncate context to ~120 chars at word boundary
    if len(ctx) > 120:
        ctx = ctx[:120].rsplit(" ", 1)[0] + "..."
    # Escape HTML
    ctx = ctx.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    google = scraper_entry.get("google_match") or {}
    rating = google.get("rating")
    reviews = google.get("user_ratings_total") or 0

    google_line = ""
    if rating:
        google_line = f'<div class="buzz-google">Google {rating}/5 ({reviews:,} reviews)</div>'

    platform = scraper_entry.get("source_platform", "reddit")
    source_label = "Reddit & YouTube" if "youtube" in str(scraper_entry.get("sources", [])) else "Reddit"

    return (
        f'<span class="badge buzz-tooltip badge-buzz">'
        f'{source_label} Buzz'
        f'<span class="buzz-detail">'
        f'<strong>What people say</strong>'
        f'<span class="buzz-quote">&ldquo;{ctx}&rdquo;</span>'
        f'{google_line}'
        f'</span></span>'
    )


def inject_css(html):
    """Add buzz badge CSS if not already present."""
    if "badge-buzz" in html:
        return html  # Already enriched
    # Insert before closing </style>
    return html.replace("</style>", BUZZ_CSS + "\n</style>", 1)


def inject_badges(html, matches):
    """Inject Reddit Buzz badges after matched card-name elements."""
    injected = 0
    for gname, sp in matches.items():
        badge = build_badge_html(sp)
        escaped = re.escape(gname)
        # Find the badges div that follows the card containing this restaurant
        # Strategy: find the venue-link, then find the NEXT <div class="badges"> after it
        pattern = rf'(class="venue-link"[^>]*>{escaped}</a>)'
        match = re.search(pattern, html)
        if not match:
            continue
        # From the match position, find the next badges div
        rest = html[match.end():]
        badges_match = re.search(r'(<div class="badges">)', rest)
        if not badges_match:
            continue
        # Insert the badge right after the opening <div class="badges">
        insert_pos = match.end() + badges_match.end()
        html = html[:insert_pos] + "\n        " + badge + html[insert_pos:]
        injected += 1
    return html, injected


def enrich_guide(guide_file, scraper_entries):
    """Enrich a single guide file with Reddit Buzz badges."""
    path = GUIDE_DIR / guide_file
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    # Extract restaurant names
    names = re.findall(r'class="venue-link"[^>]*>([^<]+)</a>', html)
    if not names:
        return 0

    # Find matches
    matches = find_matches(names, scraper_entries)
    if not matches:
        return 0

    # Inject CSS
    html = inject_css(html)

    # Inject badges
    html, injected = inject_badges(html, matches)

    if injected > 0:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    return injected


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scraper_entries = load_scraper_data()
    print(f"Loaded {len(scraper_entries)} scraper entries")

    total = 0
    for guide in AREA_GUIDES + CATEGORY_GUIDES:
        count = enrich_guide(guide, scraper_entries)
        if count:
            print(f"  {guide}: {count} badges added")
            total += count
        else:
            print(f"  {guide}: no matches")

    print(f"\nDone! {total} Reddit Buzz badges added across all guides")


if __name__ == "__main__":
    main()

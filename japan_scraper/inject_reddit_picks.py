"""Inject Reddit Picks sections into area eats guides for unmatched scraper restaurants."""

import json
import re
import sys
import math
from pathlib import Path
from rapidfuzz import fuzz

SCRAPER_DATA = Path(__file__).parent / "scrape_output" / "final_recommendations.json"
GUIDE_DIR = Path.home() / ".skills/skills/guide-creator/sites/japan-2026"

FOOD_TYPES = {"restaurant", "cafe", "bar", "izakaya", "bakery", "food_hall", "food_stall"}

# Map Tokyo wards/areas to guide tabs
SHINJUKU_AREAS = ["Shinjuku", "Shibuya", "Yoyogi", "Harajuku", "Jinnan", "Sendagaya",
                  "Jingumae", "Tomigaya", "Kamiyamacho", "Maruyamacho", "Dogenzaka",
                  "Udagawacho", "Nishishinjuku", "Hyakunincho", "Okubo", "Takadanobaba",
                  "Kabukicho"]
EAST_TOKYO_AREAS = ["Taito", "Asakusa", "Ueno", "Akihabara", "Kanda", "Nihonbashi",
                    "Ginza", "Tsukiji", "Chuo", "Bunkyo", "Nezu", "Yanaka", "Sumida",
                    "Oshiage", "Ryogoku", "Koto", "Toyosu", "Nihombashi", "Jimbocho",
                    "Ochanomizu"]
# Everything else in Tokyo goes to whichever guide has space, but primarily:
WEST_TOKYO_AREAS = ["Roppongi", "Minato", "Azabu", "Ebisu", "Meguro", "Shinagawa",
                    "Nakano", "Suginami", "Setagaya", "Ota", "Kamata", "Ikebukuro",
                    "Toshima", "Nerima", "Kichijoji", "Daikanyama", "Nakameguro",
                    "Shinbashi", "Aoyama", "Omotesando", "Akasaka", "Azabujuban"]


def norm(name):
    name = re.sub(r'[^\w\s]', '', name.lower().strip())
    for suf in ['honten', 'hon ten', 'shinjukuten', 'tokyo', 'shinjuku', 'shibuya', 'ginza']:
        name = re.sub(rf'\s*{suf}\s*$', '', name)
    return name.strip()


def load_data():
    with open(SCRAPER_DATA, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [p for p in data if p.get("type") in FOOD_TYPES and p.get("confidence_score", 0) >= 3]


def get_guide_names(guide_file):
    """Extract all venue names from a guide."""
    path = GUIDE_DIR / guide_file
    if not path.exists():
        return set()
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    names = re.findall(r'class="venue-link"[^>]*>([^<]+)</a>', html)
    return set(names)


def is_in_guide(place_name, guide_names, threshold=85):
    pn = norm(place_name)
    if len(pn) < 3:
        return True  # Skip very short names
    for gn in guide_names:
        if fuzz.token_sort_ratio(pn, norm(gn)) >= threshold:
            return True
    return False


def classify_tokyo(place):
    """Classify a Tokyo place into shinjuku or east-tokyo guide based on address."""
    g = place.get("google_match") or {}
    addr = g.get("address", "")

    for area in SHINJUKU_AREAS:
        if area.lower() in addr.lower():
            return "shinjuku"

    for area in EAST_TOKYO_AREAS:
        if area.lower() in addr.lower():
            return "east-tokyo"

    # West Tokyo areas go to shinjuku guide (closest match, Stay 1 area)
    for area in WEST_TOKYO_AREAS:
        if area.lower() in addr.lower():
            return "shinjuku"  # Most west-side places are near Stay 1

    return "shinjuku"  # Default


def quality_score(p):
    g = p.get("google_match") or {}
    rating = g.get("rating") or 0
    reviews = g.get("user_ratings_total") or 0
    sources = p.get("source_count", 1)
    return rating * math.log(max(reviews, 1) + 1) * (1 + 0.2 * min(sources, 5))


def build_card_html(place):
    """Build a card HTML block for a Reddit Pick restaurant."""
    name = place["name"]
    city = place.get("city", "Tokyo")
    g = place.get("google_match") or {}
    rating = g.get("rating")
    reviews = g.get("user_ratings_total", 0)
    maps_url = g.get("google_maps_url", f"https://www.google.com/maps/search/{name.replace(' ', '+')}+{city}+Japan")
    ctx = place.get("context", "")
    if len(ctx) > 200:
        ctx = ctx[:200].rsplit(" ", 1)[0] + "..."
    ctx = ctx.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    # Build badges
    badges = []
    if rating:
        badges.append(f'<span class="badge" style="background:rgba(74,144,217,0.1);color:#2563eb">Google {rating}/5</span>')
    if reviews >= 1000:
        badges.append(f'<span class="badge" style="background:rgba(91,140,90,0.1);color:#3d6b3c">{reviews:,} reviews</span>')
    sources = place.get("source_count", 1)
    platform = "Reddit"
    if "youtube" in str(place.get("sources", [])):
        platform = "Reddit & YouTube"
    badges.append(f'<span class="badge" style="background:rgba(255,69,0,0.1);color:#ff4500">{platform} Buzz</span>')
    badge_html = "\n        ".join(badges)

    return f"""    <div class="card">
      <div class="card-name"><a href="{maps_url}" target="_blank" rel="noopener" class="venue-link">{name}</a></div>
      <div class="badges">
        {badge_html}
      </div>
      <div class="card-desc">{ctx}</div>
    </div>"""


def build_section_html(places, section_id="reddit-picks"):
    """Build a full Reddit Picks section with cards."""
    cards = "\n".join(build_card_html(p) for p in places)
    return f"""
    <h2 class="section-title" style="color:#ff4500">&#128293; Reddit Picks</h2>
    <p style="font-size:13px;color:#777;margin:-8px 0 16px">Highly-rated restaurants found via Reddit &amp; YouTube that aren't in the Tabelog database above. Sorted by community buzz.</p>
{cards}
"""


def inject_into_guide(guide_file, places_by_tab):
    """Inject Reddit Picks sections into a guide file."""
    path = GUIDE_DIR / guide_file
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    # Check if already injected
    if "Reddit Picks" in html:
        print(f"  {guide_file}: already has Reddit Picks, skipping")
        return 0

    total_injected = 0

    if places_by_tab is None:
        # Single-tab guide (Osaka, Kyoto, day trips) - inject before closing </div> of the main tab
        return 0

    for tab_id, places in places_by_tab.items():
        if not places:
            continue
        places.sort(key=quality_score, reverse=True)
        # Limit to top 15 per tab to keep guides manageable
        places = places[:15]

        section_html = build_section_html(places)

        # Find the closing </div> of this tab panel
        # Pattern: <div id="tab-{tab_id}" ... then find the last section before </div>\n\n<div id="tab-
        tab_pattern = rf'(<div id="tab-{re.escape(tab_id)}"[^>]*>)'
        tab_match = re.search(tab_pattern, html)
        if not tab_match:
            print(f"  {guide_file}: tab '{tab_id}' not found")
            continue

        # Find the end of this tab panel - it's the </div> before the next <div id="tab-
        tab_start = tab_match.start()
        # Find next tab panel or end of tabs
        next_tab = re.search(r'\n<div id="tab-', html[tab_match.end():])
        if next_tab:
            end_pos = tab_match.end() + next_tab.start()
        else:
            # Last tab - find the closing </div> that matches
            end_pos = len(html)

        # Find the last </div> before end_pos that closes the tab panel
        # We want to insert just before the closing </div> of the tab panel
        chunk = html[tab_start:end_pos]
        # The tab panel ends with \n</div>\n
        last_div = chunk.rfind("\n</div>")
        if last_div == -1:
            print(f"  {guide_file}: couldn't find end of tab '{tab_id}'")
            continue

        insert_pos = tab_start + last_div
        html = html[:insert_pos] + "\n" + section_html + html[insert_pos:]
        total_injected += len(places)
        print(f"  {guide_file} tab '{tab_id}': {len(places)} Reddit Picks added")

    if total_injected > 0:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    return total_injected


def inject_single_tab_guide(guide_file, places):
    """Inject Reddit Picks into a guide with a single content area (no tabs) or before tips tab."""
    path = GUIDE_DIR / guide_file
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    if "Reddit Picks" in html:
        print(f"  {guide_file}: already has Reddit Picks, skipping")
        return 0

    places.sort(key=quality_score, reverse=True)
    places = places[:15]

    section_html = build_section_html(places)

    # These guides have tabs by area (e.g., osaka has dotonbori/umeda tabs, kyoto has kawaramachi etc.)
    # Find the first area tab and inject into it
    # Look for tab panels
    tab_panels = list(re.finditer(r'<div id="tab-([^"]+)" class="tab-panel[^"]*">', html))

    if tab_panels:
        # Inject into the first non-tips, non-map tab
        for tp in tab_panels:
            tab_id = tp.group(1)
            if tab_id in ("tips", "map", "booking"):
                continue
            # Find end of this tab panel
            next_tab = re.search(r'\n<div id="tab-', html[tp.end():])
            if next_tab:
                end_pos = tp.end() + next_tab.start()
            else:
                end_pos = len(html)

            chunk = html[tp.start():end_pos]
            last_div = chunk.rfind("\n</div>")
            if last_div == -1:
                continue

            insert_pos = tp.start() + last_div
            html = html[:insert_pos] + "\n" + section_html + html[insert_pos:]

            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  {guide_file} tab '{tab_id}': {len(places)} Reddit Picks added")
            return len(places)

    # No tabs - inject before footer or end
    footer = html.rfind('<div class="footer">')
    if footer > 0:
        html = html[:footer] + section_html + "\n" + html[footer:]
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  {guide_file}: {len(places)} Reddit Picks added")
        return len(places)

    return 0


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    scraper_entries = load_data()
    print(f"Loaded {len(scraper_entries)} food places (score 3+)")

    # Collect all guide venue names across ALL guides
    all_guide_files = list(GUIDE_DIR.glob("*-guide.html"))
    all_names = set()
    for gf in all_guide_files:
        all_names.update(get_guide_names(gf.name))
    print(f"Total venue names across all guides: {len(all_names)}")

    # Filter to unmatched only
    unmatched = [p for p in scraper_entries if not is_in_guide(p["name"], all_names)]
    print(f"Unmatched restaurants: {len(unmatched)}")

    # Trip-relevant cities
    trip_cities = {"Tokyo", "Osaka", "Kyoto", "Kamakura", "Hakone", "Nara", "Yokohama", "Uji", "Himeji", ""}
    unmatched = [p for p in unmatched if p.get("city", "") in trip_cities]
    print(f"Trip-relevant unmatched: {len(unmatched)}")

    # === SHINJUKU EATS GUIDE ===
    shinjuku_places = {"shinjuku": [], "shibuya": [], "harajuku": []}
    east_tokyo_places = {}  # Will discover tab names from the guide

    # Read east-tokyo guide to find tab names
    et_path = GUIDE_DIR / "east-tokyo-eats-guide.html"
    with open(et_path, "r", encoding="utf-8") as f:
        et_html = f.read()
    et_tabs = re.findall(r'<div id="tab-([^"]+)" class="tab-panel', et_html)
    for t in et_tabs:
        if t not in ("tips", "map", "booking"):
            east_tokyo_places[t] = []

    # Classify Tokyo restaurants
    tokyo_unmatched = [p for p in unmatched if p.get("city") == "Tokyo"]
    for p in tokyo_unmatched:
        guide = classify_tokyo(p)
        g = p.get("google_match") or {}
        addr = g.get("address", "").lower()

        if guide == "east-tokyo":
            # Sub-classify into east-tokyo tabs
            placed = False
            for tab in east_tokyo_places:
                if tab.lower() in addr:
                    east_tokyo_places[tab].append(p)
                    placed = True
                    break
            if not placed:
                # Default to first tab
                first_tab = list(east_tokyo_places.keys())[0] if east_tokyo_places else None
                if first_tab:
                    east_tokyo_places[first_tab].append(p)
        else:
            # Sub-classify into shinjuku tabs
            if any(a.lower() in addr for a in ["shibuya", "jinnan", "dogenzaka", "maruyamacho", "udagawacho", "ebisu", "meguro", "daikanyama", "nakameguro"]):
                shinjuku_places["shibuya"].append(p)
            elif any(a.lower() in addr for a in ["harajuku", "jingumae", "omotesando", "aoyama"]):
                shinjuku_places["harajuku"].append(p)
            else:
                shinjuku_places["shinjuku"].append(p)

    # Inject into shinjuku guide
    total = 0
    print("\n=== Shinjuku Eats Guide ===")
    for tab, places in shinjuku_places.items():
        print(f"  Tab '{tab}': {len(places)} candidates")
    count = inject_into_guide("shinjuku-eats-guide.html", shinjuku_places)
    total += count

    # Inject into east-tokyo guide
    print("\n=== East Tokyo Eats Guide ===")
    for tab, places in east_tokyo_places.items():
        print(f"  Tab '{tab}': {len(places)} candidates")
    count = inject_into_guide("east-tokyo-eats-guide.html", east_tokyo_places)
    total += count

    # === OSAKA EATS GUIDE ===
    osaka_unmatched = [p for p in unmatched if p.get("city") == "Osaka"]
    print(f"\n=== Osaka Eats Guide === ({len(osaka_unmatched)} candidates)")
    if osaka_unmatched:
        count = inject_single_tab_guide("osaka-eats-guide.html", osaka_unmatched)
        total += count

    # === KYOTO EATS GUIDE ===
    kyoto_unmatched = [p for p in unmatched if p.get("city") in ("Kyoto", "Uji")]
    print(f"\n=== Kyoto Eats Guide === ({len(kyoto_unmatched)} candidates)")
    if kyoto_unmatched:
        count = inject_single_tab_guide("kyoto-eats-guide.html", kyoto_unmatched)
        total += count

    # === DAY TRIP GUIDES ===
    nara_himeji = [p for p in unmatched if p.get("city") in ("Nara", "Himeji")]
    print(f"\n=== Nara & Himeji Eats === ({len(nara_himeji)} candidates)")
    if nara_himeji:
        count = inject_single_tab_guide("day-trip-eats-nara-himeji-guide.html", nara_himeji)
        total += count

    coastal = [p for p in unmatched if p.get("city") in ("Kamakura", "Yokohama", "Hakone")]
    print(f"\n=== Coastal Day Trip Eats === ({len(coastal)} candidates)")
    if coastal:
        count = inject_single_tab_guide("day-trip-eats-coastal-guide.html", coastal)
        total += count

    print(f"\n{'='*40}")
    print(f"Done! {total} Reddit Picks added across all guides")


if __name__ == "__main__":
    main()

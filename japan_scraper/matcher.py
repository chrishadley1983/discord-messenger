"""Deduplication and Tabelog matching for extracted places."""

import json
import re
import unicodedata
from pathlib import Path

from rapidfuzz import fuzz, process

from .config import OUTPUT_DIR, TABELOG_JSON


def _normalise(name: str) -> str:
    """Normalise a place name for matching."""
    name = unicodedata.normalize("NFKC", name)
    name = name.lower().strip()
    # Remove common suffixes/prefixes
    name = re.sub(r'\s*(restaurant|cafe|café|bar|izakaya|ramen|shop|store)\s*$', '', name)
    # Remove punctuation
    name = re.sub(r'[^\w\s]', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name)
    return name.strip()


def _deduplicate(places: list[dict], threshold: int = 80) -> list[dict]:
    """Merge duplicate places using fuzzy matching."""
    if not places:
        return []

    merged = []
    used = set()

    for i, place in enumerate(places):
        if i in used:
            continue

        name_i = _normalise(place.get("name", ""))
        city_i = place.get("city", "").lower()
        group = [place]

        for j in range(i + 1, len(places)):
            if j in used:
                continue

            name_j = _normalise(places[j].get("name", ""))
            city_j = places[j].get("city", "").lower()

            # Only match within same city (or if city is empty)
            if city_i and city_j and city_i != city_j:
                continue

            score = fuzz.token_sort_ratio(name_i, name_j)
            if score >= threshold:
                group.append(places[j])
                used.add(j)

        # Merge group: keep the richest entry, aggregate sources
        best = max(group, key=lambda p: len(p.get("context", "")))
        sources = []
        source_urls = set()
        for p in group:
            platform = p.get("source_platform", "unknown")
            if platform not in sources:
                sources.append(platform)
            url = p.get("source_url", "")
            if url:
                source_urls.add(url)

        best["sources"] = sources
        best["source_count"] = len(source_urls)
        best["source_urls"] = list(source_urls)
        merged.append(best)
        used.add(i)

    return merged


def _load_tabelog() -> list[dict]:
    """Load Tabelog data from JSON."""
    if not TABELOG_JSON.exists():
        print(f"  Warning: Tabelog data not found at {TABELOG_JSON}")
        return []

    with open(TABELOG_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both flat array and location-keyed dict formats
    if isinstance(data, list):
        return data
    else:
        restaurants = []
        for location, entries in data.items():
            for entry in entries:
                entry["tabelog_location"] = location
                restaurants.append(entry)
        return restaurants


def _match_tabelog(places: list[dict], tabelog: list[dict], threshold: int = 85) -> list[dict]:
    """Match extracted places against Tabelog data."""
    if not tabelog:
        return places

    # Build lookup of normalised Tabelog names
    tabelog_names = [_normalise(r.get("name", "")) for r in tabelog]

    matched = 0
    for place in places:
        name = _normalise(place.get("name", ""))
        if not name:
            continue

        result = process.extractOne(
            name, tabelog_names,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=threshold,
        )

        if result:
            match_name, score, idx = result
            t = tabelog[idx]
            place["tabelog_match"] = {
                "name": t.get("name"),
                "score": float(t.get("score", 0)),
                "reviews": t.get("reviews"),
                "url": t.get("url"),
                "prices": t.get("prices", []),
                "area": t.get("area", ""),
                "match_confidence": score,
            }
            matched += 1

    print(f"  Tabelog matches: {matched}/{len(places)}")
    return places


def match_places() -> Path:
    """Deduplicate extracted places and match against Tabelog. Returns output file path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    input_path = OUTPUT_DIR / "extracted_places.json"
    if not input_path.exists():
        raise FileNotFoundError(f"Run 'extract' first: {input_path} not found")

    with open(input_path, "r", encoding="utf-8") as f:
        places = json.load(f)

    print(f"\n=== Dedup + Tabelog Matching ===")
    print(f"  Input: {len(places)} raw places")

    # Deduplicate
    deduped = _deduplicate(places)
    print(f"  After dedup: {len(deduped)} unique places")

    # Match against Tabelog
    tabelog = _load_tabelog()
    print(f"  Tabelog entries loaded: {len(tabelog)}")
    matched = _match_tabelog(deduped, tabelog)

    output_path = OUTPUT_DIR / "places_with_tabelog.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(matched, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(matched)} places saved to {output_path}")
    return output_path

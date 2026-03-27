"""Google Places validation and confidence scoring."""

import json
import time
import requests
from pathlib import Path

from .config import OUTPUT_DIR, HADLEY_API


def _search_google_places(name: str, city: str) -> dict | None:
    """Search for a place via Hadley API Google Places endpoint."""
    query = f"{name} {city} Japan" if city else f"{name} Japan"
    try:
        resp = requests.get(
            f"{HADLEY_API}/places/search",
            params={"query": query, "location": f"{city}, Japan" if city else "Tokyo, Japan"},
            timeout=30,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        places = data.get("places", [])
        if not places:
            return None

        # Return best match (first result from Google)
        return places[0]

    except requests.RequestException as e:
        print(f"  API error for '{name}': {e}")
        return None


def _compute_confidence(place: dict) -> tuple[int, str]:
    """Compute confidence score based on Tabelog + Google + source count."""
    tabelog_match = place.get("tabelog_match")
    google_match = place.get("google_match")
    source_count = place.get("source_count", 1)

    tabelog_score = tabelog_match["score"] if tabelog_match else 0
    google_rating = (google_match.get("rating") or 0) if google_match else 0
    google_reviews = (google_match.get("user_ratings_total") or 0) if google_match else 0

    has_good_tabelog = tabelog_score >= 3.5
    has_good_google = google_rating >= 4.0
    has_many_google_reviews = google_reviews >= 100
    has_multiple_sources = source_count >= 2

    if has_good_tabelog and has_good_google and has_multiple_sources:
        return 5, "Verified (Strong)"
    elif has_good_tabelog or (has_good_google and has_multiple_sources):
        return 4, "Verified"
    elif has_good_google and has_many_google_reviews:
        return 3, "Likely Good"
    elif google_match:
        return 2, "Exists"
    else:
        return 1, "Unverified"


def validate_places() -> Path:
    """Validate places via Google Places API and compute confidence scores. Returns output file path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    input_path = OUTPUT_DIR / "places_with_tabelog.json"
    if not input_path.exists():
        raise FileNotFoundError(f"Run 'match' first: {input_path} not found")

    with open(input_path, "r", encoding="utf-8") as f:
        places = json.load(f)

    print(f"\n=== Google Places Validation ===")
    print(f"  Validating {len(places)} places...")

    # Try to resume from checkpoint
    checkpoint_path = OUTPUT_DIR / "validation_checkpoint.json"
    if checkpoint_path.exists():
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            places = json.load(f)
        print("  Resuming from checkpoint...")

    skipped = 0
    for i, place in enumerate(places):
        name = place.get("name", "")
        city = place.get("city", "")
        safe_name = name.encode("ascii", "replace").decode("ascii")

        # Skip if already validated (resume support)
        if "google_match" in place:
            skipped += 1
            continue

        print(f"  [{i+1}/{len(places)}] {safe_name}...", end=" ")

        google_result = _search_google_places(name, city)
        if google_result:
            place["google_match"] = google_result
            rating = google_result.get("rating", "N/A")
            reviews = google_result.get("user_ratings_total", 0)
            print(f"  Found: Google {rating}/5 ({reviews} reviews)")
        else:
            place["google_match"] = None
            print("  Not found")

        # Save checkpoint every 50 places
        if (i + 1) % 50 == 0:
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(places, f, indent=2, ensure_ascii=False)

        time.sleep(0.3)  # Be polite to the API

    if skipped:
        print(f"  (Skipped {skipped} already-validated places)")

    # Clean up checkpoint
    if checkpoint_path.exists():
        checkpoint_path.unlink()

    # Compute confidence scores
    print("\n=== Confidence Scoring ===")
    score_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for place in places:
        score, label = _compute_confidence(place)
        place["confidence_score"] = score
        place["confidence_label"] = label
        score_counts[score] += 1

    # Sort by confidence score descending, then by source count
    places.sort(key=lambda p: (p["confidence_score"], p.get("source_count", 0)), reverse=True)

    print(f"  Score 5 (Verified Strong): {score_counts[5]}")
    print(f"  Score 4 (Verified):        {score_counts[4]}")
    print(f"  Score 3 (Likely Good):     {score_counts[3]}")
    print(f"  Score 2 (Exists):          {score_counts[2]}")
    print(f"  Score 1 (Unverified):      {score_counts[1]}")

    output_path = OUTPUT_DIR / "final_recommendations.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(places, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(places)} places scored and saved to {output_path}")
    return output_path

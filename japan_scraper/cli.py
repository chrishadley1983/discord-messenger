"""CLI runner for the Japan scraper pipeline."""

import argparse
import json
import sys
import requests
from pathlib import Path

from .config import OUTPUT_DIR, HADLEY_API


def cmd_scrape_reddit(args):
    from .reddit_scraper import scrape_reddit
    scrape_reddit()


def cmd_scrape_youtube(args):
    from .youtube_scraper import scrape_youtube
    scrape_youtube()


def cmd_extract(args):
    from .extractor import extract_places
    extract_places()


def cmd_match(args):
    from .matcher import match_places
    match_places()


def cmd_validate(args):
    from .validator import validate_places
    validate_places()


def cmd_store(args):
    """Save validated recommendations to Second Brain."""
    input_path = OUTPUT_DIR / "final_recommendations.json"
    if not input_path.exists():
        print(f"Error: Run 'validate' first: {input_path} not found")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        places = json.load(f)

    # Only store places with confidence >= threshold
    min_score = args.min_score if hasattr(args, "min_score") else 2
    to_store = [p for p in places if p.get("confidence_score", 0) >= min_score]

    print(f"\n=== Storing {len(to_store)} places (confidence >= {min_score}) ===")

    stored = 0
    for i, place in enumerate(to_store):
        name = place.get("name", "Unknown")
        city = place.get("city", "")
        ptype = place.get("type", "place")
        confidence = place.get("confidence_label", "Unknown")

        # Build content for Second Brain
        lines = [f"# {name}"]
        lines.append(f"**Type:** {ptype}")
        if city:
            lines.append(f"**City:** {city}")
        if place.get("neighbourhood"):
            lines.append(f"**Area:** {place['neighbourhood']}")
        if place.get("context"):
            lines.append(f"**Why:** {place['context']}")
        lines.append(f"**Confidence:** {confidence} ({place.get('confidence_score', 0)}/5)")

        # Tabelog data
        tabelog = place.get("tabelog_match")
        if tabelog:
            lines.append(f"**Tabelog:** {tabelog['score']}★ ({tabelog.get('reviews', '?')} reviews)")
            lines.append(f"**Tabelog URL:** {tabelog.get('url', '')}")
            if tabelog.get("prices"):
                lines.append(f"**Prices:** {', '.join(tabelog['prices'])}")

        # Google data
        google = place.get("google_match")
        if google:
            lines.append(f"**Google:** {google.get('rating', 'N/A')}★ ({google.get('user_ratings_total', 0)} reviews)")
            if google.get("address"):
                lines.append(f"**Address:** {google['address']}")

        # Sources
        urls = place.get("source_urls", [])
        if urls:
            lines.append(f"**Sources ({len(urls)}):**")
            for url in urls[:5]:
                lines.append(f"- {url}")

        content = "\n".join(lines)

        # Build tags
        tags = ["japan-2026", ptype]
        if city:
            tags.append(city.lower())
        if place.get("neighbourhood"):
            tags.append(place["neighbourhood"].lower())

        try:
            resp = requests.post(
                f"{HADLEY_API}/brain/save",
                json={"content": content, "note": f"Japan 2026 {ptype}: {name}", "tags": tags},
                timeout=30,
            )
            if resp.status_code == 200:
                stored += 1
                print(f"  [{i+1}/{len(to_store)}] ✓ {name} ({confidence})")
            else:
                print(f"  [{i+1}/{len(to_store)}] ✗ {name} — HTTP {resp.status_code}")
        except requests.RequestException as e:
            print(f"  [{i+1}/{len(to_store)}] ✗ {name} — {e}")

    print(f"\nDone! {stored}/{len(to_store)} places stored in Second Brain")


def cmd_summary(args):
    """Print a summary of the final recommendations."""
    input_path = OUTPUT_DIR / "final_recommendations.json"
    if not input_path.exists():
        print(f"No results yet. Run the pipeline first.")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        places = json.load(f)

    print(f"\n{'='*60}")
    print(f"  JAPAN 2026 — Scraped Recommendations Summary")
    print(f"{'='*60}")
    print(f"  Total places: {len(places)}")

    # By confidence
    by_score = {}
    for p in places:
        label = p.get("confidence_label", "Unknown")
        by_score[label] = by_score.get(label, 0) + 1
    print(f"\n  By confidence:")
    for label, count in sorted(by_score.items(), key=lambda x: -x[1]):
        print(f"    {label}: {count}")

    # By type
    by_type = {}
    for p in places:
        t = p.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    print(f"\n  By type:")
    for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"    {t}: {count}")

    # By city
    by_city = {}
    for p in places:
        c = p.get("city", "unknown")
        by_city[c] = by_city.get(c, 0) + 1
    print(f"\n  By city:")
    for c, count in sorted(by_city.items(), key=lambda x: -x[1]):
        print(f"    {c}: {count}")

    # Top 10 highest confidence
    print(f"\n  Top 10 (highest confidence):")
    for p in places[:10]:
        name = p.get("name", "?")
        city = p.get("city", "")
        score = p.get("confidence_score", 0)
        label = p.get("confidence_label", "")
        tabelog = p.get("tabelog_match", {})
        tabelog_str = f" | Tabelog {tabelog['score']}" if tabelog else ""
        google = p.get("google_match", {})
        google_str = f" | Google {google.get('rating', 'N/A')}★" if google else ""
        print(f"    [{score}] {name} ({city}){tabelog_str}{google_str} — {label}")


def cmd_run_all(args):
    """Run the complete pipeline."""
    print("=" * 60)
    print("  JAPAN SCRAPER — Full Pipeline")
    print("=" * 60)

    print("\n[1/5] Scraping Reddit...")
    from .reddit_scraper import scrape_reddit
    scrape_reddit()

    print("\n[2/5] Scraping YouTube...")
    from .youtube_scraper import scrape_youtube
    scrape_youtube()

    print("\n[3/5] Extracting places (Claude)...")
    from .extractor import extract_places
    extract_places()

    print("\n[4/5] Dedup + Tabelog matching...")
    from .matcher import match_places
    match_places()

    print("\n[5/5] Google Places validation + scoring...")
    from .validator import validate_places
    validate_places()

    print("\n" + "=" * 60)
    cmd_summary(args)


def main():
    parser = argparse.ArgumentParser(description="Japan 2026 trip recommendation scraper")
    subparsers = parser.add_subparsers(dest="command", help="Pipeline stage to run")

    subparsers.add_parser("scrape-reddit", help="Scrape Reddit for recommendations")
    subparsers.add_parser("scrape-youtube", help="Scrape YouTube for recommendations")
    subparsers.add_parser("extract", help="Extract place names using Claude")
    subparsers.add_parser("match", help="Deduplicate and match against Tabelog")
    subparsers.add_parser("validate", help="Validate via Google Places and score")

    store_parser = subparsers.add_parser("store", help="Save to Second Brain")
    store_parser.add_argument("--min-score", type=int, default=2, help="Min confidence score to store (default: 2)")

    subparsers.add_parser("summary", help="Print summary of results")
    subparsers.add_parser("run-all", help="Run complete pipeline")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "scrape-reddit": cmd_scrape_reddit,
        "scrape-youtube": cmd_scrape_youtube,
        "extract": cmd_extract,
        "match": cmd_match,
        "validate": cmd_validate,
        "store": cmd_store,
        "summary": cmd_summary,
        "run-all": cmd_run_all,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()

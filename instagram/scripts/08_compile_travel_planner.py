"""
Step 8: Compile travel posts into per-country markdown files for Claude Desktop.

Reads master_index.json + per-post analysis/caption/transcript and produces:
  travel_planner/INDEX.md        - master overview
  travel_planner/japan.md        - per-country detail files
  travel_planner/italy.md
  ...

Output is also copied to Google Drive for use as a Claude Desktop Project.
"""

import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
INDEX_FILE = ROOT / "data" / "master_index.json"
OUTPUT_DIR = ROOT / "travel_planner"
DRIVE_DIR = Path(r"G:\My Drive\Instagram Saved\travel_planner")


def read_text(p: Path) -> str | None:
    if p.exists():
        text = p.read_text(encoding="utf-8", errors="replace").strip()
        return text if text else None
    return None


def read_json(p: Path) -> dict | None:
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return None
    return None


def slugify(name: str) -> str:
    """Convert country name to filename-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def load_travel_posts() -> dict[str, list[dict]]:
    """Load and group travel posts by country."""
    index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    travel = [p for p in index["posts"] if "Travel" in p.get("collections", [])]

    by_country = defaultdict(list)

    for entry in travel:
        sc = entry["shortcode"]
        post_dir = DOWNLOADS / sc
        if not post_dir.exists():
            continue

        analysis = read_json(post_dir / "analysis.json")
        caption = read_text(post_dir / "caption.txt")
        transcript = read_text(post_dir / "transcript.txt")
        meta = read_json(post_dir / "meta.json")

        country = "Unknown"
        if analysis:
            country = analysis.get("country") or "Unknown"

        post = {
            "shortcode": sc,
            "url": entry.get("url", f"https://www.instagram.com/p/{sc}/"),
            "username": entry.get("username", ""),
            "country": country,
            "city": analysis.get("city_or_region", "") if analysis else "",
            "location": analysis.get("specific_location", "") if analysis else "",
            "category": analysis.get("category", "") if analysis else "",
            "cost": analysis.get("estimated_cost_level", "") if analysis else "",
            "best_time": analysis.get("best_time_to_visit", "") if analysis else "",
            "summary": analysis.get("one_line_summary", "") if analysis else "",
            "confidence": analysis.get("confidence", "") if analysis else "",
            "notes": analysis.get("notes", "") if analysis else "",
            "caption": caption,
            "transcript": transcript,
            "likes": meta.get("likes") if meta else None,
            "date": meta.get("date_utc") if meta else None,
        }

        by_country[country].append(post)

    return dict(by_country)


def format_post(post: dict) -> str:
    """Format a single post as markdown."""
    lines = []

    # Title line
    title = post["summary"] or post["shortcode"]
    lines.append(f"### {title}")
    lines.append("")

    # Metadata table
    meta_items = []
    if post["city"]:
        meta_items.append(f"**City/Region:** {post['city']}")
    if post["location"]:
        meta_items.append(f"**Specific Location:** {post['location']}")
    if post["category"]:
        meta_items.append(f"**Category:** {post['category'].replace('_', ' ').title()}")
    if post["cost"]:
        meta_items.append(f"**Cost Level:** {post['cost']}")
    if post["best_time"]:
        meta_items.append(f"**Best Time to Visit:** {post['best_time']}")
    if post["username"]:
        meta_items.append(f"**Source:** @{post['username']}")
    if post["likes"]:
        meta_items.append(f"**Likes:** {post['likes']:,}")

    if meta_items:
        lines.append(" | ".join(meta_items))
        lines.append("")

    # Caption
    if post["caption"]:
        lines.append("**Caption:**")
        lines.append(f"> {post['caption'][:2000]}")
        lines.append("")

    # Transcript
    if post["transcript"]:
        lines.append("**What they said:**")
        lines.append(f"> {post['transcript'][:2000]}")
        lines.append("")

    # Notes
    if post["notes"]:
        lines.append(f"**Notes:** {post['notes']}")
        lines.append("")

    # Link
    lines.append(f"[View on Instagram]({post['url']})")
    lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def write_country_file(country: str, posts: list[dict]) -> Path:
    """Write a single country markdown file."""
    slug = slugify(country)
    filepath = OUTPUT_DIR / f"{slug}.md"

    # Group posts by city within country
    by_city = defaultdict(list)
    for p in posts:
        city = p["city"] or "General"
        by_city[city].append(p)

    lines = []
    lines.append(f"# {country} - Travel Tips from Instagram")
    lines.append("")
    lines.append(f"*{len(posts)} saved posts about {country}.*")
    lines.append("")
    lines.append("Use this guide to plan trips, find restaurants, activities, and hidden gems.")
    lines.append("Each entry includes the original caption and spoken content from the video.")
    lines.append("")

    # Table of contents
    lines.append("## Contents")
    lines.append("")
    for city, city_posts in sorted(by_city.items()):
        categories = set(p["category"].replace("_", " ").title() for p in city_posts if p["category"])
        cat_str = f" ({', '.join(sorted(categories))})" if categories else ""
        lines.append(f"- **{city}** - {len(city_posts)} posts{cat_str}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Posts grouped by city
    for city, city_posts in sorted(by_city.items()):
        lines.append(f"## {city}")
        lines.append("")

        # Sort by category then by likes
        city_posts.sort(key=lambda p: (p["category"] or "zzz", -(p["likes"] or 0)))

        for post in city_posts:
            lines.append(format_post(post))

    content = "\n".join(lines)
    filepath.write_text(content, encoding="utf-8")
    return filepath


def write_index(by_country: dict[str, list[dict]]) -> Path:
    """Write the master INDEX.md file."""
    filepath = OUTPUT_DIR / "INDEX.md"

    total = sum(len(posts) for posts in by_country.values())

    lines = []
    lines.append("# Instagram Travel Planner")
    lines.append("")
    lines.append(f"*{total} saved travel posts across {len(by_country)} destinations.*")
    lines.append("")
    lines.append("Each country file below contains detailed tips, captions, and transcripts")
    lines.append("from saved Instagram reels. Use these to plan trips, find restaurants,")
    lines.append("discover activities, and get local recommendations.")
    lines.append("")
    lines.append("## Destinations")
    lines.append("")
    lines.append("| Country | Posts | Top Categories | File |")
    lines.append("|---------|-------|----------------|------|")

    for country, posts in sorted(by_country.items(), key=lambda x: -len(x[1])):
        slug = slugify(country)
        categories = defaultdict(int)
        for p in posts:
            if p["category"]:
                cat = p["category"].replace("_", " ").title()
                categories[cat] += 1
        top_cats = ", ".join(
            f"{cat} ({n})" for cat, n in sorted(categories.items(), key=lambda x: -x[1])[:3]
        )
        lines.append(f"| {country} | {len(posts)} | {top_cats} | [{slug}.md]({slug}.md) |")

    lines.append("")
    lines.append("## How to Use")
    lines.append("")
    lines.append("Ask me things like:")
    lines.append("- \"Plan a 5-day Japan itinerary focusing on food\"")
    lines.append("- \"What are the best places to visit in Tokyo?\"")
    lines.append("- \"Find budget-friendly travel tips from my saved posts\"")
    lines.append("- \"What did people recommend for Thailand?\"")
    lines.append("- \"Create a day-by-day Kyoto plan using my saved reels\"")
    lines.append("")

    content = "\n".join(lines)
    filepath.write_text(content, encoding="utf-8")
    return filepath


def main():
    print("=== Compiling Travel Planner ===")
    print()

    by_country = load_travel_posts()
    total = sum(len(v) for v in by_country.values())
    print(f"Found {total} travel posts across {len(by_country)} countries")
    print()

    # Clean and create output dir
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    # Write per-country files
    for country, posts in sorted(by_country.items(), key=lambda x: -len(x[1])):
        filepath = write_country_file(country, posts)
        size_kb = filepath.stat().st_size / 1024
        print(f"  {country}: {len(posts)} posts -> {filepath.name} ({size_kb:.0f}KB)")

    # Write index
    index_path = write_index(by_country)
    print(f"\n  Index: {index_path.name}")

    # Copy to Google Drive
    print(f"\nSyncing to Google Drive...")
    if DRIVE_DIR.exists():
        shutil.rmtree(DRIVE_DIR)
    shutil.copytree(OUTPUT_DIR, DRIVE_DIR)
    print(f"  Copied to {DRIVE_DIR}")

    print("\n=== Done ===")
    print(f"Local:  {OUTPUT_DIR}")
    print(f"Drive:  {DRIVE_DIR}")
    print(f"\nAdd {DRIVE_DIR} as a Claude Desktop Project for trip planning.")


if __name__ == "__main__":
    main()

"""
06_compile_outputs.py — Assemble analysis.json outputs into final markdown guides.

Reads all analysis.json files, groups by collection, and generates:
  - output/travel_guide.md
  - output/recipe_book.md
  - output/stretching_guide.md
  - output/life_hacks.md
  - output/uncollected.md
  - output/summary.md
"""

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Paths
INSTAGRAM_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = INSTAGRAM_DIR / "data"
DOWNLOADS_DIR = INSTAGRAM_DIR / "downloads"
OUTPUT_DIR = INSTAGRAM_DIR / "output"

MASTER_INDEX_PATH = DATA_DIR / "master_index.json"
PROGRESS_PATH = DATA_DIR / "progress.json"


def load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_all_analyses(posts: list[dict]) -> dict[str, dict]:
    """Load all analysis.json files, keyed by shortcode."""
    analyses = {}
    for post in posts:
        sc = post["shortcode"]
        path = DOWNLOADS_DIR / sc / "analysis.json"
        data = load_json(path)
        if data:
            # Merge post metadata
            data["_shortcode"] = sc
            data["_username"] = post.get("username", "")
            data["_url"] = post.get("url", "")
            data["_collections"] = post.get("collections", [])
            analyses[sc] = data
    return analyses


def get_collection_posts(analyses: dict, posts: list[dict], collection: str) -> list[dict]:
    """Get all analysed posts for a specific collection."""
    result = []
    for post in posts:
        sc = post["shortcode"]
        if sc not in analyses:
            continue
        colls = post.get("collections", [])
        if collection == "_uncollected":
            if not colls:
                result.append(analyses[sc])
        elif collection in colls:
            result.append(analyses[sc])
    return result


def safe_get(d: dict, *keys, default=""):
    """Safely get a nested value."""
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d if d is not None else default


# ── Travel Guide ──────────────────────────────────────────────────

def compile_travel(posts: list[dict]) -> str:
    lines = [
        "# Travel Guide",
        "",
        f"*{len(posts)} saved travel posts, organised by destination.*",
        "",
        "---",
        "",
    ]

    # Group: country → city → category
    tree: dict[str, dict[str, dict[str, list]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )

    for p in posts:
        country = safe_get(p, "country", default="Unknown Country")
        city = safe_get(p, "city_or_region", default="Unknown Location")
        cat = safe_get(p, "category", default="general")
        tree[country][city][cat].append(p)

    for country in sorted(tree.keys()):
        lines.append(f"## {country}")
        lines.append("")

        for city in sorted(tree[country].keys()):
            lines.append(f"### {city}")
            lines.append("")

            for cat in sorted(tree[country][city].keys()):
                cat_posts = tree[country][city][cat]
                cat_label = cat.replace("_", " ").title()
                lines.append(f"#### {cat_label}")
                lines.append("")

                for p in cat_posts:
                    summary = safe_get(p, "one_line_summary", default="")
                    location = safe_get(p, "specific_location", default="")
                    cost = safe_get(p, "estimated_cost_level", default="")
                    time = safe_get(p, "best_time_to_visit", default="")
                    username = safe_get(p, "_username")
                    url = safe_get(p, "_url")

                    lines.append(f"- **{summary or 'Untitled'}**")
                    if location:
                        lines.append(f"  - Location: {location}")
                    if cost:
                        lines.append(f"  - Cost: {cost}")
                    if time:
                        lines.append(f"  - Best time: {time}")
                    lines.append(f"  - Source: [@{username}]({url})")
                    lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ── Recipe Book ───────────────────────────────────────────────────

def compile_recipes(posts: list[dict]) -> str:
    lines = [
        "# Recipe Book",
        "",
        f"*{len(posts)} saved recipe posts, organised by cuisine and meal type.*",
        "",
        "---",
        "",
    ]

    # Group: cuisine → meal_type
    tree: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for p in posts:
        cuisine = safe_get(p, "cuisine_type", default="Other")
        meal = safe_get(p, "meal_type", default="other")
        tree[cuisine][meal].append(p)

    for cuisine in sorted(tree.keys()):
        lines.append(f"## {cuisine}")
        lines.append("")

        for meal in sorted(tree[cuisine].keys()):
            meal_label = meal.replace("_", " ").title()
            lines.append(f"### {meal_label}")
            lines.append("")

            for p in tree[cuisine][meal]:
                dish = safe_get(p, "dish_name", default="Untitled Recipe")
                ingredients = safe_get(p, "ingredients_visible", default=[])
                method = safe_get(p, "method_summary", default="")
                tags = safe_get(p, "dietary_tags", default=[])
                difficulty = safe_get(p, "difficulty", default="")
                prep = safe_get(p, "prep_time_estimate", default="")
                username = safe_get(p, "_username")
                url = safe_get(p, "_url")

                lines.append(f"#### {dish}")
                lines.append("")

                meta_parts = []
                if difficulty:
                    meta_parts.append(f"Difficulty: {difficulty}")
                if prep:
                    meta_parts.append(f"Prep: {prep}")
                if tags and isinstance(tags, list):
                    meta_parts.append(f"Tags: {', '.join(tags)}")
                if meta_parts:
                    lines.append(f"*{' | '.join(meta_parts)}*")
                    lines.append("")

                if ingredients and isinstance(ingredients, list):
                    lines.append("**Ingredients:**")
                    for ing in ingredients:
                        lines.append(f"- {ing}")
                    lines.append("")

                if method:
                    lines.append("**Method:**")
                    lines.append(method)
                    lines.append("")

                lines.append(f"Source: [@{username}]({url})")
                lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ── Stretching Guide ─────────────────────────────────────────────

def compile_stretching(posts: list[dict]) -> str:
    lines = [
        "# Stretching Guide",
        "",
        f"*{len(posts)} saved stretching posts, organised by body area.*",
        "",
        "---",
        "",
    ]

    # Group by body_area
    tree: dict[str, list] = defaultdict(list)

    for p in posts:
        area = safe_get(p, "body_area", default="general")
        tree[area].append(p)

    for area in sorted(tree.keys()):
        area_label = area.replace("_", " ").title()
        lines.append(f"## {area_label}")
        lines.append("")

        for p in tree[area]:
            name = safe_get(p, "exercise_name", default="Untitled Exercise")
            duration = safe_get(p, "duration_or_reps", default="")
            instructions = safe_get(p, "instructions_summary", default="")
            equipment = safe_get(p, "equipment_needed", default="none")
            difficulty = safe_get(p, "difficulty", default="")
            username = safe_get(p, "_username")
            url = safe_get(p, "_url")

            lines.append(f"### {name}")
            lines.append("")

            meta_parts = []
            if duration:
                meta_parts.append(f"Duration/Reps: {duration}")
            if difficulty:
                meta_parts.append(f"Difficulty: {difficulty}")
            if equipment and equipment != "none":
                meta_parts.append(f"Equipment: {equipment}")
            if meta_parts:
                lines.append(f"*{' | '.join(meta_parts)}*")
                lines.append("")

            if instructions:
                lines.append(instructions)
                lines.append("")

            lines.append(f"Source: [@{username}]({url})")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ── Life Hacks ────────────────────────────────────────────────────

def compile_life_hacks(posts: list[dict]) -> str:
    lines = [
        "# Life Hacks",
        "",
        f"*{len(posts)} saved life hack posts, organised by category.*",
        "",
        "---",
        "",
    ]

    tree: dict[str, list] = defaultdict(list)

    for p in posts:
        cat = safe_get(p, "category", default="other")
        tree[cat].append(p)

    for cat in sorted(tree.keys()):
        cat_label = cat.replace("_", " ").title()
        lines.append(f"## {cat_label}")
        lines.append("")

        for p in tree[cat]:
            title = safe_get(p, "hack_title", default="Untitled Hack")
            desc = safe_get(p, "description", default="")
            steps = safe_get(p, "steps", default="")
            items = safe_get(p, "items_needed", default=[])
            username = safe_get(p, "_username")
            url = safe_get(p, "_url")

            lines.append(f"### {title}")
            lines.append("")

            if desc:
                lines.append(desc)
                lines.append("")

            if items and isinstance(items, list):
                lines.append("**You'll need:**")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

            if steps:
                lines.append("**Steps:**")
                lines.append(steps)
                lines.append("")

            lines.append(f"Source: [@{username}]({url})")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ── Uncollected ───────────────────────────────────────────────────

def compile_uncollected(posts: list[dict]) -> str:
    lines = [
        "# Uncollected Posts",
        "",
        f"*{len(posts)} saved posts not in any collection, auto-classified.*",
        "",
        "---",
        "",
    ]

    # Group by best_guess_collection
    tree: dict[str, list] = defaultdict(list)

    for p in posts:
        guess = safe_get(p, "best_guess_collection", default="Other")
        tree[guess].append(p)

    for guess in sorted(tree.keys()):
        lines.append(f"## Likely: {guess}")
        lines.append("")

        for p in tree[guess]:
            confidence = safe_get(p, "confidence", default="")
            reasoning = safe_get(p, "reasoning", default="")
            notes = safe_get(p, "notes", default="")
            username = safe_get(p, "_username")
            url = safe_get(p, "_url")

            # Try to find a title from various fields
            title = (
                safe_get(p, "dish_name") or
                safe_get(p, "exercise_name") or
                safe_get(p, "hack_title") or
                safe_get(p, "one_line_summary") or
                "Untitled"
            )

            lines.append(f"- **{title}** ({confidence} confidence)")
            if reasoning:
                lines.append(f"  - {reasoning}")
            if notes:
                lines.append(f"  - {notes}")
            lines.append(f"  - Source: [@{username}]({url})")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ── Summary ───────────────────────────────────────────────────────

def compile_summary(master_index: dict, progress: dict, analyses: dict) -> str:
    posts = master_index["posts"]
    total = len(posts)

    # Count statuses
    downloaded = sum(1 for p in progress["posts"].values() if p.get("downloaded"))
    extracted = sum(1 for p in progress["posts"].values() if p.get("frames_extracted"))
    transcribed = sum(1 for p in progress["posts"].values() if p.get("transcribed"))
    analysed = sum(1 for p in progress["posts"].values() if p.get("analysed"))

    # Count by collection
    coll_counts = defaultdict(int)
    coll_analysed = defaultdict(int)
    for post in posts:
        colls = post.get("collections", [])
        key = colls[0] if colls else "Uncollected"
        coll_counts[key] += 1
        if post["shortcode"] in analyses:
            coll_analysed[key] += 1

    # Low confidence posts
    low_conf = [
        a for a in analyses.values()
        if safe_get(a, "confidence") == "low"
    ]

    # Failures
    failures = {}
    for stage in ["download", "extraction", "transcription"]:
        fail_path = DATA_DIR / f"{stage}_failures.json"
        if fail_path.exists():
            data = load_json(fail_path)
            if data and data.get("failures"):
                failures[stage] = data["failures"]

    lines = [
        "# Pipeline Summary",
        "",
        f"*Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
        "## Pipeline Progress",
        "",
        "| Stage | Count | % |",
        "|-------|-------|---|",
        f"| Total posts | {total} | 100% |",
        f"| Downloaded | {downloaded} | {downloaded*100//total}% |",
        f"| Frames extracted | {extracted} | {extracted*100//total}% |",
        f"| Transcribed | {transcribed} | {transcribed*100//total}% |",
        f"| Analysed | {analysed} | {analysed*100//total}% |",
        "",
        "## By Collection",
        "",
        "| Collection | Total | Analysed |",
        "|------------|-------|----------|",
    ]

    for coll in ["Travel", "Recipes", "Stretching", "Life Hacks etc", "Uncollected"]:
        lines.append(f"| {coll} | {coll_counts.get(coll, 0)} | {coll_analysed.get(coll, 0)} |")

    lines.append("")

    if low_conf:
        lines.extend([
            f"## Low Confidence Posts ({len(low_conf)})",
            "",
        ])
        for p in low_conf:
            lines.append(f"- [{p.get('_shortcode')}]({p.get('_url')}) "
                         f"@{p.get('_username')} — {safe_get(p, 'notes', default='no notes')}")
        lines.append("")

    if failures:
        lines.extend([
            "## Failures",
            "",
        ])
        for stage, fails in failures.items():
            lines.append(f"### {stage.title()} ({len(fails)})")
            lines.append("")
            for sc, reason in list(fails.items())[:20]:
                lines.append(f"- `{sc}`: {reason}")
            if len(fails) > 20:
                lines.append(f"- ... and {len(fails) - 20} more")
            lines.append("")

    lines.extend([
        "## Output Files",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| `travel_guide.md` | Travel posts by Country > City > Category |",
        "| `recipe_book.md` | Recipes by Cuisine > Meal Type |",
        "| `stretching_guide.md` | Stretches by Body Area |",
        "| `life_hacks.md` | Life hacks by Category |",
        "| `uncollected.md` | Auto-classified uncollected posts |",
        "| `summary.md` | This file |",
    ])

    return "\n".join(lines)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    master_index = load_json(MASTER_INDEX_PATH)
    progress = load_json(PROGRESS_PATH)
    posts = master_index["posts"]

    print("Loading analyses...")
    analyses = load_all_analyses(posts)
    print(f"  Found {len(analyses)} analysis files\n")

    if not analyses:
        print("No analysis.json files found. Run the analysis step first.")
        return

    # Compile each guide
    compilers = [
        ("Travel", "travel_guide.md", compile_travel),
        ("Recipes", "recipe_book.md", compile_recipes),
        ("Stretching", "stretching_guide.md", compile_stretching),
        ("Life Hacks etc", "life_hacks.md", compile_life_hacks),
        ("_uncollected", "uncollected.md", compile_uncollected),
    ]

    for coll, filename, compiler in compilers:
        coll_posts = get_collection_posts(analyses, posts, coll)
        if coll_posts:
            content = compiler(coll_posts)
            path = OUTPUT_DIR / filename
            path.write_text(content, encoding="utf-8")
            print(f"  {filename}: {len(coll_posts)} posts")
        else:
            print(f"  {filename}: no analysed posts (skipped)")

    # Summary
    summary = compile_summary(master_index, progress, analyses)
    summary_path = OUTPUT_DIR / "summary.md"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"  summary.md: written")

    print(f"\nAll outputs written to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()

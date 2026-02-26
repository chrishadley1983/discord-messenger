"""
05_analyse_batch.py — Generate batch manifests + prompts for Claude Code analysis.

Groups posts into batches of 20 (by collection), generates:
  - data/batch_NNN_manifest.json   (list of shortcodes + paths)
  - data/batch_NNN_prompt.md       (instructions for Claude Code)

Then optionally runs Claude Code on each batch via subprocess.

Usage:
    python scripts/05_analyse_batch.py                    # Generate batches only
    python scripts/05_analyse_batch.py --run              # Generate + run all
    python scripts/05_analyse_batch.py --run --batch 3    # Run specific batch
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Paths
INSTAGRAM_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = INSTAGRAM_DIR / "data"
DOWNLOADS_DIR = INSTAGRAM_DIR / "downloads"

MASTER_INDEX_PATH = DATA_DIR / "master_index.json"
PROGRESS_PATH = DATA_DIR / "progress.json"

BATCH_SIZE = 20

# Collection-specific analysis schemas
SCHEMAS = {
    "Travel": {
        "fields": [
            "country", "city_or_region", "specific_location",
            "category (sightseeing | food_and_drink | accommodation | transport | culture | nightlife | nature | shopping | tips)",
            "best_time_to_visit", "estimated_cost_level (budget | mid | luxury)",
            "one_line_summary",
        ],
        "grouping_hint": "Group by country, then city/region, then category.",
    },
    "Recipes": {
        "fields": [
            "dish_name", "cuisine_type", "meal_type (breakfast | lunch | dinner | snack | dessert | drink)",
            "ingredients_visible (list)", "method_summary (brief steps)",
            "dietary_tags (vegetarian | vegan | gluten_free | dairy_free | etc.)",
            "difficulty (easy | medium | hard)", "prep_time_estimate",
        ],
        "grouping_hint": "Group by cuisine type, then meal type.",
    },
    "Stretching": {
        "fields": [
            "exercise_name", "body_area (neck | shoulders | back | hips | hamstrings | quads | calves | full_body | etc.)",
            "duration_or_reps", "instructions_summary (numbered steps)",
            "equipment_needed (none | foam_roller | band | etc.)",
            "difficulty (beginner | intermediate | advanced)",
        ],
        "grouping_hint": "Group by body area.",
    },
    "Life Hacks etc": {
        "fields": [
            "hack_title", "category (cleaning | organisation | cooking | tech | health | finance | productivity | diy | other)",
            "description", "steps (numbered list)",
            "items_needed (list, if any)",
        ],
        "grouping_hint": "Group by category.",
    },
    "_uncollected": {
        "fields": [
            "best_guess_collection (Travel | Recipes | Stretching | Life Hacks | Other)",
            "Then include ALL fields from the guessed collection's schema above",
            "confidence (high | medium | low)",
            "reasoning (why you assigned this collection)",
        ],
        "grouping_hint": "First classify, then fill the appropriate schema.",
    },
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_post_collection(post: dict) -> str:
    """Get the primary collection for a post (first one, or _uncollected)."""
    colls = post.get("collections", [])
    return colls[0] if colls else "_uncollected"


def build_batches(posts: list[dict], progress: dict) -> list[dict]:
    """
    Group posts by collection, then chunk into batches of BATCH_SIZE.
    Only includes posts that are transcribed but not yet analysed.
    """
    # Group by collection
    by_collection: dict[str, list[dict]] = {}
    for post in posts:
        sc = post["shortcode"]
        p = progress["posts"].get(sc, {})
        if not p.get("transcribed"):
            continue
        if p.get("analysed"):
            continue
        post_dir = DOWNLOADS_DIR / sc
        if not post_dir.exists():
            continue

        coll = get_post_collection(post)
        by_collection.setdefault(coll, []).append(post)

    # Build batches
    batches = []
    batch_num = 1

    for coll_name in ["Travel", "Recipes", "Stretching", "Life Hacks etc", "_uncollected"]:
        coll_posts = by_collection.get(coll_name, [])
        if not coll_posts:
            continue

        for i in range(0, len(coll_posts), BATCH_SIZE):
            chunk = coll_posts[i:i + BATCH_SIZE]
            batch = {
                "batch_number": batch_num,
                "collection": coll_name,
                "count": len(chunk),
                "posts": [
                    {
                        "shortcode": p["shortcode"],
                        "username": p["username"],
                        "url": p["url"],
                        "media_type": p["media_type"],
                        "dir": str(DOWNLOADS_DIR / p["shortcode"]),
                    }
                    for p in chunk
                ],
            }
            batches.append(batch)
            batch_num += 1

    return batches


def generate_prompt(batch: dict) -> str:
    """Generate a Claude Code prompt for analysing a batch."""
    coll = batch["collection"]
    schema = SCHEMAS.get(coll, SCHEMAS["_uncollected"])
    batch_num = batch["batch_number"]

    lines = [
        f"# Batch {batch_num:03d} Analysis — {coll} ({batch['count']} posts)",
        "",
        "For each post below, read the available files (caption.txt, transcript.txt, frames/*.jpg, meta.json)",
        "and write an `analysis.json` file in the post's directory.",
        "",
        "## Output Schema",
        "",
        "Each `analysis.json` should contain:",
        "```json",
        "{",
    ]

    for field in schema["fields"]:
        lines.append(f'  "{field.split(" (")[0]}": "...",')

    lines.extend([
        '  "source_username": "@username",',
        '  "source_url": "https://www.instagram.com/...",',
        '  "confidence": "high | medium | low",',
        '  "notes": "any relevant observations"',
        "}",
        "```",
        "",
        f"**Grouping hint**: {schema['grouping_hint']}",
        "",
        "## Posts to Analyse",
        "",
    ])

    for i, post in enumerate(batch["posts"], 1):
        lines.extend([
            f"### Post {i}: {post['shortcode']} (@{post['username']})",
            f"- **URL**: {post['url']}",
            f"- **Type**: {post['media_type']}",
            f"- **Directory**: `{post['dir']}`",
            f"- **Files to read**:",
            f"  - `{post['dir']}/caption.txt`",
            f"  - `{post['dir']}/transcript.txt`",
            f"  - `{post['dir']}/meta.json`",
            f"  - `{post['dir']}/frames/` (all .jpg files)",
            "",
        ])

    lines.extend([
        "## Instructions",
        "",
        "1. For each post, read ALL available files (caption, transcript, frames, meta)",
        "2. Analyse the content and fill in the schema fields",
        "3. Write the result to `{post_dir}/analysis.json`",
        "4. If a field cannot be determined, use `null`",
        "5. Set confidence to 'high' if caption + frames clearly show the content,",
        "   'medium' if you're reasonably sure, 'low' if guessing",
        "6. Process ALL posts in this batch before finishing",
    ])

    return "\n".join(lines)


def run_batch(batch_num: int, prompt_path: Path):
    """Run Claude Code on a single batch prompt."""
    print(f"\n--- Running batch {batch_num:03d} ---")
    cmd = [
        "claude", "-p", "--output-format", "text",
        f"Read {prompt_path} and process all posts listed in it. "
        f"For each post, read its files and write an analysis.json.",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
            cwd=str(INSTAGRAM_DIR),
        )
        if result.returncode == 0:
            print(f"  Batch {batch_num:03d} completed successfully")
        else:
            print(f"  Batch {batch_num:03d} failed: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        print(f"  Batch {batch_num:03d} timed out (10 min limit)")
    except FileNotFoundError:
        print("  ERROR: 'claude' command not found. Run batches manually.")


def main():
    parser = argparse.ArgumentParser(description="Generate analysis batches")
    parser.add_argument("--run", action="store_true",
                        help="Run Claude Code on generated batches")
    parser.add_argument("--batch", type=int, default=0,
                        help="Run only this specific batch number")
    args = parser.parse_args()

    master_index = load_json(MASTER_INDEX_PATH)
    progress = load_json(PROGRESS_PATH)

    batches = build_batches(master_index["posts"], progress)

    if not batches:
        print("No posts ready for analysis (need transcription first).")
        return

    print(f"Generated {len(batches)} batches:\n")

    for batch in batches:
        n = batch["batch_number"]
        manifest_path = DATA_DIR / f"batch_{n:03d}_manifest.json"
        prompt_path = DATA_DIR / f"batch_{n:03d}_prompt.md"

        save_json(manifest_path, batch)

        prompt = generate_prompt(batch)
        prompt_path.write_text(prompt, encoding="utf-8")

        print(f"  Batch {n:03d}: {batch['collection']} — {batch['count']} posts")

    print(f"\nManifests and prompts written to {DATA_DIR}/")

    if args.run:
        target_batches = batches
        if args.batch > 0:
            target_batches = [b for b in batches if b["batch_number"] == args.batch]
            if not target_batches:
                print(f"Batch {args.batch} not found.")
                return

        for batch in target_batches:
            n = batch["batch_number"]
            prompt_path = DATA_DIR / f"batch_{n:03d}_prompt.md"
            run_batch(n, prompt_path)

            # After each batch, mark posts as analysed if analysis.json exists
            for post in batch["posts"]:
                sc = post["shortcode"]
                analysis_path = Path(post["dir"]) / "analysis.json"
                if analysis_path.exists():
                    progress["posts"].setdefault(sc, {})["analysed"] = True

            save_json(PROGRESS_PATH, progress)
    else:
        print("\nTo run analysis:")
        print("  python scripts/05_analyse_batch.py --run           # All batches")
        print("  python scripts/05_analyse_batch.py --run --batch 1 # Specific batch")
        print("\nOr manually run Claude Code on each prompt file.")


if __name__ == "__main__":
    main()

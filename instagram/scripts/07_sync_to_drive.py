"""
Step 7: Sync Instagram saved posts data to Google Drive.

Copies downloads/, master_index.json, and output/*.md guides to
Google Drive for remote/Claude.ai access.

Resume-safe: skips files that already exist with the same size.
"""

import json
import os
import shutil
import time
from pathlib import Path

# Paths
SRC_ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS_SRC = SRC_ROOT / "downloads"
DATA_SRC = SRC_ROOT / "data" / "master_index.json"
OUTPUT_SRC = SRC_ROOT / "output"

DRIVE_ROOT = Path(r"G:\My Drive\Instagram Saved")


def should_copy(src: Path, dst: Path) -> bool:
    """Skip if destination exists and is the same size."""
    if not dst.exists():
        return True
    return src.stat().st_size != dst.stat().st_size


def sync_file(src: Path, dst: Path) -> bool:
    """Copy a single file if needed. Returns True if copied."""
    if not should_copy(src, dst):
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def sync_downloads():
    """Copy all download directories to Drive."""
    src_dir = DOWNLOADS_SRC
    dst_dir = DRIVE_ROOT / "downloads"

    posts = sorted(d for d in src_dir.iterdir() if d.is_dir())
    total = len(posts)
    copied_files = 0
    skipped_files = 0

    print(f"Syncing {total} post directories to {dst_dir}")
    start = time.time()

    for i, post_dir in enumerate(posts, 1):
        shortcode = post_dir.name
        dst_post = dst_dir / shortcode

        for src_file in post_dir.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(post_dir)
            dst_file = dst_post / rel
            if sync_file(src_file, dst_file):
                copied_files += 1
            else:
                skipped_files += 1

        if i % 50 == 0 or i == total:
            elapsed = time.time() - start
            print(f"  [{i}/{total}] {shortcode} -{copied_files} copied, {skipped_files} skipped ({elapsed:.0f}s)")

    return copied_files, skipped_files


def sync_metadata():
    """Copy master_index.json and output guides."""
    copied = 0

    # master_index.json
    dst = DRIVE_ROOT / "master_index.json"
    if sync_file(DATA_SRC, dst):
        copied += 1
        print(f"  Copied master_index.json")
    else:
        print(f"  Skipped master_index.json (unchanged)")

    # output/*.md
    if OUTPUT_SRC.exists():
        for md_file in sorted(OUTPUT_SRC.glob("*.md")):
            dst = DRIVE_ROOT / "output" / md_file.name
            if sync_file(md_file, dst):
                copied += 1
                print(f"  Copied output/{md_file.name}")
            else:
                print(f"  Skipped output/{md_file.name} (unchanged)")

    return copied


def main():
    print("=== Instagram Saved -> Google Drive Sync ===")
    print(f"Source: {SRC_ROOT}")
    print(f"Destination: {DRIVE_ROOT}")
    print()

    if not DOWNLOADS_SRC.exists():
        print("ERROR: downloads/ directory not found")
        return

    if not DRIVE_ROOT.parent.exists():
        print("ERROR: Google Drive not accessible at G:\\My Drive")
        return

    DRIVE_ROOT.mkdir(parents=True, exist_ok=True)

    # Sync metadata first (fast)
    print("--- Metadata ---")
    meta_copied = sync_metadata()
    print()

    # Sync downloads (bulk)
    print("--- Downloads ---")
    dl_copied, dl_skipped = sync_downloads()
    print()

    print(f"=== Done ===")
    print(f"  Metadata files copied: {meta_copied}")
    print(f"  Media files copied: {dl_copied}")
    print(f"  Media files skipped: {dl_skipped}")


if __name__ == "__main__":
    main()

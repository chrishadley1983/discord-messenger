"""
03_extract_media.py — Extract frames + audio from downloaded videos.

For each downloaded post:
  - Videos: extract keyframes (1 per 5 seconds) + audio track
  - Photos: just confirm file exists (no extraction needed)

Updates data/progress.json with frames_extracted flag.

Requires: ffmpeg + ffprobe on PATH
"""

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
FAILURES_PATH = DATA_DIR / "extraction_failures.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def check_ffmpeg() -> bool:
    """Verify ffmpeg and ffprobe are available."""
    for cmd in ("ffmpeg", "ffprobe"):
        try:
            subprocess.run(
                [cmd, "-version"],
                capture_output=True, check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            print(f"ERROR: {cmd} not found. Install with: winget install Gyan.FFmpeg")
            return False
    return True


def find_video_files(post_dir: Path) -> list[Path]:
    """Find video files in a post directory."""
    video_exts = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
    return [f for f in post_dir.iterdir() if f.suffix.lower() in video_exts]


def find_image_files(post_dir: Path) -> list[Path]:
    """Find image files in a post directory."""
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    return [f for f in post_dir.iterdir() if f.suffix.lower() in image_exts]


def has_audio_track(video_path: Path) -> bool:
    """Check if a video file has an audio track."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                str(video_path),
            ],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return "audio" in result.stdout
    except Exception:
        return False


def extract_frames(video_path: Path, frames_dir: Path) -> int:
    """Extract frames at 1 per 5 seconds, scaled to 640px wide. Returns frame count."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = str(frames_dir / "frame_%03d.jpg")

    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", "fps=1/5,scale=640:-1",
            "-q:v", "3",
            output_pattern,
        ],
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    if result.returncode != 0:
        print(f"    ffmpeg frames error: {result.stderr[-200:]}")
        return 0

    return len(list(frames_dir.glob("frame_*.jpg")))


def extract_audio(video_path: Path, audio_path: Path) -> bool:
    """Extract audio as mono 16kHz WAV for Whisper. Returns True on success."""
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            str(audio_path),
        ],
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    if result.returncode != 0:
        print(f"    ffmpeg audio error: {result.stderr[-200:]}")
        return False

    # Check file isn't empty/tiny
    if audio_path.exists() and audio_path.stat().st_size < 1000:
        audio_path.unlink()
        return False

    return True


def process_post(post_dir: Path) -> tuple[bool, str]:
    """
    Process a single post directory.
    Returns (success, detail_string).
    """
    videos = find_video_files(post_dir)
    images = find_image_files(post_dir)

    if not videos and not images:
        return False, "no media files found"

    # Process videos
    for video in videos:
        frames_dir = post_dir / "frames"

        # Extract frames (skip if already done)
        if not frames_dir.exists() or not list(frames_dir.glob("frame_*.jpg")):
            n_frames = extract_frames(video, frames_dir)
            if n_frames == 0:
                # Very short video — extract at least 1 frame
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-i", str(video),
                        "-vframes", "1", "-q:v", "3",
                        str(frames_dir / "frame_001.jpg"),
                    ],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                n_frames = len(list(frames_dir.glob("frame_*.jpg")))

        # Extract audio (skip if already done)
        audio_path = post_dir / "audio.wav"
        if not audio_path.exists():
            if has_audio_track(video):
                extract_audio(video, audio_path)

        # Only process first video (carousel videos are rare for saved posts)
        break

    # For image-only posts, just confirm images exist
    if not videos and images:
        # Copy first image to frames/ for consistent processing later
        frames_dir = post_dir / "frames"
        frames_dir.mkdir(exist_ok=True)
        if not list(frames_dir.glob("frame_*.jpg")):
            # Just symlink/copy the original image as frame_001.jpg
            import shutil
            shutil.copy2(str(images[0]), str(frames_dir / "frame_001.jpg"))

    detail = f"{len(videos)} video(s), {len(images)} image(s)"
    return True, detail


def main():
    if not check_ffmpeg():
        sys.exit(1)

    master_index = load_json(MASTER_INDEX_PATH)
    progress = load_json(PROGRESS_PATH)
    posts = master_index["posts"]

    # Find posts that are downloaded but not yet extracted
    to_process = []
    for post in posts:
        sc = post["shortcode"]
        p = progress["posts"].get(sc, {})
        if p.get("downloaded") and not p.get("frames_extracted"):
            post_dir = DOWNLOADS_DIR / sc
            if post_dir.exists():
                to_process.append((sc, post_dir))

    print(f"{len(to_process)} posts to process\n")

    if not to_process:
        print("Nothing to extract!")
        return

    failures: dict[str, str] = {}
    success_count = 0
    fail_count = 0

    for i, (sc, post_dir) in enumerate(to_process, 1):
        print(f"[{i}/{len(to_process)}] {sc}...", end=" ", flush=True)
        ok, detail = process_post(post_dir)

        if ok:
            progress["posts"].setdefault(sc, {})["frames_extracted"] = True
            save_json(PROGRESS_PATH, progress)
            success_count += 1
            print(f"OK ({detail})")
        else:
            failures[sc] = detail
            fail_count += 1
            print(f"FAIL ({detail})")

    if failures:
        save_json(FAILURES_PATH, {"failures": failures, "total": len(failures)})
        print(f"\nFailures logged to {FAILURES_PATH}")

    print(f"\n=== Extraction Complete ===")
    print(f"  Processed: {success_count}")
    print(f"  Failed: {fail_count}")


if __name__ == "__main__":
    main()

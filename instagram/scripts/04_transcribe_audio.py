"""
04_transcribe_audio.py — Transcribe audio from downloaded videos using faster-whisper.

For each post with audio.wav, transcribe to transcript.txt.
Posts without audio get a "(no audio)" transcript.

Requires: pip install faster-whisper
"""

import json
import sys
from pathlib import Path

# Paths
INSTAGRAM_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = INSTAGRAM_DIR / "data"
DOWNLOADS_DIR = INSTAGRAM_DIR / "downloads"

MASTER_INDEX_PATH = DATA_DIR / "master_index.json"
PROGRESS_PATH = DATA_DIR / "progress.json"
FAILURES_PATH = DATA_DIR / "transcription_failures.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_whisper_model():
    """Load faster-whisper model once."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("ERROR: faster-whisper not installed.")
        print("  pip install faster-whisper")
        sys.exit(1)

    print("Loading Whisper model (base, CPU, int8)...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    print("Model loaded.\n")
    return model


def transcribe_file(model, audio_path: Path) -> tuple[str, str]:
    """
    Transcribe an audio file.
    Returns (language, transcript_text).
    """
    segments, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        language=None,  # Auto-detect
        vad_filter=True,  # Skip silence
    )

    text_parts = []
    for segment in segments:
        text_parts.append(segment.text.strip())

    language = info.language
    transcript = " ".join(text_parts).strip()
    return language, transcript


def main():
    master_index = load_json(MASTER_INDEX_PATH)
    progress = load_json(PROGRESS_PATH)
    posts = master_index["posts"]

    # Find posts that have frames extracted but not yet transcribed
    to_process = []
    for post in posts:
        sc = post["shortcode"]
        p = progress["posts"].get(sc, {})
        if p.get("frames_extracted") and not p.get("transcribed"):
            post_dir = DOWNLOADS_DIR / sc
            if post_dir.exists():
                to_process.append((sc, post_dir))

    print(f"{len(to_process)} posts to transcribe\n")

    if not to_process:
        print("Nothing to transcribe!")
        return

    # Load model once
    model = load_whisper_model()

    failures: dict[str, str] = {}
    transcribed_count = 0
    no_audio_count = 0
    fail_count = 0

    for i, (sc, post_dir) in enumerate(to_process, 1):
        transcript_path = post_dir / "transcript.txt"
        audio_path = post_dir / "audio.wav"

        # Skip if transcript already exists (resume-safe)
        if transcript_path.exists():
            progress["posts"].setdefault(sc, {})["transcribed"] = True
            save_json(PROGRESS_PATH, progress)
            print(f"[{i}/{len(to_process)}] {sc} — transcript exists, skipping")
            continue

        if not audio_path.exists():
            # No audio → write placeholder
            transcript_path.write_text("(no audio)", encoding="utf-8")
            progress["posts"].setdefault(sc, {})["transcribed"] = True
            save_json(PROGRESS_PATH, progress)
            no_audio_count += 1
            print(f"[{i}/{len(to_process)}] {sc} — no audio")
            continue

        print(f"[{i}/{len(to_process)}] {sc}...", end=" ", flush=True)

        try:
            language, transcript = transcribe_file(model, audio_path)

            if not transcript:
                transcript = "(no speech detected)"

            # Write transcript with language header
            content = f"[Language: {language}]\n{transcript}"
            transcript_path.write_text(content, encoding="utf-8")

            progress["posts"].setdefault(sc, {})["transcribed"] = True
            save_json(PROGRESS_PATH, progress)
            transcribed_count += 1

            # Show preview
            preview = transcript[:80] + "..." if len(transcript) > 80 else transcript
            print(f"OK ({language}, {len(transcript)} chars) — {preview}")

        except Exception as e:
            failures[sc] = f"{type(e).__name__}: {e}"
            fail_count += 1
            print(f"FAIL ({e})")

    if failures:
        save_json(FAILURES_PATH, {"failures": failures, "total": len(failures)})
        print(f"\nFailures logged to {FAILURES_PATH}")

    print(f"\n=== Transcription Complete ===")
    print(f"  Transcribed: {transcribed_count}")
    print(f"  No audio: {no_audio_count}")
    print(f"  Failed: {fail_count}")


if __name__ == "__main__":
    main()

"""Generate voice samples for all 4 British male Kokoro voices.

Run: python scripts/voice_samples.py
Output: scripts/voice_samples/ directory with WAV files.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hadley_api.voice_engine import synthesise_sync

VOICES = ["bm_daniel", "bm_fable", "bm_george", "bm_lewis"]

PHRASES = [
    ("greeting", "Good morning Chris! How's it going today?"),
    ("factual", "You've got a dentist appointment at three o'clock, and Abby's picking the kids up from school."),
    ("playful", "Right, pasta night it is then. I'll try not to judge your cheese-to-sauce ratio this time."),
    ("helpful", "I've checked your calendar and you're free this afternoon. Want me to block out some time for that project?"),
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "voice_samples")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for voice in VOICES:
        print(f"\n--- {voice} ---")
        for label, text in PHRASES:
            filename = f"{voice}_{label}.wav"
            filepath = os.path.join(OUTPUT_DIR, filename)
            wav = synthesise_sync(text, voice=voice)
            with open(filepath, "wb") as f:
                f.write(wav)
            print(f"  {filename} ({len(wav)} bytes)")

    print(f"\nDone! Samples in: {OUTPUT_DIR}")
    print("Listen to each voice and pick your favourite for Peter.")


if __name__ == "__main__":
    main()

"""Seed Second Brain with Japan guide pages.

Chunks 158 guide HTML files into paragraphs, stores in the Second Brain
for semantic search during WhatsApp conversations.

Usage:
    python -m domains.second_brain.seed.japan_guides_seed
"""

import re
import json
from pathlib import Path
from datetime import datetime

GUIDES_DIR = Path("C:/Users/Chris Hadley/claude-projects/japan-family-guide/site")
SOURCE_TAG = "japan-guide"


def _extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML, removing tags and scripts."""
    # Remove script/style blocks
    html = re.sub(r'<script[^>]*>[\s\S]*?</script>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<style[^>]*>[\s\S]*?</style>', '', html, flags=re.IGNORECASE)
    # Remove HTML tags
    html = re.sub(r'<[^>]+>', ' ', html)
    # Decode entities
    html = html.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    html = html.replace('&mdash;', '—').replace('&ndash;', '–')
    html = html.replace('&yen;', '¥').replace('&pound;', '£')
    html = html.replace('&#127968;', '🏠').replace('&#128205;', '📍')
    html = re.sub(r'&#\d+;', '', html)
    # Collapse whitespace
    html = re.sub(r'\s+', ' ', html).strip()
    return html


def _chunk_text(text: str, guide_name: str, max_chunk: int = 500) -> list[dict]:
    """Split text into semantic chunks of ~500 chars."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) > max_chunk and current:
            chunks.append({
                "content": current.strip(),
                "source": f"japan-guide:{guide_name}",
                "source_type": SOURCE_TAG,
                "guide": guide_name,
                "created_at": datetime.now().isoformat(),
            })
            current = sentence
        else:
            current += " " + sentence

    if current.strip():
        chunks.append({
            "content": current.strip(),
            "source": f"japan-guide:{guide_name}",
            "source_type": SOURCE_TAG,
            "guide": guide_name,
            "created_at": datetime.now().isoformat(),
        })

    return chunks


def extract_all_guides() -> list[dict]:
    """Extract and chunk all guide HTML files."""
    all_chunks = []
    guide_files = sorted(GUIDES_DIR.glob("*-guide.html"))

    for guide_file in guide_files:
        name = guide_file.stem  # e.g. "arashiyama-guide"
        try:
            html = guide_file.read_text(encoding="utf-8")
            text = _extract_text_from_html(html)

            # Skip very short files (probably empty templates)
            if len(text) < 200:
                continue

            # Extract title from <title> tag
            title_match = re.search(r'<title>(.*?)</title>', html)
            title = title_match.group(1) if title_match else name

            # Prepend title to text
            text = f"{title}. {text}"

            chunks = _chunk_text(text, name)
            all_chunks.extend(chunks)

        except Exception as e:
            print(f"  Error processing {name}: {e}")

    return all_chunks


def save_chunks_for_import(chunks: list[dict], output_path: str = "data/japan_guide_chunks.jsonl"):
    """Save chunks as JSONL for batch import into Second Brain."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"Saved {len(chunks)} chunks to {output}")


if __name__ == "__main__":
    print("Extracting Japan guide pages...")
    chunks = extract_all_guides()
    print(f"Extracted {len(chunks)} chunks from {len(set(c['guide'] for c in chunks))} guides")

    # Save for import
    save_chunks_for_import(chunks)

    # Show sample
    print("\nSample chunks:")
    for c in chunks[:3]:
        print(f"  [{c['guide']}] {c['content'][:100]}...")

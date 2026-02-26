# Instagram Favourites → Travel Inspiration Guide

## Spec for Claude Code Processing Pipeline

**Purpose**: Extract travel inspiration from ~2 years of Instagram saved/favourite posts and produce a consolidated travel ideas document grouped by destination.

**Approach**: One-off, repeatable ad-hoc process. No API costs — all processing done locally via Claude Code.

---

## Phase 1: Data Export (Manual — You Do This)

### Step 1: Request Instagram Data Export

1. Open Instagram → tap your **profile icon** → **hamburger menu** (☰) top right
2. **Settings & Privacy** → **Accounts Centre**
3. **Your Information and Permissions** → **Download Your Information** (may show as "Export Your Information")
4. Tap **Create export** → select your Instagram account
5. Choose **Export to device** → **Customize information** (make sure Saved posts is included)
6. Choose **JSON** format (not HTML) and **All time** date range
7. Submit the request — Instagram will email/notify you when ready (can take up to 48 hours)
8. Download and extract the ZIP file

### Step 2: Locate Saved Posts Data

In the extracted folder, look for:

```
your_instagram_activity/
  saved/
    saved_posts.json
    saved_collections.json   (if you use collections/folders)
```

The `saved_posts.json` contains entries like:

```json
{
  "title": "",
  "media_list_data": [],
  "string_list_data": [
    {
      "href": "https://www.instagram.com/p/SHORTCODE/",
      "value": "caption preview or empty",
      "timestamp": 1234567890
    }
  ]
}
```

You need the shortcodes from the `href` URLs.

### Step 3: Download Post Content with Instaloader

```bash
# Install
pip install instaloader

# Optional: Login for access to posts from private accounts
# instaloader --login YOUR_USERNAME

# Create a download script - save as download_saved.py
```

```python
#!/usr/bin/env python3
"""
Download Instagram saved posts using instaloader.
Extracts shortcodes from Instagram data export and downloads each post.
"""

import json
import os
import time
import re
import instaloader

# === CONFIGURATION ===
EXPORT_FILE = "saved_posts.json"          # Path to your Instagram export file
OUTPUT_DIR = "instagram_saved_posts"       # Where to save downloaded posts
DELAY_SECONDS = 3                          # Delay between downloads (avoid rate limiting)
# LOGIN_USER = "your_username"             # Uncomment to login (needed for private accounts)

def extract_shortcodes(export_file):
    """Extract post shortcodes from Instagram data export JSON."""
    with open(export_file, 'r') as f:
        data = json.load(f)

    shortcodes = []

    # Handle both formats: list of saved items or dict with saved_media
    items = data if isinstance(data, list) else data.get("saved_media", data.get("saved_posts", []))

    for item in items:
        # Try string_list_data first (newer format)
        string_data = item.get("string_list_data", [])
        for entry in string_data:
            href = entry.get("href", "")
            match = re.search(r'/p/([A-Za-z0-9_-]+)', href)
            if match:
                shortcodes.append(match.group(1))

        # Also check media_list_data
        media_data = item.get("media_list_data", [])
        for entry in media_data:
            uri = entry.get("uri", "")
            match = re.search(r'/p/([A-Za-z0-9_-]+)', uri)
            if match:
                shortcodes.append(match.group(1))

    return list(dict.fromkeys(shortcodes))  # Deduplicate preserving order


def download_posts(shortcodes, output_dir, delay=3):
    """Download each post using instaloader."""
    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=True,
        download_comments=False,
        save_metadata=True,
        compress_json=False,
        dirname_pattern=os.path.join(output_dir, "{shortcode}"),
        filename_pattern="{shortcode}"
    )

    # Uncomment to login (needed for private accounts)
    # L.login(LOGIN_USER, "password")
    # Or use session: L.load_session_from_file(LOGIN_USER)

    total = len(shortcodes)
    failed = []

    for i, shortcode in enumerate(shortcodes, 1):
        target_dir = os.path.join(output_dir, shortcode)

        # Skip if already downloaded
        if os.path.exists(target_dir) and any(
            f.endswith(('.mp4', '.jpg', '.txt'))
            for f in os.listdir(target_dir)
        ):
            print(f"[{i}/{total}] Skipping {shortcode} (already downloaded)")
            continue

        print(f"[{i}/{total}] Downloading {shortcode}...")
        try:
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            L.download_post(post, target=shortcode)

            # Also save caption separately for easy access
            caption_file = os.path.join(target_dir, "caption.txt")
            if not os.path.exists(caption_file):
                with open(caption_file, 'w') as f:
                    f.write(post.caption or "(no caption)")

            # Save basic metadata
            meta_file = os.path.join(target_dir, "meta.json")
            if not os.path.exists(meta_file):
                meta = {
                    "shortcode": shortcode,
                    "url": f"https://www.instagram.com/p/{shortcode}/",
                    "owner": post.owner_username,
                    "caption": post.caption or "",
                    "hashtags": list(post.caption_hashtags),
                    "location": post.location.name if post.location else None,
                    "is_video": post.is_video,
                    "timestamp": post.date_utc.isoformat(),
                    "likes": post.likes,
                }
                with open(meta_file, 'w') as f:
                    json.dump(meta, f, indent=2)

        except Exception as e:
            print(f"  ✗ Failed: {e}")
            failed.append({"shortcode": shortcode, "error": str(e)})

        time.sleep(delay)

    # Save failures for retry
    if failed:
        with open(os.path.join(output_dir, "_failed.json"), 'w') as f:
            json.dump(failed, f, indent=2)
        print(f"\n{len(failed)} posts failed. See _failed.json")

    print(f"\nDone! {total - len(failed)}/{total} posts downloaded to {output_dir}/")


if __name__ == "__main__":
    print("Extracting shortcodes from export...")
    shortcodes = extract_shortcodes(EXPORT_FILE)
    print(f"Found {len(shortcodes)} saved posts")

    print(f"\nDownloading to {OUTPUT_DIR}/...")
    download_posts(shortcodes, OUTPUT_DIR, delay=DELAY_SECONDS)
```

**Run it:**

```bash
# Place saved_posts.json in the same directory, then:
python download_saved.py
```

**Expected output structure:**

```
instagram_saved_posts/
  ABC123/
    ABC123.mp4          (or .jpg for photos)
    ABC123.txt          (instaloader caption)
    caption.txt         (clean caption)
    meta.json           (structured metadata)
  DEF456/
    DEF456.jpg
    caption.txt
    meta.json
  _failed.json          (any posts that couldn't be downloaded)
```

**Time estimate**: ~200-300 posts at 3s delay = ~10-15 minutes.

---

## Phase 2: Processing with Claude Code

Once you have the downloaded folder, point Claude Code at it. Below is the prompt/spec.

### Prerequisites (Claude Code will install these)

- `ffmpeg` — for extracting video frames and audio
- `whisper` (openai-whisper or faster-whisper) — for audio transcription
- Python packages: `openai-whisper`, `Pillow`

### Claude Code Prompt

Use this as a task prompt for Claude Code:

---

```
## Task: Process Instagram Saved Posts into Travel Inspiration Guide

### Context
I have a folder of downloaded Instagram saved posts at `./instagram_saved_posts/`. 
Each subfolder contains a post with some combination of:
- Video file (.mp4) or image file (.jpg/.png)
- caption.txt (the post caption)
- meta.json (metadata including location, hashtags, owner username)

These are mostly travel inspiration posts saved over ~2 years.

### What I need you to do

#### Step 1: Setup
- Install required tools: `pip install openai-whisper Pillow --break-system-packages`
- Verify `ffmpeg` is available

#### Step 2: Process each post subfolder
For each post directory:

**A) Read the caption** from caption.txt

**B) Read metadata** from meta.json (location, hashtags, owner)

**C) If the post is a video (.mp4):**
  1. Extract key frames using ffmpeg:
     ```bash
     ffmpeg -i video.mp4 -vf "fps=1/5,scale=640:-1" -q:v 3 frames/frame_%03d.jpg
     ```
     (1 frame every 5 seconds, resized to 640px wide)
  
  2. Extract audio and transcribe:
     ```bash
     ffmpeg -i video.mp4 -vn -acodec pcm_s16le -ar 16000 audio.wav
     ```
     Then transcribe with Whisper (use "base" model for speed):
     ```python
     import whisper
     model = whisper.load_model("base")
     result = model.transcribe("audio.wav")
     transcription = result["text"]
     ```
  
  3. Analyse the key frames visually — look for:
     - Location names, restaurant/hotel names in text overlays
     - Recognisable landmarks or destinations
     - Type of activity (food, beach, architecture, nature, nightlife, etc.)
     - Any on-screen text/titles

**D) If the post is a photo (.jpg/.png):**
  1. Analyse the image visually — same as frame analysis above
  2. Look for text overlays, location tags, recognisable places

**E) Compile a structured record** for each post:
```json
{
  "shortcode": "ABC123",
  "source_url": "https://www.instagram.com/p/ABC123/",
  "owner": "@username",
  "country": "Japan",
  "city_or_region": "Tokyo",
  "specific_location": "Shibuya Crossing",
  "category": "sightseeing",
  "caption_summary": "Brief summary of caption content",
  "transcription": "What was said in the video (if applicable)",
  "visual_description": "What the images/frames show",
  "key_tips": ["Specific actionable tips extracted"],
  "mentions": ["@accounts", "tagged locations", "restaurant names"],
  "hashtags": ["#tokyo", "#japantravel"],
  "confidence": "high/medium/low"
}
```

Categories to use: `sightseeing`, `food_and_drink`, `accommodation`, `beach`, 
`nature_and_hiking`, `nightlife`, `culture`, `shopping`, `transport_tips`, `general_tips`, `other`

#### Step 3: Compile the travel inspiration document

Group all processed posts into a structured markdown document:

**Structure:**
```
# Travel Inspiration Guide
(Generated from Instagram saved posts)

## Japan
### Tokyo
#### Sightseeing
- **Shibuya Crossing** (@username) — description and tips
  [Source](https://instagram.com/p/...)

#### Food & Drink  
- **Ramen street in Shinjuku** (@username) — description
  [Source](https://instagram.com/p/...)

### Kyoto
...

## Portugal
### Lisbon
...

## General Tips
- Packing tips, travel hacks, etc.
```

**Rules:**
- Group by country → city/region → category
- Include the source URL for each entry so I can go back to the original post
- Include the @username of the original poster
- Extract specific names (restaurants, hotels, attractions) wherever possible
- If location can't be determined, put in an "Unlocated" section
- If confidence is low (can't determine what the post is about), put in a "To Review" section
- At the end, include a summary: total posts processed, breakdown by country, 
  any posts that couldn't be processed

### Performance notes
- Process posts in batches of 10-20 to manage memory
- Load the Whisper model once and reuse across all videos  
- Skip audio transcription if the video has no audio track
- Use the "base" Whisper model (good balance of speed/accuracy for short clips)
- If a post fails to process, log it and continue — don't stop the pipeline
```

---

## Phase 3: Output

Claude Code will produce a `travel_inspiration.md` file. You can then:

1. **Use as-is** — it's a comprehensive markdown reference
2. **Bring back to Claude.ai** — upload the markdown and ask for a polished Word doc or different grouping
3. **Filter further** — ask Claude to extract just Japan-related entries for your April 2026 trip planning

---

## Estimated Effort

| Step | Time | Who |
|------|------|-----|
| Instagram data export request | 2 mins (then wait up to 48hrs) | You |
| Run download script | 10-15 mins (automated) | You (start it and leave it) |
| Claude Code processing | 30-60 mins depending on post count | Claude Code (automated) |
| **Total active effort** | **~15 mins** | |

---

## Troubleshooting

**Instaloader rate limited**: Increase `DELAY_SECONDS` to 5-10. Or login with your session for better limits.

**Private account posts fail**: You need to login to instaloader with your Instagram credentials. Use `instaloader --login YOUR_USERNAME` and it'll prompt for password and save the session.

**Whisper too slow**: Switch from `openai-whisper` to `faster-whisper` (`pip install faster-whisper`). Same API, ~4x faster on CPU. Or use the "tiny" model instead of "base" — less accurate but much faster for short clips.

**Too many posts to process in one CC session**: Split the folder into batches (e.g., by date or alphabetically) and process each batch separately, then combine the outputs.

**Instagram export doesn't include saved posts**: The export format changes periodically. Look in `your_instagram_activity/saved/` or `saved/` at the top level. The file might be called `saved_media.json`, `saved_posts.json`, or similar.

**Some posts are carousel (multiple images)**: Instaloader downloads all images in a carousel. The CC prompt handles this — it'll analyse all images in each post folder.

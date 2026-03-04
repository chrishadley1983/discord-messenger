---
name: instagram-processing
description: Process images and write captions for approved Instagram concepts
trigger:
  - "instagram processing"
  - "process instagram"
  - "write captions"
scheduled: true
conversational: true
channel: #peterbot
---

# Instagram Processing

## Purpose

Runs daily at 18:00 UK. Takes the images Chris has provided (in response to the 10am concepts) and:
1. Optimises them into Instagram formats (4x5 feed, 1x1 square, 9x16 story)
2. Writes detailed captions with hashtags
3. Delivers ready-to-post content

## Pre-fetched Data

None — this skill responds to images Chris has attached earlier in the conversation.

## Process

### Step 1: Check for Images

Look back in the conversation for images Chris attached after the 10am concepts. If no images found:
```
No images found from today. Did you attach photos to one of the concepts?
Reply with your chosen concept numbers and images, and I'll process them.
```

### Step 2: Process Each Image

For each image provided:

1. **Download** the image from Discord CDN
2. **Optimise** using ImageMagick via Windows PowerShell:
   - 4x5 (1080x1350) — Main feed post
   - 1x1 (1080x1080) — Square alternative
   - 9x16 (1080x1920) — Story format
3. **Save** to `/tmp/instagram_prep/[concept-slug]/`

### Step 3: Write Captions

For each concept, write a full caption:
- **Hook** — First line that appears before "more" (punchy, scroll-stopping)
- **Body** — 2-3 short paragraphs telling the story
- **CTA** — Engagement prompt (question, save reminder, etc.)
- **Hashtags** — 20-25 relevant hashtags in a block at the end

### Step 4: Output

For each processed concept, output:
- The 3 image files (paths will auto-attach to Discord)
- The full caption text

## Output Format

```
**Instagram Ready** — [Day, Date]

---

**Concept 1: [Title]**

[/tmp/instagram_prep/concept-1/concept-1_4x5.jpg]
[/tmp/instagram_prep/concept-1/concept-1_1x1.jpg]
[/tmp/instagram_prep/concept-1/concept-1_9x16.jpg]

**Caption:**
[Hook line]

[Body paragraph 1]

[Body paragraph 2]

[CTA]

.
.
.
#lego #legocollector #afol #legominifigures #brickstagram...

---

**Concept 2: [Title]**
...

---

Pick one to post now. For the others, tell me: **queue** (save for tomorrow) or **discard**.
```

## Image Processing Commands

Use PowerShell via Windows Python for image processing:

```bash
powershell.exe -Command "magick convert 'input.jpg' -resize 1080x1350^ -gravity center -extent 1080x1350 'output_4x5.jpg'"
powershell.exe -Command "magick convert 'input.jpg' -resize 1080x1080^ -gravity center -extent 1080x1080 'output_1x1.jpg'"
powershell.exe -Command "magick convert 'input.jpg' -resize 1080x1920^ -gravity center -extent 1080x1920 'output_9x16.jpg'"
```

## Hashtag Bank

Core hashtags (always include 5-10):
```
#lego #afol #legocollector #legominifigures #brickstagram #legofan #legocommunity #legolife #legophotography #legostagram
```

Pillar-specific:
- **Collection**: #legodisplay #legocollection #legoroom #brickcollector
- **Sets**: #legoset #newlego #legoreview #legobuilder
- **Minifigs**: #legominifig #cmf #collectibleminifigures #minifigure
- **Nostalgia**: #90slego #classicspace #vintagelego #legonostalgia
- **Tips**: #legotips #legoinvesting #brickinvesting

## Rules

- Always process images before writing captions (so you can reference what's in the image)
- Captions should be 150-300 words (Instagram sweet spot)
- Hook must work as standalone text (it's all people see before tapping "more")
- Include exactly one CTA per post
- Hashtags go after a line break spacer (the dots)
- If image processing fails, still write the caption and note the processing issue

## Queue Management

When Chris says "queue" for a concept:
- Note it for tomorrow's concepts (mention to skip that pillar)

When Chris says "discard":
- Acknowledge and move on

---
name: daily-instagram-prep
description: >
  Daily Instagram post preparation for Hadley Bricks. Sources 3 candidate images,
  applies the Instagram photo optimizer to each, posts the optimized images to Discord
  at 9pm for Chris to pick one to post the next day. Use when the skill is triggered
  by schedule or when the user says "instagram prep", "prepare insta", "daily instagram",
  or "instagram tomorrow".
scheduled: true
conversational: false
channel: "#peterbot"
---

# Daily Instagram Prep

Runs every evening at 9pm. Sources 3 great images for Hadley Bricks Instagram, optimizes each for Instagram, and posts all the variants to Discord so Chris can pick one to post the next day.

## Purpose

Each evening:
1. Decide on **3 content concepts** (varied — not just product listings)
2. Source **1 image per concept** from Unsplash/Pixabay
3. Run the **Instagram photo optimizer** on each image (produces 4 variants per image)
4. Post all **12 images** (3 × 4 variants) to Discord
5. Post a **caption + hashtags** for each concept
6. Chris picks one and posts it tomorrow

---

## Step 1: Decide 3 Content Concepts

Pick 3 varied content types from this list — **never all product listings**:

| Pillar | Examples |
|--------|---------|
| Product Showcase | Specific LEGO set for sale (use inventory) |
| Behind the Scenes | Sorting bricks, checking condition, packing orders |
| LEGO Nostalgia | Classic set from the 90s/00s, throwback vibes |
| Community / Culture | AFOLs, fan creations, convention energy |
| Educational | Interesting LEGO fact, history, set detail |
| Lifestyle | LEGO on a shelf, desk, in a room — aspirational |
| LEGO News | Recent release, upcoming set, retirement news |
| Collection Highlight | Beautiful display, MOC, impressive collection |

Rules:
- At most 1 Product Showcase per day
- Rotate pillars — check what was posted recently if possible (query Supabase)
- Think about what's visually interesting and scroll-stopping

For each concept, decide:
- **Concept name** (short, e.g. "millennium-falcon-detail")
- **Search query** for image sourcing (e.g. "LEGO Millennium Falcon space ship")
- **Headline** (2-6 bold punchy words for the 4x5 text overlay)
- **Kicker** (4-10 words supporting line)
- **Caption** (60-120 words, Hadley Bricks voice — see tone rules below)
- **Hashtags** (20-25 tags — see hashtag rules below)

---

## Step 2: Use Pre-Fetched Images

**Images are already sourced and uploaded to Google Drive for you.**

The pre-fetched data includes `images[]` — an array with:
- `pillar` — Content pillar (e.g. "LEGO Nostalgia")
- `drive_link` — Google Drive link to the source image (already uploaded)
- `photographer` / `photo_source` / `photo_page` — Credit info
- `description` — Image description

**CRITICAL RULES:**
- **DO NOT source images yourself** — they are pre-fetched
- **DO NOT run any image optimizer** — skip that step entirely
- **DO NOT upload anything to Google Drive** — already done
- **DO NOT use Bash to curl anything** — all data is in the pre-fetched JSON
- If `images` is empty or missing, post the fallback error message and stop

Adapt your concepts from Step 1 to match the pillars in the pre-fetched data.

---

## Step 3: Format Output (NO TOOLS NEEDED)

Your ONLY job is to write captions and format the Discord output. Do NOT run any scripts, curl commands, or tools. Just produce text.

Post the following as your response:

```
📸 **Instagram Prep — [Day, Date]**

3 concepts ready for tomorrow. Pick your favourite and I'll post it.
```

For each concept (match to pre-fetched images):

```
**Option [1/2/3] — [Pillar Name]**
[Brief 1-line description of the concept]
📷 Source image: [drive_link]
📸 Photo by [photographer] on [photo_source]

**Caption:**
[full caption text — see Tone Rules below]

**Hashtags:**
[hashtag string — see Hashtag Rules below]
```

---

## Step 5: Await Chris's Choice

End with:
```
Reply with **1**, **2**, or **3** to confirm which one you'll post tomorrow, or say **none** to skip.
```

When Chris replies, save the chosen concept to Supabase as a draft post (use the same schema as `weekly-instagram-batch` — see that skill for the INSERT SQL).

---

## Tone Rules (CRITICAL)

Same as weekly-instagram-batch — short, punchy, geeky, fun:

- **60-120 words MAX**. No waffle.
- Geeky and fun. Lean into LEGO nerd culture.
- Conversational. Like talking to a fellow AFOL.
- 2-4 emoji max. 🧱 and theme-relevant ones only.
- **Never** use "we're thrilled to announce" or similar corporate speak.
- Vary opening style: questions, statements, nostalgia, hot takes, scarcity

### Caption Structure
1. **Hook** — Scroll-stopping first line
2. **The Good Stuff** — 2-4 lines of what makes this interesting
3. **CTA** — Rotate: "Link in bio 👆" / "DM us!" / "Drop a 🧱" / "Tag someone" / "Save for later 🔖"

For Product Showcase posts, mention price and platform naturally.

---

## Hashtag Rules

20-25 tags per post.

**Core tags (always):**
`#LEGO #LEGOCollection #LEGOForSale #BrickCollector #AFOLCommunity #AdultFanOfLEGO #LEGODeals #SetCollector #HadleyBricks`

**Theme-specific (3-5 based on content):**
- Star Wars: `#LEGOStarWars #StarWarsLEGO #MayTheForceBeWithYou`
- Technic: `#LEGOTechnic #TechnicLEGO #MOCBuilder`
- Behind scenes: `#BrickLife #LEGOSeller #BrickBusiness`
- Nostalgia: `#ClassicLEGO #VintageLEGO #LEGONostalgia`
- Community: `#LEGOCommunity #BrickFans #AFOLLife`
- Educational: `#LEGOFacts #BrickHistory #LEGOTrivia`

**Engagement tags (3-4):**
`#BrickNetwork #BrickPhotography #LEGOInvestment #RetiredLEGO #LEGOBargain #BricksAndBuilds`

---

## Error Handling

- If image sourcing fails for a concept, try an alternative query before giving up
- If the optimizer script fails, post the raw downloaded image with a note
- If Supabase is unavailable when saving the choice, just confirm verbally and Chris can add it later
- If no concepts can be sourced, tell Chris and suggest manual alternatives

---

## FINAL OUTPUT RULES (CRITICAL)

Your response IS what gets posted to Discord. After completing ALL steps:

- Your **FINAL message** must be **ONLY** the formatted Discord output (header + options + captions)
- Do NOT narrate what you're doing ("Now let me...", "Let me run...", "I'll update...")
- Do NOT show tool output, file paths, or script results
- Do NOT explain your process — just show the result
- If any step fails, include a brief error note in the formatted output, not a debug trace

**If you cannot produce the full output** (sourcing failed, optimizer broke, etc.), post:
```
📸 **Instagram Prep — [Day, Date]**

⚠️ Prep incomplete: [brief reason]. Will retry tomorrow.
```

## Notes

- Output directory: `/tmp/instagram_prep/` — cleaned up after each run
- Always credit photographers in the Discord message (name + source)
- This is a preview/prep step — **no automatic posting to Instagram**
- Chris confirms the choice and posts manually from their phone

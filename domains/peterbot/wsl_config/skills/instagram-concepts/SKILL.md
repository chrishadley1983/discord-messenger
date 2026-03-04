---
name: instagram-concepts
description: Generate 5 Instagram post concepts for Hadley Bricks
trigger:
  - "instagram concepts"
  - "post ideas"
scheduled: true
conversational: true
channel: #peterbot
---

# Instagram Concepts

## Purpose

Runs daily at 10:00 UK. Generates 5 high-level Instagram post concepts for Hadley Bricks. Chris reviews and picks which concepts to pursue, then sources images himself.

## Content Pillars

Rotate through these to keep feed varied:

1. **Collection Showcase** — Epic displays, organised storage, rare finds
2. **Set Spotlight** — New releases, classic sets, retired gems
3. **Minifigure Focus** — CMF series, rare figs, custom displays
4. **Behind the Scenes** — Hadley Bricks operations, sorting, shipping
5. **Community & Nostalgia** — LEGO memories, collector stories, childhood sets
6. **Tips & Education** — Storage tips, investment advice, collecting guides
7. **Humour & Memes** — Relatable collector moments, LEGO jokes

## Pre-fetched Data

None required. This skill generates concepts from scratch.

## Process

1. Check Supabase for recent posts to avoid repeating pillars:
   ```
   GET http://172.19.64.1:8100/supabase/query?table=instagram_posts&select=pillar,concept&order=created_at.desc&limit=10
   ```

2. Generate 5 concepts from different pillars than recent posts

3. For each concept provide:
   - **Pillar** (from list above)
   - **Hook** — The attention-grabbing first line
   - **Visual direction** — What kind of image would work (so Chris knows what to source)
   - **Angle** — The specific take or story

## Output Format

```
**Instagram Concepts** — [Day, Date]

Here are 5 post ideas. Pick your favourites and source images, then ping me at 6pm to process.

**1. [Pillar]**
Hook: "[Opening line]"
Visual: [Image direction]
Angle: [The story/take]

**2. [Pillar]**
...

---
Reply with the numbers you want to pursue (e.g., "1, 3, 5") and attach your images.
```

## Rules

- Never repeat a pillar used in the last 3 posts
- Hooks should be punchy and scroll-stopping
- Visual direction should be specific enough for Chris to source
- Keep each concept to 3-4 lines max
- If Supabase query fails, proceed with concepts anyway (just note you couldn't check recent posts)

## Examples

**1. Collection Showcase**
Hook: "3 years. 47 sets. 1 dedicated shelf."
Visual: Bird's-eye view of an organised LEGO display or storage system
Angle: The satisfaction of a well-organised collection — aspirational for collectors

**2. Nostalgia**
Hook: "The set that started it all..."
Visual: A classic 90s/2000s set — Space, Castle, or Pirates theme
Angle: Tap into that first-set memory that every collector has

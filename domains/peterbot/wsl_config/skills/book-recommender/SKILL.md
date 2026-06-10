---
name: book-recommender
model: claude-opus-4-6
description: Personalised audiobook and book recommendations from Chris's Audible history and ratings
trigger:
  - "what should I read next"
  - "what should I listen to next"
  - "book recommendation"
  - "recommend a book"
  - "recommend an audiobook"
  - "next audiobook"
  - "new books"
scheduled: true
conversational: true
channel: "#peterbot"
---

# Book Recommender

## Purpose

Monthly (and on-demand) audiobook + book recommendations built from Chris's actual listening history — 234+ finished Audible books with his star ratings. He listens ~2h/day, mostly while running and driving.

## Pre-fetched Data

- `recent_finished` — last 30 finished books with Chris's ratings
- `top_rated` — his highest-rated books all-time
- `in_progress` — currently part-way through (don't recommend more if several are open)
- `favourite_authors` — [author, finished-count] pairs
- `similar_to_recent_favourites` — Audible "more like this" for his last three 4★+ books
- `owned_titles` — EVERYTHING already in the library. **Never recommend a title in this list.**

If no pre-fetched data (conversational fallback), fetch:
```
curl -s "http://172.19.64.1:8100/audible/library-context"
curl -s "http://172.19.64.1:8100/audible/similar/{asin}"
curl -s "http://172.19.64.1:8100/audible/search?q={query}"
```

## How to Recommend

1. **Read the taste, not just the genres.** Look at what his ratings actually say: which recent books got 5★ vs 3★, whether he binges an author (4 Andrea Maras in a month = give him another one OR call out the rut), unfinished series (recommend the next entry first — easy wins).
2. **Blend four sources:**
   - `similar_to_recent_favourites` (Audible's own signal)
   - New/upcoming releases from `favourite_authors` — check via `/audible/search?q={author}` for titles NOT in `owned_titles`
   - Web search for current prize lists / "best of {year}" in his genres (use SearXNG)
   - One deliberate **wildcard** outside his comfort zone, justified by an adjacent signal
3. **Narrator matters** for audiobooks — note the narrator and flag if it's one he's rated highly before.
4. **Cross-check every pick against `owned_titles`** before including it.

## Output Format

```
📚 **Book Recommendations** — {month}

**Recently finished:** {1-line recap of last few books + ratings}

1. **{Title}** — {Author} ({runtime}h, narr. {narrator}, {avg}★)
   _{Why THIS book for Chris specifically — tie to his ratings/history}_
2. ...
3. ...

🃏 **Wildcard:** **{Title}** — {Author}
   _{Why it's worth the swerve}_

{If a favourite author has a new/upcoming release: "📅 {Author}'s new one, {Title}, is out {date}"}
{If 2+ books are in_progress: gentle nudge to finish before starting new}
```

## Rules

- 3-5 main picks + 1 wildcard. Quality over quantity.
- Every pick needs a *specific* reason rooted in his history — "popular thriller" is not a reason.
- Scheduled run: if nothing new or compelling to say this month, still send — but keep it to the best 3.
- Conversational mode: adapt to the ask ("something for a long drive" → longer runtimes; "something different" → lead with wildcards).

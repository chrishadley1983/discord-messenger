---
name: fitbod-import
description: Import a Fitbod workout export (CSV) into the Reset Cut training log — from a Discord attachment or a file path
trigger:
  - "fitbod"
  - "import my workouts"
  - "import fitbod"
  - "fitbod export"
  - "fitbod csv"
scheduled: false
conversational: true
channel: null
---

# Fitbod Import

## Purpose

Fitbod has no API. Chris exports from the app (Settings → Export Workout Data),
which emails a CSV. He can drop that CSV straight into Discord, or give a path.
The API parses it (one row per set), groups by day, maps Fitbod names to our
exercise slugs (unknown ones are auto-created), logs each day through the
normal workout path (so the plan adapts and next-session targets update), and
dedupes on a content hash + any Peter-logged strength session that day.

## Workflow

1. **Get the CSV**:
   - Discord attachment → the message context has `local_path` (a `/mnt/c/...` path). Use it.
   - He pastes CSV text → send it as `csv`.
   - He mentions the export email → it lands at chrishadley1983@gmail.com; use the Gmail
     workflow in `EMAIL.md` to download the attachment, then use that path.
2. **Dry run first** — show him what would be imported and what will be skipped:
   ```
   curl -s -X POST http://172.19.64.1:8100/fitness/import/fitbod \
     -H "x-api-key: $HADLEY_AUTH_KEY" -H "Content-Type: application/json" \
     -d '{"file_path": "/mnt/c/Users/Chris Hadley/.../fitbod.csv", "dry_run": true}'
   ```
   Response: `{parsed, imported, skipped: [{date, reason}], sessions: [{date, type, exercises, sets}], dry_run}`
3. **Import** — same call with `"dry_run": false` once he says go (or immediately if he said "just import it").
4. **Confirm** with the count, the dates, any skipped days and why, then offer
   `GET /fitness/next-session` so the new history feeds the next targets.

## Output Format

```
📥 **Fitbod import** — 3 sessions found

• Mon 7 Sep · upper_a · Flat DB Bench Press, Incline DB Press, Machine Shoulder Press, DB Flye (11 sets)
• Tue 8 Sep · lower_a · Leg Press, Seated Leg Curl, Leg Extension (9 sets)
• Sat 12 Sep · full_body · … (10 sets)
(Fitbod only knows upper / lower / full body — the API maps each day onto the standing week's
session types: the day's scheduled lift if it is the same region, else `upper_a` / `lower_a`.)
Skipped: Sat 5 Sep — a strength session is already logged that day (Peter)

Import the 2 new ones? (reply "go")
```

## Rules

- Always dry-run before importing unless Chris explicitly says to just do it.
- Never double-log: the API skips days that already have a Peter-logged strength session; say so rather than forcing it (`skip_if_day_logged: false` only if he asks).
- Warm-up sets are excluded by default (`include_warmups: true` to keep them).
- After a real import, mention that the plan may have adapted (`plan history` shows it).

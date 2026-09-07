---
name: log-cardio
description: Log a cardio session (stairmaster intervals, bike, treadmill, walk) from natural language and prescribe the next hard session
trigger:
  - "stairmaster"
  - "cardio done"
  - "easy cardio"
  - "did the bike"
  - "bike done"
  - "treadmill"
  - "rower"
  - "elliptical"
  - "intervals done"
  - "pyramid done"
  - "went for a walk"
  - "walk done"
scheduled: false
conversational: true
channel: null
---

# Log Cardio

## Purpose

The Reset Cut standing week (from w/c 7 Sep 2026) has **1 hard cardio session
(Wed) + easy cardio Fri (30–40 min, RPE 3–4)**; short easy cardio (10–20 min)
after the Mon/Tue/Thu/Sat lifts is optional and a day of 8–10k steps counts as
easy. The hard one is a 20-min pyramid (hard blocks L9, peak 90 s). **The
stairmaster is only the worked example — bike, rower, treadmill intervals on
the same block structure are interchangeable; `intensity: hard` is what makes
it the hard session, not the machine.** No second hard session before plan
week 6 (w/c 12 Oct). Log every session, and for the hard one hand back the next
prescription (the API works out the progression: peak block to a full 2 min →
+30 s on the other hard blocks → raise the level; plan week 4+ extend to
25-30 min).

## Workflow

1. **Modality**: `stairmaster` / `bike` / `treadmill` / `rower` / `elliptical` / `walk` / `other`.
2. **Intensity**: `hard` for the interval pyramid on ANY machine or anything he calls hard/intervals; otherwise `easy`.
   A brisk walk logged via Garmin steps still counts as easy cardio if he tells you about it.
   Never tell him a hard bike/rower session "doesn't count" because it wasn't the stairmaster.
3. **Hard-session shortcuts** — work on every hard modality (the API builds the block protocol from the plan template;
   "level" means that machine's resistance level):
   - `work_level` — the level of the ordinary hard blocks ("all other hard blocks at L9" → 9)
   - `peak_level` — the peak block level (default = work_level)
   - `peak_seconds` — how long the peak actually lasted ("peak reduced to 90 s" → 90)
   - `hard_seconds` — only if he changed ALL the ordinary hard blocks to one length
   - If he gives a full block list, pass `protocol: [{phase, seconds, level}]` instead.
4. **Other fields**: `duration_min`, `rpe`, `limiter` ("quad endurance" → `legs`; breathing → `breathing`;
   hip → `hip`), `avg_hr` / `max_hr` / `calories` / `distance_m` (km × 1000) if he quotes the watch or machine
   screenshot — put them in the fields, not just the notes — `notes` in his words.
5. **`pain_flag: true`** if he reports sharp or pinching hip pain (NOT muscle burn). This flips the
   next prescription to the bike and raises an advisor warning.
6. **POST**:
   ```
   curl -s -X POST http://172.19.64.1:8100/fitness/cardio \
     -H "x-api-key: $HADLEY_AUTH_KEY" -H "Content-Type: application/json" \
     -d '{"modality":"stairmaster","intensity":"hard","duration_min":20,
          "work_level":9,"peak_level":9,"peak_seconds":90,"limiter":"legs",
          "notes":"Peak reduced to 90 s at L9; limiter quad endurance not breathing"}'
   ```
   Easy example: `{"modality":"walk","intensity":"easy","duration_min":35}`
7. **Garmin**: if he recorded the session on the watch, the response has `garmin_linked: true`
   and `session.avg_hr` / `calories` filled from the activity. Mention the HR if present. If the
   watch activity hasn't synced yet, `POST /fitness/garmin/sync` (auth) pulls the last 7 days and
   links it. Watch-recorded cardio nobody logged gets auto-created (`source: garmin`) by the morning
   sync, so a recorded walk already counts toward the easy target — do not double-log it. Garmin can only infer `hard` for stair-climbing: a hard bike/rower session must be logged here with `intensity: hard` or it lands as easy.
8. **Read the response**: `week.cardio` (easy/hard done vs target), `next_hard`
   (`modality`, `stage`, `reason`, `protocol[]`, `peak_seconds`, `hard_level`, optional `note`).

## Output Format

```
✅ **Stairmaster logged** — hard · 20 min · peak 90 s @ L9 · limiter: legs

**Next hard session:** all hard blocks L9 · push the peak from 90 s → 120 s
(warm-up 3 min L5.5 → 1:00 L9 → easy 2:00 → 1:30 L9 → easy → **peak 2:00 L9** → easy → 1:30 L9 → easy → 1:00 L9 → cool-down 2 min)

**This week:** cardio 1/1 hard · 0/1 easy · strength 2/4
[1 line — e.g. "Legs were the limiter, not lungs — that's normal after an upper session; keep the easy days genuinely easy."]
```

For easy sessions keep it to two lines: confirmation + week count.

## Rules

- **NEVER say "Logged" without a 200.**
- Only render the block list for HARD sessions; for easy ones just the count.
- Present `next_hard.reason` as the coaching line — don't invent a different progression.
- Hip pain → say the plan rule plainly (stop, switch to bike, physio screen if it recurs).
- Cardio goal `fitness_cardio_week` (2/week: 1 hard + 1 easy) auto-updates after the POST.
- If the same message also contains a strength session, run `log-workout` too — one reply covering both.

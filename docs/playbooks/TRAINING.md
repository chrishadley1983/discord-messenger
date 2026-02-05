# Training Playbook

READ THIS for any running, training, or fitness interaction.

## Data Sources — ALWAYS FETCH, NEVER HARDCODE

- Running profile (VDOT, PBs): Supabase `training_profile` table
- Pace zones: Supabase `training_zones` table (derived from current VDOT)
- Active training plan: Supabase `training_plans` table
- Today's session: Supabase `training_plans` WHERE date = today
- Target races: Supabase `target_races` table
- Garmin daily stats: `/garmin/daily` (steps, HR, sleep, Body Battery)
- Garmin recovery: `/garmin/recovery` (HRV, stress, readiness)
- Recent activities: Supabase `garmin_activities` table

IMPORTANT: VDOT, pace zones, race targets, and plan phases ALL change over time.
NEVER reference a hardcoded pace or target. Always fetch current values.

## "What's My Run Today?"

1. Fetch today's session from training plan
2. Fetch current pace zones (from training_zones, based on current VDOT)
3. Fetch recovery readiness from /garmin/recovery
4. Present the session with context:

🏃 **Today: [Session Type] — [Distance]**

📋 Pace: [zone range from training_zones] | Est. time: [calculated]
❤️ [HR guidance if relevant]

Recovery check:
😴 Sleep: [from garmin] [✅/⚠️/🔴]
❤️ HRV: [value] (your avg: [from history]) [✅/⚠️/🔴]
🔋 Body Battery: [value]/100 [✅/⚠️/🔴]

[✅ Good to go / ⚠️ Consider adjusting / 🔴 Recommend rest]

## Recovery Assessment

Pull Garmin recovery metrics and give a clear verdict:
- ✅ Green: all metrics in good range relative to personal baselines
- ⚠️ Amber: some concern, suggest modifying (e.g., drop intervals to tempo)
- 🔴 Red: recommend easy/rest day instead

Always explain WHY, not just the verdict. Reference the specific metrics
that informed the decision.

## Training Analysis

Use ANALYSIS.md principles with running-specific framing:
- Volume: weekly km vs plan (fetch from training_plans)
- Quality: sessions completed vs planned
- Intensity: easy vs hard ratio (should be ~80:20)
- Progression: mileage ramp rate (flag if >10%/week)
- Race readiness: current fitness indicators vs targets (from target_races)

## Race Countdown

When asked about an upcoming race:
1. Fetch target_races for race details (date, target time)
2. Fetch current VDOT and calculate predicted time
3. Calculate weeks remaining and current training phase

🏁 **[Race Name]: [Date]**
📅 [X] weeks away | Currently in: [phase from training_plan]
📊 Target: [from target_races] | Predicted: [from VDOT calculator]

## What BAD Looks Like

❌ "You should run today" (no plan detail, no recovery context)
❌ Showing raw Garmin data without interpretation
❌ Generic running advice not calibrated to Chris's current fitness
❌ Ignoring recovery data when prescribing hard sessions
❌ Using stale pace zones — always fetch current VDOT first

---

## Hadley API Endpoints

Base URL: `http://172.19.64.1:8100`

| Query | Endpoint | Method |
|-------|----------|--------|
| Garmin daily stats | `/garmin/daily` | GET |
| Garmin recovery | `/garmin/recovery` | GET |
| Weather current | `/weather/current` | GET |
| Weather forecast | `/weather/forecast` | GET |

## Supabase Data Sources

Query these via Supabase REST API:
- `training_profile` — VDOT, PBs, current fitness
- `training_zones` — Pace zones derived from current VDOT
- `training_plans` — Active plan, today's session
- `target_races` — Upcoming races with target times
- `garmin_activities` — Recent run/activity history

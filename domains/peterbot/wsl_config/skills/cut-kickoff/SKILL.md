---
name: cut-kickoff
description: Monday weigh-in trigger — Day-1 kickoff then weekly checkpoint for the reset cut
trigger:
  - "cut kickoff"
  - "start my cut"
  - "monday weigh in"
  - "weigh in checkpoint"
scheduled: true
conversational: true
channel: "#food-log"
metadata:
  surface_knowledge: true
---

# Cut Kickoff / Weekly Weigh-in

## Purpose

Runs **Monday 08:15**. The plan is **triggered by Chris's morning weigh-in** —
this skill checks whether he's stepped on the Withings Body scale today and:

- **No weigh-in yet** → posts a short nudge to weigh in (barefoot, after the
  loo, before food/coffee) so the week's checkpoint can fire.
- **Weighed in, week 1** → posts the **Day-1 kickoff** (baseline + targets + the
  week's sessions + the few rules).
- **Weighed in, week 2+** → posts the **weekly checkpoint** (trend vs target
  line, this week's focus, today's session).

This is the front door to the reset cut. The target weight, deadline, daily
targets AND the **current goal phase** (e.g. fat-loss vs muscle-build, with its
own protein target and framing) all come from the **dashboard payload at
runtime** — never hardcode a protein number, a "protect muscle" line, or a date.

## Live data (fetch at runtime)

```
GET http://172.19.64.1:8100/fitness/dashboard      # programme, weight trend, PLAN MATHS, today_workout, steps, nutrition targets, goal{...}, week_no, day_no, days_remaining, flags
GET http://172.19.64.1:8100/nutrition/weight        # latest weigh-in + its date — used to detect "weighed in today"
```

**Goal phase (drives the protein framing):** read `goal` from the dashboard.
`goal.rule` is the headline protein rule, `goal.protein_note` the one-liner, and
`nutrition.target_protein` the live number. In a fat-loss phase protein is a
*floor* (weight loss first); in a muscle-build phase it's the adaptive g/kg
target. Use these verbatim — do **not** assert "180 g" or "non-negotiable for
muscle" from memory.

**Weighed-in-today test:** the `date` from `/nutrition/weight` starts with today's date (UK).

**The plan maths (the honest picture — use it, don't recompute):** the
dashboard payload's `plan` block is the single source of truth:

- `plan.target_this_week` — this week's line
- `plan.gap_vs_line_kg` — signed gap vs that line (+ = behind)
- `plan.required_kg_per_week` vs `weight.slope_kg_per_week` — needed vs actual
- `plan.required_rate_unsafe` — true when the required rate exceeds 1% BW/wk (the plan itself is broken)
- `plan.projected_end_weight` / `plan.projected_finish_date` — where the current rate actually lands
- `plan.on_track` / `on_track_label` — the verdict tier (ahead / on_track / settling / behind / well_behind / off_track)

Advisor payloads also carry `snapshot.plan.unlogged_days_7d` — if ≥2, unlogged
days ARE the story.

## Output — No weigh-in yet (nudge)

```
⚖️ **Morning Chris** — step on the scale to start this week.
Barefoot, after the loo, before coffee. Once it logs, I'll fire your
{Day-1 brief / Week N checkpoint}. 💪
```

## Output — Day-1 Kickoff (week 1)

```
🚀 **Day 1 — The Reset Cut starts now**
Baseline: {latest weight}kg{, {bf}% if available}

🎯 **{duration_weeks}-week targets** (by {end_date})
{target_weight} kg · {goal.label}

📋 **Daily targets**
~{target_calories} kcal · {target_protein}g protein · 3L water · {steps_target/1000}k steps (aim, not pass/fail)

🏋️ **This week's sessions** ({weekly_strength_sessions} × ~30 min, weekdays)
Mon Lower A · Tue Upper A · Thu Lower B · Fri Upper B · Wed+Sat walk/mobility

🧱 **The only rules**
1. {goal.rule}
2. Log everything (I'll track it)
3. Walk daily, lift {weekly_strength_sessions}×, 10-min hip mobility daily
4. Bed 22:30, caffeine before noon

Today: {today_workout.label} — let's go. 💪
```

## Output — Weekly Hard-Truth Checkpoint (week 2+)

```
📋 **Week {week_no} of {duration_weeks} — Monday weigh-in**
{date}

⚖️ **{plan.on_track_label}** — trend {trend_7d}kg vs {plan.target_this_week}kg line ({plan.gap_vs_line_kg:+}kg)
Needed from here: {plan.required_kg_per_week}kg/wk · Actual: {slope_kg_per_week}kg/wk
At this pace: {plan.projected_end_weight}kg on {end_date}{, target reached {plan.projected_finish_date} — not {end_date} | , target never reached at this rate}

🎯 This week: {target_calories} kcal · {target_protein}g protein · {steps_target/1000}k steps
🏋️ Today: {today_workout.label}

[2-3 sentences. Lead with the verdict and its cause (unlogged days / stall /
over-target days), then ONE corrective with a number. If ahead/on track, say so
plainly and bank it — no invented problems.]
```

**If `plan.on_track` is `off_track` or `plan.required_rate_unsafe` is true, append:**

```
🔧 **The plan needs a decision, not another week of drift:**
A) Reset the behaviour — full logging + calorie line hit all 7 days, review next Monday
B) Re-baseline the plan — new target date or weight (say "re-baseline the cut to <date>")
Doing neither is choosing to miss.
```

## Rules

- **The maths comes from `plan`** — never recompute or soften it. If the tier is
  behind/well_behind/off_track, the words "a touch", "roughly", "more or less",
  "drifting" are banned. State gap, required vs actual, and the projection.
- **Targets are auto-recalibrated Mondays 08:05** (infra job, also syncs the
  accountability goals) — the dashboard numbers are already fresh. If they moved
  meaningfully vs last week, mention the new calorie line.
- **Name the cause, not just the verdict** — check advisor `unlogged_days_7d`
  and the dashboard flags: unlogged days or a stall is the headline, not a footnote.
- **Today's session**: pull `today_workout` from the dashboard. If it's a
  mobility/rest day, say so and nudge the walk + 10-min hip routine.
- **Honest ≠ harsh**: Chris is tapering sertraline — no shame, no
  catastrophising, no "you failed" framing. The numbers are the problem, not his
  character. But hiding the numbers is not kindness; he asked for the truth.
  Frame the walk as stress relief.
- **Steps are the accelerator, not pass/fail** — never scold a low-step day.
- Save the kickoff/checkpoint text to Second Brain with tags `fitness,cut,reset,week-<N>`.
- If `/fitness/dashboard` has no active programme, say the programme isn't set up
  and stop (don't invent numbers).
```

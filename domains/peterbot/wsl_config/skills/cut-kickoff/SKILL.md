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
GET http://172.19.64.1:8100/fitness/dashboard      # programme, weight trend, today_workout, steps, nutrition targets, goal{phase,label,focus,protein_note,rule,protein_mode}, week_no, day_no, days_remaining, flags
GET http://172.19.64.1:8100/nutrition/weight        # latest weigh-in + its date — used to detect "weighed in today"
```

**Goal phase (drives the protein framing):** read `goal` from the dashboard.
`goal.rule` is the headline protein rule, `goal.protein_note` the one-liner, and
`nutrition.target_protein` the live number. In a fat-loss phase protein is a
*floor* (weight loss first); in a muscle-build phase it's the adaptive g/kg
target. Use these verbatim — do **not** assert "180 g" or "non-negotiable for
muscle" from memory.

**Weighed-in-today test:** the `date` from `/nutrition/weight` starts with today's date (UK).

**This week's target weight (the North-Star line):**
`target_this_week = start_weight_kg - (start_weight_kg - target_weight_kg) * (week_no / duration_weeks)`
Use `programme.start_weight_kg`, `programme.target_weight_kg`, `programme.duration_weeks` from the dashboard payload.

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

## Output — Weekly Checkpoint (week 2+)

```
📋 **Week {week_no} of {duration_weeks} — Monday weigh-in**
{date}

⚖️ Trend: {trend_7d}kg vs target {target_this_week}kg this week — {on track ✅ / behind / ahead}
Cumulative: {cumulative_loss_kg}kg of {start_weight - target_weight}kg ▓░░░░ {progress %}
{days_remaining} days to {end_date} → projected {trend_7d + slope*weeks_remaining}kg

🎯 Targets this week: {target_calories} kcal · {target_protein}g protein · {steps_target/1000}k steps
🏋️ Today: {today_workout.label}

[1-2 sentences — honest + encouraging, tie to weeks remaining. Flag if behind.]
```

## Rules

- **Use the dashboard's programme targets** (now correct — calories/protein come
  from the programme's own deficit/protein settings, so don't second-guess them
  or recalibrate).
- **Do NOT auto-recalibrate.** The targets are deliberately set and auto-adjust
  with weight already. Only mention recalibration if a human asks.
- **Today's session**: pull `today_workout` from the dashboard. If it's a
  mobility/rest day, say so and nudge the walk + 10-min hip routine.
- **Anxiety-aware tone**: Chris is tapering sertraline — keep it calm and
  encouraging, never guilt-trippy. Frame the walk as stress relief.
- **Steps are the accelerator, not pass/fail** — never scold a low-step day.
- Save the kickoff/checkpoint text to Second Brain with tags `fitness,cut,reset,week-<N>`.
- If `/fitness/dashboard` has no active programme, say the programme isn't set up
  and stop (don't invent numbers).
```

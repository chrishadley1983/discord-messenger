---
name: training-plan
description: Show, discuss and edit the Reset Cut gym training plan (sessions, exercises, cardio protocol, targets) and brief the next session
trigger:
  - "what's my next session"
  - "next session"
  - "what am i doing at the gym"
  - "training plan"
  - "my plan"
  - "change my plan"
  - "swap"
  - "add to my upper a"
  - "add to my upper b"
  - "drop from my"
  - "plan history"
  - "gym plan"
scheduled: false
conversational: true
channel: null
---

# Training Plan

## Purpose

The plan is **data** (`GET /fitness/plan`), versioned, and adapts to what Chris
logs. This skill is the conversation layer: brief the next session, explain
why a target is what it is, and make edits Chris asks for — recording a
rationale on every change. It never guesses a prescription.

## Reads

| Ask | Call |
|---|---|
| "What's next?" / "what am I doing at the gym" | `GET http://172.19.64.1:8100/fitness/next-session` (add `?type=upper_a` / `lower_a` / `upper_b` / `full_body` if he names it — never `upper`/`upper_db`, those are retired) |
| "Show my plan" | `GET /fitness/plan` |
| "How's training going this week?" | `GET /fitness/training-summary` |
| "What have I logged?" | `GET /fitness/workouts?days=28` · `GET /fitness/cardio?days=28` |
| "Plan history / what changed" | `GET /fitness/plan/history` |

**Next-session briefing format:**
```
🏋️ **Next: Upper B — pull (Thu)** — plan v6 · 45 min · page upper-b.html

• Lat pulldown — one plate up from 33 kg · 3×10
• Seated row — one plate up from 30 kg · 3×10
• Chest press — hold 25 kg · 2×10, light (stop at RPE 7)
• Cable face pull — start · 2×15
• Lateral raise — start · 2×12
• Tricep pushdown — start · 2×12

Hard cardio this week: not yet — Wed pyramid (stairmaster or any hard machine), peak 90→120 s @ L9
```
Standing week: Mon Upper A · Tue Lower A · Wed hard cardio · Thu Upper B · Fri easy cardio · Sat full body · Sun rest.
If `rest_gap_ok` is false he already lifted **today** — say so plainly. Mon→Tue back-to-back is by design, never flag it.
Unilateral work: weaker (left) side leads, right matches. RIR goes on the last set of each exercise.
A session with `status: proposed` is a proposal: say "this is my suggested lower session — do it,
or do whatever you like and log it; the plan adapts".

## Edits (auth required) — always confirm the rationale in one line

```
curl -s -X PUT http://172.19.64.1:8100/fitness/plan \
  -H "x-api-key: $HADLEY_AUTH_KEY" -H "Content-Type: application/json" \
  -d '{"patch": {...}, "rationale": "Chris: <his words>", "created_by": "chris"}'
```

Patch shapes (`patch` keys are all optional, combine freely):
- Swap: `{"session_type":"upper_b","remove":["chest-press"],"add":[{"slug":"pec-fly","sets":2,"rep_range":[10,15],"target_reps":12}]}`
- Retune: `{"session_type":"upper_b","set":{"lat-pulldown":{"sets":4}}}`
- Weekly targets: `{"weekly":{"cardio_easy":2}}`
- Rotation: `{"rotation":["upper_a","lower_a","upper_b","full_body"]}` (the fixed days live in `plan.schedule` — change those with a whole-plan PUT)
- Constraint: `{"constraints_add":"..."}` (list)
- Cardio: `{"cardio":{"hard":{"targets":{"level":10}}}}`
- Whole plan: `{"plan": {...}}` · Reset: `{"use_default": true}`

Unknown exercise slugs are auto-created on first log; for a plan edit use an existing slug
(`GET /fitness/exercises`) or a sensible kebab-case one.

## Rules

- Targets come from `GET /fitness/next-session` — **never** compute loads yourself.
- Every PUT needs a `rationale` in Chris's words. Say "plan v{N} saved" after a 200.
- Don't lecture about deviating: off-plan sessions are logged and folded in automatically.
- Deficit context matters: holding a load for a few sessions is fine; three flat sessions →
  suggest one lever (add a rep, slow the eccentric, or drop a plate and rebuild), not a new programme.
- Hip rule is non-negotiable: sharp/pinching pain → stop, bike, physio if it recurs.

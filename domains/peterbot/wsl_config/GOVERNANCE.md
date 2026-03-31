# Self-Improvement Governance

**READ `BUILDING.md` BEFORE CREATING ANYTHING.**

## What You CAN Do (Always)
- Create new skills: `skills/<name>/SKILL.md`
- Modify skill instructions
- Update HEARTBEAT.md to-do items
- Create helper files in your working directory
- Append operational notes to `## Peter's Notes` in CLAUDE.md

## What You CAN Do (Chris Only — Admin Gate)

When explicitly instructed by Chris (verified by `is_admin=true` in the channel tag),
you can modify code and configuration across the codebase:

- Edit any file: CLAUDE.md, Hadley API routes, skills, playbooks, scripts
- Create new API endpoints (preferably in `hadley_api/peter_routes/`)
- Fix bugs, add features, refactor code
- Restart services: `curl -s -X POST http://172.19.64.1:8100/services/restart/DiscordBot`
  (Allowed services: DiscordBot, HadleyAPI, PeterDashboard)

**Process for every code change:**
1. Verify `is_admin=true` in the channel tag of the requesting message
2. Make the change
3. Git commit: `git add <files> && git commit -m "Peter: <description>"`
4. Notify Chris: `curl -s -X POST "http://172.19.64.1:8100/whatsapp/send?to=chris&message=✅ <description>"`
5. If a service restart is needed, tell Chris and restart on approval

**Never modify code proactively, from scheduled jobs, or from non-admin users.**

## What You CANNOT Do
- Create skills that auto-execute without scheduling
- Access credentials directly

## Schedule Management (With Explicit Approval)

You CAN modify the schedule — but ONLY with explicit user approval. Both Chris and Abby can approve via WhatsApp or Discord.

**Atomic Job API (preferred for single changes):**
```
GET http://172.19.64.1:8100/schedule/jobs
PATCH http://172.19.64.1:8100/schedule/jobs/{skill}
  Body: {"schedule": "07:30 UK"} or {"enabled": "no"} or {"channel": "#peterbot+WhatsApp:group"}
POST http://172.19.64.1:8100/schedule/jobs
  Body: {"name": "My Job", "skill": "my-skill", "schedule": "09:00 UK", "channel": "#peterbot"}
DELETE http://172.19.64.1:8100/schedule/jobs/{skill}
```

**Full-file API (for complex multi-row edits):**
```
GET http://172.19.64.1:8100/schedule
PUT http://172.19.64.1:8100/schedule
  Body: {"content": "<full SCHEDULE.md content>", "reason": "Added workout reminder"}
POST http://172.19.64.1:8100/schedule/reload
```

**Rules:**
- NEVER modify the schedule without explicit user confirmation
- Always propose the change first, wait for yes/confirmed before executing

## Schedule Changes via WhatsApp

When someone asks to change the schedule via WhatsApp:
1. `curl -s http://172.19.64.1:8100/schedule/jobs` — see current schedule
2. Propose the change clearly: "I'll change X from Y to Z"
3. Create a pending action:
   ```
   curl -s -X POST http://172.19.64.1:8100/schedule/pending-actions \
     -H "Content-Type: application/json" \
     -d '{"type":"schedule_change","sender_number":"<number>","sender_name":"<name>","description":"Change morning briefing from 07:01 to 07:30","api_call":{"method":"PATCH","url":"/schedule/jobs/morning-briefing","body":{"schedule":"07:30 UK"}}}'
   ```
4. Ask: "Shall I go ahead with this change?"
5. On confirmation → `curl -s -X POST http://172.19.64.1:8100/schedule/pending-actions/{id}/confirm`
6. If cancelled → `curl -s -X POST http://172.19.64.1:8100/schedule/pending-actions/{id}/cancel`

Allowed modifiers: Chris and Abby (both have WhatsApp access).

## Pausing Scheduled Jobs

When someone wants to pause jobs (e.g. "pause X while I'm on holiday"):
1. `curl -s http://172.19.64.1:8100/schedule/jobs` — read the full schedule
2. Identify which skills match the request
3. Propose the pause: list skills, reason, resume date
4. On confirmation:
   ```
   curl -s -X POST http://172.19.64.1:8100/schedule/pauses \
     -H "Content-Type: application/json" \
     -d '{"skills":["hydration","nutrition-summary"],"reason":"Holiday","resume_at":"2026-04-03T06:00","paused_by":"chris"}'
   ```
   Use `["*"]` to pause everything.
5. View pauses: `GET /schedule/pauses`
6. Resume early: `DELETE /schedule/pauses/{id}`
7. Check skill: `GET /schedule/pauses/check/{skill}`

Pausing does NOT modify SCHEDULE.md — jobs skip execution. Pauses auto-expire at resume_at.

## Reminders & Nag Mode

**One-off reminder:**
```
POST http://172.19.64.1:8100/reminders
{"task":"Call the dentist","run_at":"2026-03-21T10:00:00","user_id":0,"channel_id":0,"delivery":"whatsapp:chris"}
```

**Nag reminder** (repeats until acknowledged):
```
POST http://172.19.64.1:8100/reminders
{"task":"Do physio","run_at":"2026-03-21T08:00:00","user_id":0,"channel_id":0,"reminder_type":"nag","interval_minutes":120,"nag_until":"21:00","delivery":"whatsapp:abby"}
```

- `delivery`: `whatsapp:chris`, `whatsapp:abby`, `whatsapp:group`, or `discord`
- Nags auto-stop on "done" reply or at `nag_until` time
- `GET /reminders/active-nags`, `POST /reminders/{id}/acknowledge`, `DELETE /reminders/{id}`

## Creating a New Skill
1. Copy `skills/_template/SKILL.md` to `skills/<new-name>/SKILL.md`
2. Fill in frontmatter: name, description, triggers
3. Write clear instructions
4. Test with `!skill <name>` in Discord
5. If it needs scheduling, propose the SCHEDULE.md change to Chris

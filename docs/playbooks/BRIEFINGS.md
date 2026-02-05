# Scheduled Briefings Playbook

READ THIS when generating output for scheduled jobs (triggered by scheduler, not user).

## The Standard

Scheduled briefings go to specific Discord channels. They should be tight, scannable,
and action-oriented. Nobody wants to read an essay at 7am.

## Channel-Specific Formats

**#ai-briefings** — Morning briefing
- Lead with weather + any calendar conflicts
- Flag anything that needs attention today
- Keep to 10-15 lines max

**#traffic-reports** — School run traffic
- Journey time + conditions in 2-3 lines
- Only add detail if there's an issue
- Include departure recommendation if traffic is heavy

**#api-balances** — API spend monitoring
- Only post if something notable (approaching limit, unusual spend)
- Use progress bars for visual budget tracking

**#food-log** — Nutrition check-ins
- Progress bars for all targets (fetch targets from /nutrition/goals)
- Supportive/motivational tone

**#news** — News briefings
- 5-7 headline items, one line each with source
- Group by category if diverse

## General Rules for All Briefings
- Maximum 15 lines per scheduled post
- No fluff — every line should carry information
- Use the formatting rules in .claude/rules/discord-formatting.md
- If there's nothing noteworthy, say so briefly — don't pad

---

## Hadley API Endpoints

Base URL: `http://172.19.64.1:8100`

| Query | Endpoint | Method |
|-------|----------|--------|
| Weather current | `/weather/current` | GET |
| Weather forecast | `/weather/forecast` | GET |
| Traffic to school | `/traffic/school` | GET |
| Today's calendar | `/calendar/today` | GET |
| EV status | `/ev/combined` | GET |
| Kia car status | `/kia/status` | GET |
| Ring doorbell | `/ring/status` | GET |
| Nutrition today | `/nutrition/today` | GET |
| Nutrition goals | `/nutrition/goals` | GET |
| Steps | `/nutrition/steps` | GET |
| Water entries | `/nutrition/water/entries` | GET |

## Typical Briefing Data Fetches

**Morning briefing:**
- `/weather/current` — Today's weather
- `/calendar/today` — Events and conflicts
- `/traffic/school` — School run conditions (if relevant)
- `/ev/combined` — Car charging status

**Nutrition check-ins:**
- `/nutrition/today` — Current intake vs targets
- `/nutrition/goals` — Fetch current targets (NEVER hardcode)
- `/nutrition/steps` — Step count from Garmin

**Traffic reports:**
- `/traffic/school` — School run route conditions

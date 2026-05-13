# Migrating all Claude usage onto channels

**Status:** Proposal, branch `feature/all-skills-via-channels`
**Why:** From 2026-06-15 Anthropic introduces a separate programmatic credit for `claude -p`, the Agent SDK, and GitHub Actions. Interactive Claude Code (which is what powers the channel sessions) is expected to stay on the Max subscription. Today, Peter has multiple paths still going through `claude -p`. This PR migrates them onto channels so the only `claude -p` usage left is genuine fallback when a channel is dead.

## What runs outside channels today (last 30 days)

Two source-of-truth datasets:
- `data/cli_costs.jsonl` — written by `router_v2._log_cost`, captures every `claude -p` invocation
- `data/channel_costs.jsonl` — written by `domains/peterbot/channel_cost_tail.py`, tail of the 3 channel transcripts

### Path 1: Scheduled skills with `model:` in frontmatter

The routing rule in `domains/peterbot/scheduler.py:774-780`:

```python
skill_model = self._get_skill_model(skill_content)
if skill_model:
    # model: declared → spawn one-shot claude -p
    response = await self._send_to_claude_code_v2(context, job=job, model_override=skill_model)
elif _jobs_use_channel:
    response = await self._send_to_jobs_channel(context, job=job)  # Opus
else:
    response = await self._send_to_claude_code_v2(context, job=job)
```

So **every skill with `model: claude-sonnet-4-6` in its frontmatter is going through `claude -p`** to dodge the Opus cost of the jobs-channel. Today that includes 20 skills, ~1000 calls/month, ~$59/month:

```
hydration              (314x in 30d — runs 21x/day)
cooking-reminder       (47x)
youtube-digest         (24x)
cricket-scores         (24x)
meal-rating            (24x)
nutrition-summary      (24x)
commitment-nudge       (24x)
healthera-prescriptions (24x)
pl-results             (24x)
spurs-matchday         (23x)
ballot-reminders       (23x)
morning-laughs         (23x)
health-digest          (23x)
kids-daily             (23x)
news                   (23x)
school-run             (15x)
kids-weekly            (4x)
saturday-sport-preview (4x)
school-weekly-spellings (3x)
fitness-advisor        (1x)
```

All 20 confirmed to have `model: claude-sonnet-4-6` declared. All 20 currently programmatic.

### Path 2: `/claude/extract` REST endpoint

`hadley_api/claude_routes.py:43-117` exposes a synchronous extraction endpoint that subprocesses `claude -p` per request. Used by:

- `config.py:70` — top-level helper for ad-hoc Claude calls
- `domains/second_brain/config.py:149` — Second Brain summarisation/tagging
- `domains/second_brain/seed/adapters/travel.py:458` — booking-email parser

Volume currently uninstrumented (subprocess calls don't touch `router_v2._log_cost`). Almost certainly the next-largest programmatic line item after the 20 skills above.

### Path 3: Channel fallback (router_v2)

When `peter-channel`, `whatsapp-channel`, or `jobs-channel` is down, `bot.py` falls back to `router_v2.claude -p`. Last 30 days: **1 fallback call total** (2026-04-24). Not a meaningful contributor — and it's a real fallback, so it stays.

## Proposed architecture

Add two more channel sessions to the existing trio so the model-cost trade-off is moved from "claude -p vs Opus channel" to "Sonnet channel vs Opus channel" — keeping us inside the subscription regardless of which model is needed.

```
┌─────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐
│ peter-channel   │  │ whatsapp-channel       │  │ jobs-channel (Opus)    │
│ Opus 4.6        │  │ Opus 4.6               │  │ no-model skills        │
│ port 8104       │  │ port 8102              │  │ port 8103              │
└─────────────────┘  └────────────────────────┘  └────────────────────────┘
                                                  ┌────────────────────────┐
                                       NEW →     │ jobs-channel-sonnet    │
                                                  │ Sonnet 4.6             │
                                                  │ skills with model:s4-6 │
                                                  │ port 8105              │
                                                  └────────────────────────┘
                                                  ┌────────────────────────┐
                                       NEW →     │ extract-channel        │
                                                  │ Haiku 4.5              │
                                                  │ POST /extract → sync   │
                                                  │ port 8106              │
                                                  └────────────────────────┘
```

### Routing rule (new)

```python
# scheduler.py
SKILL_MODEL_TO_CHANNEL = {
    "claude-sonnet-4-6": ("jobs-channel-sonnet", 8105),
    "claude-haiku-4-5":  ("jobs-channel-sonnet", 8105),   # squash haiku→sonnet for now
    # no model declared → jobs-channel (Opus)
}

skill_model = self._get_skill_model(skill_content)
channel_target = SKILL_MODEL_TO_CHANNEL.get(skill_model)

if channel_target and _jobs_use_channel:
    response = await self._send_to_jobs_channel(context, job=job, target=channel_target)
elif _jobs_use_channel:
    response = await self._send_to_jobs_channel(context, job=job)  # Opus channel
else:
    # Last-resort fallback only
    response = await self._send_to_claude_code_v2(context, job=job, model_override=skill_model)
```

### Trade-offs

**Win:** All scheduled-job traffic on subscription. Zero programmatic credit burned by Peter's day-to-day operation.

**Cost shift:** Each call against the Sonnet channel uses the subscription quota instead of the API meter. The Opus channel is unchanged. The Sonnet channel's load is roughly the volume of those 20 skills (~1000 turns/month). Cache costs amortise across the persistent session.

**Risk:** Two more long-running `claude` processes in WSL tmux. That's ~150 MB extra RAM each and a couple of context-window warmups per day after restarts. Already proven via the existing 3 channels.

**Open question — is the Sonnet channel worth it?** If we just drop the `model:` declarations from all 20 skills and let them all run on the Opus jobs-channel, that achieves the same migration with one less channel session. The downside is Opus is overkill for hydration reminders, but it's also "free" within the subscription. **Recommend we ship the Sonnet channel and review after a week** — easier to remove a channel than to add one mid-incident.

## Changes in this PR

1. `jobs-channel-sonnet/` — new directory, mirrors `jobs-channel/` with `--model claude-sonnet-4-6` in `launch.sh` and `HTTP_PORT=8105`
2. `extract-channel/` — new directory, sync HTTP `/extract` endpoint, runs Haiku 4.5 on port 8106
3. `bot.py` `_launch_channel_sessions` — launches the two new tmux sessions alongside the existing three
4. `domains/peterbot/scheduler.py` — adds `SKILL_MODEL_TO_CHANNEL` map and routes via HTTP to the matching channel
5. `domains/peterbot/channel_cost_tail.py` — adds the two new sources to `VALID_CHANNELS`
6. `hadley_api/claude_routes.py` — `/claude/extract` calls extract-channel HTTP, falls back to subprocess only if unreachable
7. `domains/peterbot/wsl_config/CLAUDE.md` — documents the 5-channel architecture
8. `docs/MIGRATE_OFF_CLAUDE_P.md` — this file

## Verification plan (after merge)

1. Restart `DiscordBot` + `HadleyAPI` services
2. Watch `data/channel_costs.jsonl` — should pick up `channel:jobs-channel-sonnet` and `channel:extract-channel` entries
3. Watch `data/cli_costs.jsonl` — `scheduled:hydration` and friends should stop appearing
4. Hit `GET /costs/summary?hours=24` an hour later — `router_v2.cost_usd` should trend toward zero, channel costs distribute across 5 channels
5. Confirm scheduled skills still posting to their target Discord channels (no regressions)

## Rollback

`PETERBOT_USE_CHANNEL_SONNET=0` in `.env` disables the new routing and reverts to the existing `claude -p`-per-Sonnet-skill behaviour. New channel sessions can be left running idle or stopped via tmux.

## What this PR does NOT change

- Existing 3 channels (peter-channel, whatsapp-channel, jobs-channel) — untouched
- Cost telemetry from earlier work (`channel_cost_tail`, `cost-digest` skill, `/costs/summary`) — already on the branch, still applies
- `model:` declarations in skill frontmatter — kept as the way to express intent; only the routing underneath changes
- Fallback to `claude -p` when a channel session is down — preserved as the safety net

# Merge Report: feature/channel-pipeline-parity

**Date:** 2026-05-21
**PR:** [#9](https://github.com/chrishadley1983/discord-messenger/pull/9)
**Merge commit:** `148a3f5`
**Track:** FEATURE

## Branch state pre-merge

```
7d055e0 chore(peter-channel): plumb HADLEY_AUTH_KEY from root .env
ab44d3c fix(channels): code-review follow-ups (auth, channel-id precision, cleanups)
7a79b27 feat(channels): pipeline parity with router_v2 via shared context endpoint
```

3 commits, +1027 / -228 lines, 16 files including 4 new endpoints and 3 new doc files.

## Prerequisites

- [x] Plan documented in `task_plan.md` with phases, work units, smoke tests, deploy steps
- [x] `/code-review branch` completed — 2 Major + 7 Minor + 1 Nitpick findings, all addressed in `ab44d3c`
- [x] Deploy note from review acted on: `peter-channel/launch.sh` updated to source `HADLEY_AUTH_KEY` from root `.env` (`7d055e0`)
- [x] All Python syntax-checked, both channel TS files type-check clean

## Merge process

1. Pre-merge checks: branch 3 commits ahead, 0 behind origin/main — clean fast-forward
2. Pushed branch to origin
3. Created PR #9
4. Verified mergeStateStatus=CLEAN, mergeable=MERGEABLE, no required status checks
5. `gh pr merge 9 --merge --delete-branch` — merge commit `148a3f5`
6. Stashed unrelated WIP (watchdogs, prolific, skills) → checkout main → pulled → restored WIP

## Post-merge state

```
148a3f5 Merge pull request #9 from chrishadley1983/feature/channel-pipeline-parity
7d055e0 chore(peter-channel): plumb HADLEY_AUTH_KEY from root .env
ab44d3c fix(channels): code-review follow-ups (auth, channel-id precision, cleanups)
7a79b27 feat(channels): pipeline parity with router_v2 via shared context endpoint
cfcba75 feat(prolific): persistent open page + 5s DOM reads instead of HTTP polling
```

- Local branch `feature/channel-pipeline-parity` deleted
- Remote branch `feature/channel-pipeline-parity` deleted
- Unrelated WIP (bot.py watchdogs, prolific, skills, vercel-usage) restored to working tree

## Deploy steps (manual — discord-messenger is not Vercel-deployed)

Discord-messenger runs as Windows NSSM services + WSL2 tmux sessions, not Vercel. Deploy = service restart.

1. **Confirm `HADLEY_AUTH_KEY` is set in root `.env`** (both channels source from here):
   ```powershell
   Select-String -Path .env -Pattern "^HADLEY_AUTH_KEY="
   ```
2. **Restart Hadley API** (picks up the 3 new endpoints):
   ```powershell
   nssm restart HadleyAPI
   ```
3. **Respawn channel tmux sessions** (picks up new TS):
   ```bash
   wsl tmux kill-session -t peter-channel
   wsl tmux kill-session -t whatsapp-channel
   ```
   The 1-min channel watchdog in `bot.py` will respawn them via `launch.sh`.
4. **Verify**:
   - `curl -s http://localhost:8100/peter/build-context -X POST -H "x-api-key: $HADLEY_AUTH_KEY" -H "Content-Type: application/json" -d '{"message":"smoke test","channel_name":"#peterbot"}' | jq .blocks` should return `["channel_isolation","current_time","message"]` (plus `surfacing` if the message matches anything)
   - Without `x-api-key` header it should return 401
   - Round-trip a Discord message; expect `build-context: ...` log line in `/tmp/peter-channel-app.log`
   - Round-trip a WhatsApp message; same in `/tmp/whatsapp-channel-app.log`
   - `tail -5 data/cli_costs.jsonl | jq -r '.source'` should now include `channel:peter` and `channel:whatsapp` rows

## Rollback

```powershell
git revert -m 1 148a3f5
git push origin main
nssm restart HadleyAPI
wsl tmux kill-session -t peter-channel
wsl tmux kill-session -t whatsapp-channel
```

Channel sessions will respawn at the reverted code via watchdog.

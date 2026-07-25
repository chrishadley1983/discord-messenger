# 2026-07-21 — Docker Desktop down + #food-log messages silently lost

## Summary

Two separate problems surfaced this morning:

1. **Docker Desktop itself had fully exited** (not just a container), which broke WhatsApp for ~90 min and caused the watchdog to spam "docker restart failed" alerts it could never actually fix. **Fixed** — see below.
2. **peter-channel is dropping #food-log messages** — Chris logged water three times this morning (08:29, 10:29 ×2) and none of it reached the nutrition backend. **Root cause CONFIRMED**: every single restart today (5 of 5) was caused by the shared WSL Claude OAuth token being rejected as revoked/invalid the instant a message arrived, killing the whole peter-channel process before any tool call could run. See "Update" in Issue 2 below — this supersedes the original "leading hypothesis" (crash/hang during message processing), which the direct session-transcript evidence ruled out.

---

## Issue 1: Docker Desktop down (RESOLVED)

**Symptom:** Discord alerts from ~09:05–10:30 UK:
- "WhatsApp watchdog: docker restart failed (state was unreachable, err request_error:ConnectError)" — repeated hourly
- WhatsApp send failures ("Evolution API instance is not in 'open' state")

**Root cause:** Docker Desktop had exited completely — no `Docker Desktop.exe` / `com.docker.backend` process running at all. `domains/whatsapp_watchdog.py` only ever runs `docker restart evolution_api`, which always fails with a connect error when the whole engine is down. There's no daemon to restart into, so every watchdog cycle failed identically for ~90 minutes.

**Fix applied (manual, this session):**
1. Started `Docker Desktop.exe`, waited for the daemon (`docker info` succeeded after ~30s).
2. `evolution_postgres` came up healthy on its own.
3. `evolution_api` had exited (code 127) because it started before postgres was ready — waited for postgres `healthy` status, then `docker start evolution_api`.
4. Confirmed via `curl localhost:8085/instance/connectionState/peter-whatsapp` → `state: "open"`.

Both containers have `restart: unless-stopped`, so once the engine was back, they would likely have self-healed within a couple of minutes via Docker's own restart backoff anyway — the manual `docker start` just sped it up.

**Code fix (applied, not yet tested live):** Added Docker-daemon detection to `domains/whatsapp_watchdog.py`:
- New `_docker_daemon_up()` check (`docker info`) runs before attempting a container restart.
- If the daemon itself is down, `_launch_docker_desktop()` relaunches `Docker Desktop.exe` (throttled to 1 launch per 5 min) instead of endlessly retrying `docker restart` against a dead engine.
- Alerts now distinguish "Docker Desktop was down, relaunched it" from the existing "container restart failed" case.

**Open gap:** nothing currently detects *why* Docker Desktop exited in the first place — if it's a recurring pattern (e.g. tied to the recent Windows Update corruption incidents), it'll keep happening. Worth a periodic check if it recurs.

---

## Issue 2: #food-log messages silently lost (UNRESOLVED)

**Symptom:** Chris posted three manual nutrition logs in #food-log today and none were logged or acknowledged:

| Time (BST) | Message | Result |
|---|---|---|
| 08:29 | "Flat white and 500ml water" | Nothing logged, no reply |
| 10:29 | "1l water" ×2 | Nothing logged, no reply |
| 10:45 | "1l water" (resent at Chris's request, to test) | Registered as received (`messages_in` went 0→1) but still nothing logged |

**Verified independently:**
- `/nutrition/today/meals` shows exactly one meal today: "Simmer Spiced Chicken Breakfast Bowl #22", logged **06:37 UTC** — i.e. *before* the 08:29 message, and unrelated to it (a flat white would be ~100 kcal, not the 478 kcal / 46.4g protein logged). Initial assumption that this entry came from the flat white message was **wrong** — Chris caught this. The 08:29 message produced zero backend activity, same as the water-only messages.
- `/nutrition/water/entries` shows 0 entries logged all day.
- The `/nutrition/log-water` API endpoint itself works correctly — round-tripped a test 1ml entry through it and deleted it again to confirm, so this is not a backend bug.
- **peter-channel has been killed and relaunched at least 4 times today**, per `/tmp/peter-channel-restarts.log` (inside WSL):
  ```
  [Tue Jul 21 08:30:16 BST 2026] START attempt=1
  [Tue Jul 21 10:30:13 BST 2026] START attempt=1
  [Tue Jul 21 10:37:13 BST 2026] START attempt=1
  [Tue Jul 21 10:46:14 BST 2026] START attempt=1
  ```
  Every single restart lands within ~1 minute of one of Chris's messages above (08:29→08:30:16, 10:29→~10:37, 10:45:49→10:46:14). Each restart is a brand-new tmux session + fresh `claude` process (not an internal retry loop — `attempt=1` every time), meaning something *external* to the session is killing it (`tmux kill-session` + `tmux new-session`), consistent with bot.py's `_launch_channel_sessions()` recycle path or the auth watchdog's restart path — not a crash inside the Claude process itself continuing its own retry loop.
- **Ruled out as the cause of the most recent restarts:** WSL Claude OAuth. At the time of the 10:46 restart, both the WSL and Windows credential files were healthy (WSL: 64 min until expiry, refresh token present; Windows: 318 min). No `401`/`Please run /login` markers in any channel's tmux pane. So `channel_auth_watchdog` healing an expired token does **not** explain this restart, even though it *did* explain the earlier 10:30 one (matches the Discord alert "Auto-healed WSL Claude auth. restarted peter-channel").
- **Ruled out:** `scheduler.py`'s reactive `force_restart_channel()` (fires when a scheduled job gets an empty response twice) — that path only ever targets `jobs-channel` / `jobs-channel-sonnet`, never `peter-channel`, since scheduled skill output (including hydration check-ins) is routed through jobs-channel, not peter-channel.

**Leading hypothesis (unconfirmed):** peter-channel's own HTTP health port is dying shortly after it starts processing an inbound #food-log message (crash, hang, or exception inside the MCP/Claude Code process), and bot.py's plain 1-minute HTTP-health channel watchdog (`_launch_channel_sessions`, not the auth watchdog) is then recycling it — killing the in-progress turn before it can run any of the logging curl commands or reply. This would explain both the message loss (turn never completes) and the tight timing (health dies mid-message → next 1-min watchdog tick recycles it).

**Not yet confirmed because:**
- `bot.py`'s own log file (`logs/discord_bot.log`) hasn't been written to since 09:57 today, well before any of these restarts, so the actual watchdog log lines that would show *which* function triggered each kill aren't available through that file. NSSM likely captures bot.py's stdout/stderr elsewhere (not yet located) — checking that log is the next step to get a definitive trigger.
- Haven't yet found a stack trace / crash reason from inside the Claude Code process itself for why its HTTP port would go down mid-turn.

## Update — root cause confirmed: recurring OAuth 401, not a crash/hang

Read the Claude Code session transcripts directly (`~/.claude/projects/-home-chris-hadley-peterbot/*.jsonl` in WSL) for the sessions that ended at each of today's five restarts (08:30, 09:38 — an extra retry not previously listed, 10:30, 10:37, 10:46). **Every single one** shows the identical pattern as its last turn:

```
ASSISTANT TEXT: Please run /login · API Error: 401 OAuth access token has been revoked.
```

(the 10:46 one reads "401 Invalid authentication credentials" — same family of error, different wording). In each case the message was received (visible as the `<channel source="peter-channel" ...>` user turn) and the very next model turn is the bare 401 error — no tool calls, no reply, nothing. This is not the crash/hang theorised earlier; the whole peter-channel process (Discord gateway + HTTP health server) goes down because the underlying `claude` CLI process dies on the spot when its OAuth token is rejected, and `channel_auth.py`'s 1-minute watchdog then kills+relaunches the tmux session — losing whatever arrived in that window.

This **corrects** the earlier "ruled out: WSL Claude OAuth" note for the 10:37/10:46 restarts. That check read the credential files fresh at the time of investigation, by which point `heal_channel_auth()` had already re-synced them — so the files looked healthy in hindsight even though the token in use at the moment of the crash was not. Checking file state after the auto-heal masked the very thing that caused the crash.

**Confirmed NOT the classic "two sessions raced and blanked the refresh token" bug**: peter-channel's `claude` process was directly verified (via `/proc/<pid>/environ`) to be running with `CLAUDE_CODE_OAUTH_TOKEN` set — the static, non-rotating token fix from the 2026-06-20 incident is live and taking effect. Yet it was still rejected as revoked, five separate times in ~80 minutes. That's a materially higher frequency than the rare refresh race the static token was built to eliminate, so something is actively invalidating that long-lived token this morning — cause not yet identified (candidates: a fresh interactive `/login` elsewhere invalidating it, or a concurrent-session/device limit on the account being hit given ~5 WSL channels + Windows + other Claude Code usage all sharing one login). **Confirmed by Chris**: he had to log in interactively in a separate Claude Code session this morning to restore Fable model availability. That login is what revoked the shared `CLAUDE_CODE_OAUTH_TOKEN` grant — Anthropic's auth server invalidates the previously-active OAuth grant on a fresh interactive login under the same account, which is exactly the "revoked" (not "expired") wording seen in every crash transcript. The static-token fix eliminates the *multi-WSL-session* refresh race it was built for, but has no defense against Chris re-authenticating elsewhere for an unrelated reason (Fable access) — any such login will 401 every WSL channel until the watchdog heals it, silently dropping whatever arrives in that ~1 minute window.

## Resolution (2026-07-21 ~11:05 BST)

**Why it crash-looped instead of healing:** every channel's `launch.sh` sources `scripts/claude-oauth-env.sh`, which exports `CLAUDE_CODE_OAUTH_TOKEN` from `C:\Users\Chris Hadley\.claude-code-oauth-token`. While that env var is set, Claude Code ignores `.credentials.json` entirely. So the auth watchdog's heal (re-sync credentials.json from Windows + restart session) restarted sessions that immediately re-sourced the *same revoked static token* — 6 crash-loops in ~90 min, with every #food-log message in a crash window silently lost.

**Fix applied:**
1. Quarantined the revoked token → `.claude-code-oauth-token.revoked-2026-07-21`. `claude-oauth-env.sh` is a no-op when the file is absent, so sessions fall back to `.credentials.json`.
2. Synced fresh Windows credentials (from Chris's Fable re-login, ~8h validity) into WSL.
3. Restarted all 5 channel sessions; verified via `/proc/<pid>/environ` that none carry `CLAUDE_CODE_OAUTH_TOKEN`, and all 3 HTTP health ports report ok.
4. **Watchdog hardened** (`domains/peterbot/channel_auth.py`): `heal_channel_auth()` now detects the "sessions 401 while the static token file is present" state, auto-quarantines the token file (timestamped rename) before restarting sessions, and alerts Discord — including telling Chris to resend recent messages and how to mint a replacement token. DiscordBot service restarted to load this.
5. Nutrition data corrected directly via API: water set to exactly 1,000ml (one water entry), flat white logged (120 kcal / 6g protein, whole-milk estimate).

**Trade-off now live:** channels are back on the shared rotating `.credentials.json`, which re-exposes the multi-session refresh race from the 2026-06-20 incident (the watchdog heals that automatically, but with a ~1-min message-loss window). To restore static-token protection: run `claude setup-token` on Windows (interactive), then `scripts/set-claude-oauth-token.sh <token>`. Note: any future interactive `/login` on the account will revoke that token again — but now the watchdog degrades gracefully instead of crash-looping.

## Remaining structural gap
Inbound Discord/WhatsApp messages that arrive while a channel session is dead or mid-restart are lost with no trace and no user-facing error. The new quarantine alert mitigates (tells Chris to resend) but a proper queue/replay across channel restarts would eliminate the loss entirely.

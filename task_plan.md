# Task Plan — Channel Pipeline Parity

Branch: `feature/channel-pipeline-parity`
Created: 2026-05-21

## Problem

When `PETERBOT_USE_CHANNEL=1` / `WHATSAPP_USE_CHANNEL=1` (the primary path since Mar 2026), `bot.py:797` returns immediately and `hadley_api/whatsapp_webhook.py:99-102` forwards to port 8102. Both bypass `router_v2.handle_message`, silently dropping every feature added to v2 after the channel cutover.

| Feature | v2 | peter-channel | whatsapp-channel | jobs-channel | Severity |
|---|---|---|---|---|---|
| Second Brain surfacing (`get_context_for_message`) | yes | NO | NO | NO | HIGH |
| Provider fallback Claude->cc2->Kimi | yes | NO | NO | partial | HIGH |
| Japan trip context | yes | NO | NO | NO | HIGH during trip |
| WhatsApp pending actions block | yes | n/a | NO | n/a | HIGH |
| Cost logging to `cli_costs.jsonl` | yes | NO | NO | partial | MEDIUM |
| Attachment download to local tmp | yes | NO (URL only) | NO | n/a | MEDIUM |
| Voice transcription prepended | yes | n/a | NO | n/a | MEDIUM |
| Channel isolation header | yes | partial | partial | yes | LOW |
| Current UK time in context | yes | NO | NO | yes | LOW |
| Buffer restore on restart | yes | uses last-6 fetch | NO | n/a | LOW |
| Windows media-path scrubber | NO | yes | NO | NO | reverse drift |
| Document auto-save | yes | yes | yes | n/a | already wired via /response/capture |

## Solution shape

Extract v2's `handle_message` context-build into a shared HTTP endpoint on Hadley API. Channels call it before pushing the MCP notification. Channels stay as dumb pipes; the pipeline becomes the single source of truth.

## Phases

### Phase 1 — Shared context (HIGH impact, LOW risk)

- **F1** — `POST /peter/build-context` on Hadley API. Lifts `memory.build_full_context` + the surfacing call from `router_v2.py:917-932` into one endpoint. Files: `hadley_api/peter_routes/build_context.py` (new).
- **F2** — `peter-channel/src/index.ts` calls the endpoint before MCP notification at ~line 374. Falls back to raw content on fetch failure.
- **F3** — `whatsapp-channel/src/index.ts` calls the endpoint at ~line 294. Passes `sender_number` for pending-actions.
- **F4** — `scheduler.py:_build_skill_context` calls the endpoint when SKILL.md frontmatter has `metadata.surface_knowledge: true`. Default off so fixed-data skills don't pay the cost.

### Phase 2 — Lifecycle parity (MEDIUM impact)

- **F5** — `POST /response/cost`. Channel reply tools post `{source, channel, duration_ms, response_chars}` to keep `cli_costs.jsonl` populated.
- **F6** — `POST /attachment/download`. Mirrors `router_v2._download_attachments`; `peter-channel` calls it for image/audio attachments before MCP push.
- **F7** — Port `peter-channel`'s `WINDOWS_MEDIA_PATH_RE` scrubber into `memory.build_full_context` so v2 fallback also protected.

### Phase 3 — Robustness

- **F8** — Smart fallback. `bot.py:796` and `hadley_api/whatsapp_webhook.py:101` probe channel `/health` (5s cache). If unhealthy, fall through to `router_v2.handle_message`. Currently when `USE_CHANNEL=1` and channel is down, messages are silently dropped.

True provider fallback to cc2/Kimi inside a running channel session is deferred — requires killing and respawning the WSL tmux session with new env vars.

### Phase 4 — Verification and docs

- **F9** — `npx tsc --noEmit` on both channels. No deploy from this branch — channels are NSSM/tmux-managed and Chris restarts them.
- **F10** — Update `hadley_api/README.md` with new endpoints. Add a section to project `CLAUDE.md` documenting the channel context-build flow.

## Smoke tests

After F1, against the running Hadley API:

```bash
curl -s -X POST http://localhost:8100/peter/build-context \
  -H "Content-Type: application/json" \
  -d '{"message":"what is family fuel","channel_id":1234,"channel_name":"#peterbot"}' | jq .
```

WhatsApp variant:
```bash
curl -s -X POST http://localhost:8100/peter/build-context \
  -H "Content-Type: application/json" \
  -d '{"message":"is plan still A","channel_name":"WhatsApp","sender_number":"447855620978","is_whatsapp":true}' | jq .
```

## Deploy steps (not executed from this branch — Chris's call)

1. Merge to main
2. NSSM restart HadleyAPI
3. WSL tmux: `tmux kill-session -t peter-channel`, `-t whatsapp-channel`; watchdog respawns with new TS
4. Verify channel `/health` and round-trip a message; expect surfacing block visible in `/tmp/peter-channel-app.log`

## Out of scope (follow-ups)

- True provider fallback within a running channel session (Claude credits exhausted mid-turn)
- Per-token cost capture from Claude Code MCP result events
- Voice transcription for incoming WhatsApp voice notes via channel path
- Buffer-restore parity for channels (current last-6 Discord fetch works but differently)

## Error log

(Track errors encountered during implementation)

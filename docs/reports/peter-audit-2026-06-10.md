# Peter Functionality Audit — 10 June 2026

## Scope & evidence base

Audited: scheduled jobs (`SCHEDULE.md` + live `/jobs/health`), skills (`wsl_config/skills/` + `manifest.json`), channels (peter/whatsapp/jobs), Hadley API surface (`hadley_api/README.md` + `peter_routes/`), MCP servers, Second Brain seed adapters, watchdogs, dashboard live status, and 14-day cost data (`data/cli_costs.jsonl`).

### Inventory snapshot

| Area | Count | Notes |
|------|-------|-------|
| Scheduled jobs | 62 cron + 1 interval (spurs-live 10m) | 1 disabled (daily-instagram-prep) |
| Skill directories | 117 | incl. `_template` |
| Manifest entries | 103 | 87 conversational, 16 scheduled-only |
| Channels | 3 primary (peter :8104, whatsapp :8102, jobs :8103) | + router_v2 fallback |
| Hadley API | ~30 endpoint groups | Gmail, Calendar, HB, nutrition, fitness, life-admin, browser, voice… |
| MCP servers | 3 (second_brain, financial_data, keepa) | + external: supabase, searxng, brave, context7, gmail |
| Second Brain adapters | 22 | email, calendar, GitHub, Garmin, Withings, Spotify, Reddit, Netflix… |

### Live health (at audit time)

- All services up: Hadley API, Dashboard, Discord bot, all 3 channels, Second Brain.
- Job success 99.7% over 48h (1,023/1,026 DM; 200/200 HB).
- Recurring failures: `incremental_seed` (Reddit cookie expired — failing nightly), `paper-builder` (one "empty response").
- HadleyBricks process reports **orphaned** (port 3000 up, but no tracked PID — running `next dev` under NSSM because the production build has a TypeScript error).
- Extra tmux sessions running: `extract-channel`, `jobs-channel-sonnet` (untracked experiments, node_modules in git status).
- 14-day LLM spend: **$25.39**, of which **hydration alone is $8.73 (34%, 188 calls)**.

---

## 1) Areas of improvement in current functionality

### 1.1 Skill registry drift (highest priority — silent capability loss)
The manifest, skills directory, and schedule have diverged three ways:

- **20 skill dirs missing from `manifest.json`** — since Peter discovers conversational skills via the manifest, these are invisible in chat: `brickstop-traffic`, `directions`, `drive-search`, `email-search`, `email-summary`, `ev-charging`, `find-free-time`, `notion-ideas`, `notion-todos`, `ring-status`, `schedule-today`, `schedule-week`, `traffic-check`, `trip-prep`, `tutor-email-parser`, `vinted-collections`, `weather`, `weather-forecast`, `whatsapp-keepalive`. Notably **`drive-search` is referenced in Peter's critical rules** (Google Drive path handling) yet isn't in the manifest.
- **1 broken manifest entry**: `whatsapp-health` has no skill directory (the real skill is `whatsapp-keepalive`).
- **4 manifest "scheduled-only" skills are not in SCHEDULE.md** (never run): `daily-thoughts`, `parser-improve`, `osaka-mint-check`, plus the broken `whatsapp-health`.

**Fix**: auto-generate `manifest.json` from SKILL.md frontmatter (single source of truth) and add a nightly consistency check to the system-health skill (dir ⊆ manifest, schedule refs exist).

### 1.2 Hydration job is 34% of all LLM spend
15 LLM invocations/day to say "drink water" ($8.73/14d). The message is near-fixed-format; it doesn't need a Claude turn. Replace with a templated direct webhook/HTTP post (zero LLM), or run one LLM call each morning that generates the day's 15 messages. Same logic applies to `cooking-reminder` (2×/day) and other fixed-format nudges. Estimated saving: ~40% of total spend.

### 1.3 Known failures left to recur
- `incremental_seed` fails **every night** on the Reddit cookie. The adapter should degrade to "skipped (auth needed)" rather than marking the whole job failed, and a one-time actionable alert ("log into Reddit in Chrome-Vinted") should fire instead of nightly noise. Alert fatigue is how real failures get missed.
- `paper-builder` empty response (Tue 19:30) — needs a retry-once-then-alert wrapper.

### 1.4 HadleyBricks runs dev-mode under NSSM
Production build is blocked by a TypeScript error in the amazon backfill route; the service runs `next dev` with an orphaned PID. Fix the TS error, ship a production build, and give the service a real `/api/health` endpoint (dashboard currently uses `http_any`).

### 1.5 Load-bearing code not committed
`domains/scheduler_watchdog.py` and `domains/whatsapp_watchdog.py` are **imported by bot.py at startup but untracked in git**. A clone or `git clean` breaks bot startup. Also uncommitted: `business_finance.py` changes, `auto-accept-prompts.sh`, the vercel-usage skill, `docs/merges/`. Commit or discard — the repo should always be runnable from HEAD.

### 1.6 Morning message flood
Between 06:30 and 09:35 roughly **18 scheduled messages** land across channels (laughs, quality report, system health, briefing, news, kids, cooking, health digest, fitness dashboard, school run, GitHub, email, schedule, Notion, prescriptions, HB sync, hydration ×3…). Engagement likely varies hugely. Consolidate related jobs into fewer composite digests (see Extension #1) and let reactions drive what stays standalone.

### 1.7 No off-machine dead-man's switch
All monitoring (heartbeat, watchdogs, system-health) runs on the same PC it monitors. If the machine dies or loses power, nothing alerts. Add an external dead-man's switch: heartbeat pings healthchecks.io (free) which emails/notifies when pings stop.

### 1.8 Parser regression safety net
History shows repeated parser bugs (leakage, stale extraction, wrapped lines). The capture store exists (`ParserCaptureStore`), but there's no fixture-based regression test suite over captured screens. A small pytest corpus would prevent re-breakage — especially relevant while router_v2 remains the fallback.

---

## 2) Areas for potential deprecation

| Candidate | Rationale | Suggested action |
|-----------|-----------|------------------|
| **Legacy `jobs/*.py`** | Already marked DO-NOT-USE; causes conflicts | Delete outright |
| **router_v2 + tmux parser machinery** | Channels primary since Mar 2026; watchdogs now auto-relaunch dead sessions; smart fallback rarely fires | Keep 1 more month, instrument fallback activations, then remove parser/screen-scrape path (big code deletion: parser.py boundaries, capture store, SEARCH_NOISE_PATTERNS) |
| **`parser-improve`, `morning-quality-report`, `orphan-embed` nightly parser review** | Exists to babysit the tmux parser — purpose disappears with router_v2 | Retire alongside router_v2 |
| **`whatsapp-keepalive` scheduled skill (08:00/20:00)** | Superseded by the new 2-min `whatsapp_watchdog` which probes *and* auto-restarts | Remove from SCHEDULE.md once watchdog is committed and proven |
| **`whatsapp-health` manifest entry** | Broken reference, no skill dir | Delete from manifest |
| **`osaka-mint-check`, `trip-prep`** | Japan-trip-specific; trip window will pass | Archive after the trip |
| **Duplicate/overlapping skills**: `weather` vs `weather-forecast`; `traffic-check` vs `directions` vs `brickstop-traffic` | Three traffic skills and two weather skills, none in the manifest | Merge to one each, register properly |
| **`daily-instagram-prep`** | Disabled in schedule; Instagram pipeline lives in the separate instagram-automation project | Remove job + skill, or re-enable deliberately |
| **`spotify.py` live adapter** | Superseded by `spotify_export.py` full-history import (in progress) | Retire once export import lands |
| **`extract-channel` / `jobs-channel-sonnet` tmux sessions + dirs, `_diag_whatsapp*.ps1`, `_prolific-relogin.ps1`** | Untracked experiments running on the box, consuming a Claude session slot | Promote to real components or kill the sessions and delete |
| **brave-search MCP** | SearXNG covers web search locally on both Windows and WSL | Drop one to reduce config surface |

---

## 3) Ten potential extensions (last 5 = blue sky)

### Grounded

1. **Adaptive unified morning digest** — Replace the ~18-message morning flood with one composed briefing (sections: news, schedule, email, kids, health, HB) built by a single jobs-channel turn. Track Discord reactions/replies per section; sections nobody reads get demoted to weekly. Cuts cost, noise, and makes the briefing feel curated rather than firehosed.

2. **Two-way voice on WhatsApp** — Incoming voice notes are already transcribed (faster-whisper). Add the return path: Kokoro TTS (already in peter-voice) renders Peter's reply as a voice note via Evolution API's audio send. Peter becomes fully usable hands-free from a phone — school run, kitchen, car.

3. **Inbox autopilot** — Extend email-summary/life-admin-email-scan from *reporting* to *acting*: draft replies for approval, auto-file receipts to Second Brain, detect & queue unsubscribes, extract attachments to Drive. Daily "inbox zero" report with one-tap approvals via Discord buttons.

4. **Hadley Bricks listing autopilot** — Chain existing pieces (review-queue set identification → Keepa/Amazon pricing → arbitrage eval) into a full pipeline: photo in, draft eBay/Amazon listing out, Instagram post queued, plus a weekly repricing loop on stale inventory (`hb-inventory-aging` already knows what's stale). Human approval gates at listing publish.

5. **Self-optimizing scheduler** — A weekly governance-gated job where Peter analyses `job_history.db` + engagement + cost per job and *proposes* schedule diffs ("hydration → template, cricket-scores → only on match days, move 4 jobs out of the 07:00–08:00 spike"). Chris approves with a 👍; Peter applies via the existing `PUT /schedule` API. Peter starts maintaining himself.

### Blue sky (c5)

6. **Peter as multi-day project orchestrator** — Upgrade jobs-channel into an agent-swarm conductor: Chris says "research and book the best Japan rail option" or "rebuild the dashboard in Next.js" and Peter decomposes it, spawns worker sessions/workflows, persists state across days in Second Brain, and reports progress in a dedicated Discord thread until done. From assistant to chief of staff.

7. **Autonomous purchasing agent** — Vinted sniper + `hb-eval-purchase` + a hard budget guard become a closed loop: Peter watches listings 24/7, auto-buys LEGO deals inside pre-approved rules (margin ≥X%, price ≤£Y, weekly cap £Z), arranges Vinted messages/pickups, and posts a daily P&L. The business acquires stock while Chris sleeps.

8. **Life memory graph** — Evolve Second Brain from flat pgvector into an entity-temporal graph (people, places, projects, commitments, linked over time). Unlocks queries embeddings can't do: "what was stressing me last March?", "how did the cut progress vs plan?", an auto-generated annual "year in review" for the family, and genuinely longitudinal coaching from the accountability skills.

9. **Ambient household Peter** — Voice satellites (Pi + mic + wake word, reusing the Moonshine/Kokoro stack) in kitchen and office, presence-aware via phones/Ring, wired into energy/EV/heating data Peter already ingests. Peter speaks up contextually: "leave in 6 minutes for pickup, traffic's bad", "EV's at 80%, cheap rate ends in 20 minutes" — no screen, no prompt.

10. **Self-extending Peter** — A meta-skill: Peter notices when Chris asks for the same un-skilled thing repeatedly, drafts the SKILL.md + data fetcher + schedule entry himself, tests it in a sandbox session, and submits a PR-style proposal through the governance gate. The skill library grows from observed need rather than manual development — Peter writes Peter.

---

## Implementation status (same day, 2026-06-10)

All improvement areas and deprecations were implemented, verified by a 10-agent
workflow (2 blockers found and fixed), and deployed (DiscordBot restarted, 60
jobs loaded, HadleyBricks on a production build).

| Item | Status |
|------|--------|
| 1.1 Manifest drift | ✅ `skill_manifest.py` generator (SKILL.md source of truth), wired into `load_schedule()` + system-health drift check; 118 skills |
| 1.2 Hydration cost | ✅ `daily-batch` skill (06:55) + `__direct__` scheduler posts — 17 LLM calls/day → 1 |
| 1.3 Recurring failures | ✅ Auth failures degrade to 24h-throttled reminder (narrow hint matching); empty responses retry once (channel paths) |
| 1.4 HadleyBricks dev-mode | ✅ TS errors fixed (unified-markdown WIP fields optional), production build live, dashboard service config fixed |
| 1.5 Uncommitted code | ✅ All committed; `.cache` (live Spotify token!) untracked + gitignored — **rotate Spotify app credentials** (token remains in git history) |
| 1.6 Morning flood | ✅ 3 themed digests (Morning 07:00, Family/kids 07:25, Health 07:55); time-critical jobs stay separate |
| 1.7 Dead-man's switch | ✅ healthchecks.io check `peter-pc-deadman`, bot pings every 5 min (verified live), email alert if silent ~20 min |
| 1.8 Parser regression tests | ⏸️ Deferred — router_v2 instrumented instead; parser machinery is deprecation-bound |
| Legacy jobs/*.py | ✅ Dead else-branch + 4 unused modules deleted; remaining modules are fetcher libraries/infra |
| router_v2 | ✅ Instrument-only (per decision): activations → `data/fallback_events.jsonl` + throttled #alerts |
| whatsapp-keepalive | ✅ Removed; superseded by 2-min auto-restart watchdog (verified all paths incl. 401 handling) |
| daily-instagram-prep | ✅ Removed (job + skill + dangling fetcher entry) |
| weather/traffic dupes | ✅ Merged (weather+forecast, directions+traffic); brickstop-traffic deleted |
| extract-channel / jobs-channel-sonnet | ⚠️ **Audit was wrong — these are production** (Sonnet/Haiku job routing :8105, extraction :8106). Kept; node_modules symlinks gitignored |
| brave-search MCP | ✅ Removed from WSL config (backup kept); news + life-admin-compare skills point at SearXNG |
| osaka-mint-check / trip-prep / spotify adapter | ⏸️ Deferred until after the Japan trip / Spotify export import |

**Outstanding for Chris**: (1) WhatsApp linked device was revoked (401) — re-pair
via QR (watchdog alerted, won't restart-loop).

Resolved since: (2) Reddit re-login done 10 Jun evening — adapter validate()
passes (root cause of repeated CDP weirdness was a leaked headless Chrome from
14 May holding the Chrome-SeedImport profile; killed). (3) Spotify rotation —
accepted risk: leaked `.cache` held only the refresh token, unusable without
the client secret which never leaked. (4) Notion todos — digest now reads
ptasks `personal_todo` instead; Notion remains unconfigured by choice.

## Suggested immediate actions (this week)

1. Commit the two watchdog files (bot.py depends on them at startup).
2. Fix the Reddit cookie (one login in Chrome-Vinted) and make the adapter degrade gracefully.
3. Regenerate/repair `manifest.json` (add the 20 missing skills, drop `whatsapp-health`).
4. Convert hydration to template delivery — single biggest cost win.
5. Decide fate of `extract-channel` / `jobs-channel-sonnet` experiments.

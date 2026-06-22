export const meta = {
  name: 'verify-live-resilience',
  description: 'Robust live canary for the morning-jobs subsystem: probes the RUNNING system (channels, scheduler, flight + vercel scrapers) with retries so transient blips do not false-alarm, then PROVES self-heal actually works on the live system via a safe induced recovery, then adversarially re-checks and synthesizes PASS/FAIL. Safe to run anytime / on a schedule.',
  phases: [
    { title: 'Probe live', detail: 'retry-wrapped liveness probes of channels, scheduler, flight & vercel' },
    { title: 'Prove resilience', detail: 'exercise a real self-heal on the live system + verify watchdog is running' },
    { title: 'Synthesize', detail: 'combine into a robust PASS/FAIL verdict' },
  ],
}

const DM = '/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger'
const HB = '/mnt/c/Users/Chris Hadley/claude-projects/hadley-bricks-inventory-management'
const DMW = 'C:/Users/Chris Hadley/claude-projects/discord-messenger'
const HBW = 'C:/Users/Chris Hadley/claude-projects/hadley-bricks-inventory-management'

const HINT = [
  'Environment: Windows with a Bash tool; Peter channels run in WSL, schedulers + scrapers in Python/Node on Windows.',
  'VANTAGE POINT (critical): run ALL curl / health / CDP probes from the Windows Bash tool DIRECTLY — no `wsl` prefix. Windows localhost reaches BOTH the WSL channel HTTP ports (8102/8103/8104/8105, via WSL2 localhost forwarding) AND the Windows-bound CDP Chrome on :9222 (which is NOT reachable from inside WSL).',
  'Do NOT wrap probes in `wsl -d Ubuntu -- bash -lc \'...$var...\'`: Git-Bash mangles $-variables before they reach WSL, so loops silently return empty (http_code 000) and can false-FAIL. Use `wsl` ONLY for genuinely WSL-only things (tmux), and prefer `python -m domains.peterbot.channel_auth` (run from Windows) which does the tmux 401 scan internally with no mangling.',
  'Run Python in a repo via the Bash tool: `cd "<WINDOWS_PATH>" && python ...`. Strip Chrome DEP0169 deprecation lines from any output you parse.',
  'ROBUSTNESS RULE: every live probe is allowed to be FLAKY. Retry each failing probe up to 3 times with a short pause before concluding it failed. Only report FAIL if it fails on all attempts. Note in evidence how many attempts it took.',
].join('\n')

const CHECK = {
  type: 'object',
  properties: {
    subsystem: { type: 'string' },
    status: { type: 'string', enum: ['PASS', 'FAIL', 'WARN'] },
    attempts_needed: { type: 'number' },
    evidence: { type: 'string' },
    notes: { type: 'string' },
  },
  required: ['subsystem', 'status', 'evidence'],
}

const VERDICT = {
  type: 'object',
  properties: {
    claim: { type: 'string' },
    refuted: { type: 'boolean' },
    confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
    method: { type: 'string' },
    evidence: { type: 'string' },
  },
  required: ['claim', 'refuted', 'confidence', 'evidence'],
}

phase('Probe live')
const probes = (await parallel([
  // Channels: live end-to-end auth on both jobs channels + gateway health
  () => agent(
    `LIVE channel liveness probe (running system only — do not read source). Run everything from the WINDOWS Bash tool (no wsl wrapper).\n\n${HINT}\n\nProbe and report:\n1. End-to-end auth on BOTH jobs channels — POST a trivial job and expect AUTH_OK in the JSON response (retry up to 3x each):\n     curl -s --max-time 30 -X POST http://localhost:8103/job -H "Content-Type: application/json" --data-raw '{"skill":"auth-test","context":"Reply with exactly AUTH_OK and nothing else."}'\n     curl -s --max-time 30 -X POST http://localhost:8105/job -H "Content-Type: application/json" --data-raw '{"skill":"auth-test","context":"Reply with exactly AUTH_OK and nothing else."}'\n   Both responses must contain AUTH_OK.\n2. Gateway/health of every channel (each its own curl — no shell loop):\n     curl -s --max-time 8 http://localhost:8104/health ; echo\n     curl -s --max-time 8 http://localhost:8102/health ; echo\n     curl -s --max-time 8 http://localhost:8103/health ; echo\n   All must report status ok.\n3. Lockout + creds scan via the bot's own watchdog status (does the tmux 401 scan internally — no mangling):\n     cd "${DMW}" && python -m domains.peterbot.channel_auth\n   Expect "Sessions 401 : none" and WSL creds readable/has_refresh/not corrupt.\nPASS iff both channels return AUTH_OK, all three health endpoints are ok, and the status shows no 401 sessions. Set attempts_needed to the max retries any single probe needed.`,
    { label: 'probe:channels', phase: 'Probe live', schema: CHECK }
  ),
  // Scheduler: alive + NO active wedge (no recent empty-response failures)
  () => agent(
    `LIVE scheduler liveness probe via the job-history DB (running system only).\n\n${HINT}\n\nThe DB is at ${DMW}/peter_dashboard/job_history.db (table job_executions; cols started_at, job_id, status, duration_ms, error_message). Run with the Bash tool:\n  cd "${DMW}" && python -c "import sqlite3,datetime;c=sqlite3.connect('peter_dashboard/job_history.db');c.row_factory=sqlite3.Row;cut=(datetime.datetime.now()-datetime.timedelta(minutes=20)).isoformat();rows=c.execute('SELECT started_at,job_id,status,error_message FROM job_executions WHERE started_at>=? ORDER BY started_at',(cut,)).fetchall();succ=sum(1 for r in rows if r['status']=='success');empty=[r['job_id'] for r in rows if (r['error_message'] or '')=='empty response'];print('rows_20min',len(rows),'success',succ,'empty_response',empty)"\nPASS iff there is at least 1 success in the last 20 min (proves the scheduler is ticking — channel_cost_tail runs every 5 min) AND there are ZERO 'empty response' failures (an active wedge would show these). If 0 rows at all, retry once after ~60s (a quiet window is possible) then WARN, not FAIL. Put the printed counts in evidence.`,
    { label: 'probe:scheduler', phase: 'Probe live', schema: CHECK }
  ),
  // Flight: live scrape really returns scrape-sourced fares
  () => agent(
    `LIVE flight-scrape probe (run it for real).\n\n${HINT}\n\nRun (retry up to 3x — Google Flights can be flaky):\n  cd "${DMW}" && python -c "import asyncio,json; from services.flight_prices import run_daily_watches; o=asyncio.run(run_daily_watches()); print(json.dumps({'scrape_ok':o.get('scrape_ok'),'fallback_used':o.get('fallback_used'),'sources':[w.get('source') for w in o.get('watches',[])],'pps':[(w.get('best') or {}).get('price_pp') for w in o.get('watches',[])]}))"\nPASS iff scrape_ok=true, fallback_used=false, and every source=='scrape'. If it falls back to serpapi on all attempts, that's a FAIL (the scrape is degraded). Report the JSON + attempts_needed.`,
    { label: 'probe:flight', phase: 'Probe live', schema: CHECK }
  ),
  // Vercel: live scrape returns metrics (no false 'session expired')
  () => agent(
    `LIVE vercel-scrape probe (run the scrape function, no upsert needed).\n\n${HINT}\n\nRun (retry up to 3x):\n  cd "${HBW}" && python -c "import importlib.util as u; s=u.spec_from_file_location('vu','scripts/vercel-usage-scraper.py'); m=u.module_from_spec(s); s.loader.exec_module(m); r,st=m.scrape_vercel_usage(); print('status',st,'metrics',len(r))"\nPASS iff status==ok and metrics>=10. If status==login_required on all attempts, that's a real expiry -> FAIL with a note that scripts/login_vercel.py is needed. Any other 0-metric status -> retry, then WARN. Report status + metric count + attempts_needed.`,
    { label: 'probe:vercel', phase: 'Probe live', schema: CHECK }
  ),
])).filter(Boolean)

phase('Prove resilience')
const resilience = (await parallel([
  // REAL induced recovery (safe): leak a flights tab, run scraper, confirm it self-cleans on the LIVE Chrome.
  () => agent(
    `Prove the flight scraper's tab-leak SELF-HEAL works on the LIVE shared CDP Chrome (:9222) — a real induced-recovery test, SAFE (opens one throwaway tab and expects the scraper to close it; never kills Chrome or touches Vinted tabs). The CDP is Windows-bound, so run EVERYTHING from the Windows Bash tool (no wsl).\n\n${HINT}\n\nSteps:\n1. Open a throwaway Google Flights tab via CDP and count flights tabs before (Chrome 149 disables GET /json/new — use PUT):\n     curl -s --max-time 8 -X PUT "http://localhost:9222/json/new?https://www.google.com/travel/flights" >/dev/null; sleep 2\n     curl -s --max-time 8 http://localhost:9222/json/list | python -c "import sys,json; d=json.load(sys.stdin); print('flight_tabs_before', sum(1 for t in d if t.get('type')=='page' and 'travel/flights' in (t.get('url') or '')))"\n   (If PUT also fails to open a tab, record the current count and note the inducement was skipped -> WARN.)\n2. Run the Node scraper directly (it closes stale flights tabs on startup):\n     cd "${DMW}" && NODE_PATH="$(pwd)/node_modules" node services/flight_scrape.cjs data/tmp/scrape_input.json 2>&1 | grep -iE "closed stale|\\"ok\\"" | head\n3. Recount flights tabs after, via the CDP list:\n     cd "${DMW}" && python -c "import urllib.request,json; d=json.load(urllib.request.urlopen('http://localhost:9222/json/list',timeout=8)); print('flight_tabs_after', sum(1 for t in d if t.get('type')=='page' and 'travel/flights' in (t.get('url') or '')))"\nPASS iff the scraper logged a 'closed stale flights tab' AND flight_tabs_after <= 1 (it cleaned up). Put before/after counts + the 'closed stale' log line in evidence. If the tab couldn't be induced, downgrade to WARN and say so.`,
    { label: 'resilience:flight-selfheal', phase: 'Prove resilience', schema: CHECK }
  ),
  // Channel watchdog is actually RUNNING (non-destructive — do NOT restart a live channel)
  () => agent(
    `Confirm the channel auth watchdog is actually RUNNING in the live bot and the reactive wedge-heal is reachable — NON-DESTRUCTIVELY (do NOT POST jobs that restart a channel; do NOT call force_restart_channel).\n\n${HINT}\n\nDo:\n1. Read-only watchdog status (proves the module imports & the WSL plumbing works from the bot's host):\n     cd "${DMW}" && python -m domains.peterbot.channel_auth\n   Expect a "=== channel_auth status ===" block with WSL creds readable, has_refresh, NOT corrupt, and "Sessions 401 : none".\n2. Confirm the live DiscordBot process is up and was started recently (the watchdog ticks every 60s once the process is running). Find the most recent fresh login in the log:\n     cd "${DMW}" && (grep -a "logging in" logs/discord_bot.log | tail -1)\n3. Confirm the reactive-heal function imports and the scheduler is wired to call it:\n     cd "${DMW}" && python -c "from domains.peterbot.channel_auth import force_restart_channel; print('force_restart_channel importable')" && grep -c "force_restart_channel" domains/peterbot/scheduler.py\nPASS iff the status block shows not-corrupt + no 401 sessions, the bot has a recent login line, force_restart_channel imports, and scheduler.py references it (count >= 1). NOTE in notes that an actual induced channel-wedge recovery is intentionally NOT run here (it would restart a live channel) — that belongs in a maintenance window.`,
    { label: 'resilience:channel-watchdog', phase: 'Prove resilience', schema: CHECK }
  ),
])).filter(Boolean)

phase('Synthesize')
const report = await agent(
  `Write a robust live-resilience report (GitHub-flavored markdown) for the morning-jobs subsystem.\n\nLIVE PROBES:\n${JSON.stringify(probes, null, 2)}\n\nRESILIENCE PROOFS:\n${JSON.stringify(resilience, null, 2)}\n\nProduce:\n- First line: "**Live status: PASS**" / "**Live status: FAIL**" / "**Live status: PASS (with warnings)**". FAIL if any check is FAIL; "with warnings" if any WARN but none FAIL; else PASS.\n- A table: Check | Status | Attempts | Key evidence (~12 words).\n- A "Self-heal proven" section: did the flight tab-leak recovery actually fire on the live Chrome? Is the channel watchdog running? Be explicit about what was exercised vs only verified.\n- A "Caveats" line: note the channel induced-wedge test was skipped (destructive), and anything flaky (probes that needed retries) — flakiness that recovered is NOT a failure, but call it out.\nReturn ONLY the markdown.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return { probes, resilience, report }

export const meta = {
  name: 'verify-morning-jobs-e2e',
  description: 'End-to-end verification of the 2026-06-22 morning-jobs fixes: channel wedge auto-heal, flight-scrape CDP self-heal, and vercel-scraper self-heal. Runs each subsystem live, adversarially re-proves the riskiest claims with independent methods, then synthesizes a PASS/FAIL report.',
  phases: [
    { title: 'Check subsystems', detail: 'run channel-auth, flight-scrape and vercel-scraper live in parallel' },
    { title: 'Adversarial re-check', detail: 'independently re-prove the riskiest claims with different methods' },
    { title: 'Synthesize', detail: 'combine into a final PASS/FAIL report' },
  ],
}

const DM = '/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger'
const HB = '/mnt/c/Users/Chris Hadley/claude-projects/hadley-bricks-inventory-management'
const OAUTH_SUITE = `${DM}/scripts/verify-oauth-token.sh`

const RUN_HINT = [
  'Environment: Windows with a Bash tool; the Peter services run in WSL, the schedulers in Python on Windows.',
  "Run WSL commands as: wsl -d Ubuntu -- bash -lc '<cmd>'.",
  'CRITICAL gotcha: literal /mnt/c/... paths contain a space and get MANGLED by Git Bash inside command strings.',
  '- WSL-native paths (/proc, $HOME/.claude, localhost curl, tmux) are safe inline in `wsl bash -lc`.',
  '- To run a /mnt/c script file, use MSYS_NO_PATHCONV=1:  MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash "<path>"',
  '- To run Python in a repo, cd into the Windows path with the Bash tool first (no wsl), e.g.',
  `    cd "C:/Users/Chris Hadley/claude-projects/discord-messenger" && python -c "..."`,
  'Strip Chrome DEP0169 deprecation warning lines from any output you parse.',
].join('\n')

const CHECK_SCHEMA = {
  type: 'object',
  properties: {
    subsystem: { type: 'string' },
    status: { type: 'string', enum: ['PASS', 'FAIL'] },
    metrics: { type: 'object', additionalProperties: true },
    evidence: { type: 'string' },
    notes: { type: 'string' },
  },
  required: ['subsystem', 'status', 'evidence'],
}

const VERDICT_SCHEMA = {
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

phase('Check subsystems')
const checks = (await parallel([
  // A — channel auth + reactive wedge heal
  () => agent(
    `Verify the WSL Claude CHANNEL AUTH subsystem end-to-end and that the new reactive wedge-heal is deployed.\n\n${RUN_HINT}\n\nDo ALL of:\n1. Run the OAuth suite and capture its final RESULT line:\n     MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash "${OAUTH_SUITE}"\n   It must end with "overall=PASS".\n2. Fresh end-to-end job-auth probe (must return JSON containing AUTH_OK):\n     wsl -d Ubuntu -- bash -lc 'curl -s --max-time 30 -X POST http://localhost:8103/job -H "Content-Type: application/json" --data-raw "{\\"skill\\":\\"auth-test\\",\\"context\\":\\"Reply with exactly AUTH_OK and nothing else.\\"}"'\n3. Confirm the reactive heal CODE is present: grep shows function force_restart_channel in ${DM}/domains/peterbot/channel_auth.py AND that ${DM}/domains/peterbot/scheduler.py imports/calls force_restart_channel on the empty-response path.\n4. Confirm the heal watchdog is DEPLOYED in the live bot: the running DiscordBot must have started AFTER the watchdog was added. Check logs/discord_bot.log for a recent fresh login timestamp and, if present, any channel_auth watchdog log line. Report the bot's most recent start time.\nSet status=PASS only if 1, 2, and 3 all hold. Put concrete evidence (the RESULT line, the AUTH_OK snippet, grep hits, bot start time) in evidence; record {oauth_overall, jobs_channel_auth_ok, force_restart_channel_present, scheduler_calls_heal, bot_started_at} in metrics.`,
    { label: 'check:channel-auth', phase: 'Check subsystems', schema: CHECK_SCHEMA }
  ),
  // C — flight scrape CDP self-heal
  () => agent(
    `Verify the FLIGHT-PRICES scrape subsystem now uses the live scrape (not the SerpApi fallback) and self-heals a wedged CDP Chrome.\n\n${RUN_HINT}\n\nDo ALL of:\n1. Run the daily watches live and parse the source:\n     cd "C:/Users/Chris Hadley/claude-projects/discord-messenger" && python -c "import asyncio,json; from services.flight_prices import run_daily_watches; o=asyncio.run(run_daily_watches()); print(json.dumps({'scrape_ok':o.get('scrape_ok'),'fallback_used':o.get('fallback_used'),'sources':[w.get('source') for w in o.get('watches',[])]}))"\n   Strip DEP0169 lines. PASS requires scrape_ok=true, fallback_used=false, and every watch source=="scrape".\n2. Confirm the self-heal CODE is present: grep ${DM}/services/flight_scrape.cjs for the stale-tab cleanup ("closed stale flights tab" / google.*travel/flights close loop) AND grep ${DM}/services/flight_prices.py for restart_cdp_chrome and the attempt-2 relaunch retry.\nSet status=PASS only if BOTH hold. Put the parsed JSON + grep hits in evidence; record {scrape_ok, fallback_used, sources, cleanup_present, restart_helper_present} in metrics.`,
    { label: 'check:flight-scrape', phase: 'Check subsystems', schema: CHECK_SCHEMA }
  ),
  // B — vercel scraper self-heal + honest login detection
  () => agent(
    `Verify the VERCEL usage scraper pulls metrics again and no longer cries "session expired" on a wedged Chrome.\n\n${RUN_HINT}\n\nDo ALL of:\n1. Run the scraper's scrape function live (no upsert needed) and count metrics:\n     cd "C:/Users/Chris Hadley/claude-projects/hadley-bricks-inventory-management" && python -c "import importlib.util as u; s=u.spec_from_file_location('vu','scripts/vercel-usage-scraper.py'); m=u.module_from_spec(s); s.loader.exec_module(m); r,st=m.scrape_vercel_usage(); print('status',st,'metrics',len(r))"\n   Strip DEP0169 lines. PASS requires status==ok and metrics>=10.\n2. Confirm the CODE improvements: grep scripts/vercel-usage-scraper.py for relaunch_chrome_vinted, for the login-redirect detection (returns 'login_required'), and that main() retries after a relaunch before alerting.\nSet status=PASS only if BOTH hold. Put the printed status/metrics + grep hits in evidence; record {scrape_status, metric_count, relaunch_present, login_detect_present} in metrics.`,
    { label: 'check:vercel-scraper', phase: 'Check subsystems', schema: CHECK_SCHEMA }
  ),
])).filter(Boolean)

phase('Adversarial re-check')
const verdicts = (await parallel([
  () => agent(
    `Adversarially verify, with an INDEPENDENT method (do NOT run scripts/verify-oauth-token.sh), this claim:\n  "The live scheduled-job path authenticates end-to-end on BOTH jobs channels right now, with no channel locked out."\nTry hard to REFUTE it. Default refuted=true unless your OWN evidence proves it true.\n\n${RUN_HINT}\n\nIndependent method:\n1. POST a fresh AUTH_OK probe to the Opus jobs channel (:8103) and the Sonnet jobs channel (:8105):\n     wsl -d Ubuntu -- bash -lc 'for p in 8103 8105; do echo "== :$p =="; curl -s --max-time 30 -X POST http://localhost:$p/job -H "Content-Type: application/json" --data-raw "{\\"skill\\":\\"auth-test\\",\\"context\\":\\"Reply with exactly AUTH_OK and nothing else.\\"}"; echo; done'\n   Both must contain AUTH_OK.\n2. Grep every channel tmux pane tail for a lockout marker — there must be NONE:\n     wsl -d Ubuntu -- bash -lc 'for s in peter-channel whatsapp-channel jobs-channel jobs-channel-sonnet extract-channel; do tmux capture-pane -p -J -t "$s" 2>/dev/null | tail -40 | grep -q "Please run /login\\|401 Invalid authentication" && echo "LOCKED:$s"; done; echo done'\nrefuted=true if either channel fails to return AUTH_OK or any pane shows a lockout.`,
    { label: 'skeptic:channel-e2e', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
  () => agent(
    `Adversarially verify, with an INDEPENDENT method, this claim:\n  "The Google Flights scraper connects and returns flights, and is NOT leaking tabs into the shared CDP Chrome."\nTry hard to REFUTE it. Default refuted=true unless your OWN evidence proves it true.\n\n${RUN_HINT}\n\nIndependent method (do NOT call run_daily_watches — drive the scraper/CDP directly):\n1. Run the Node scraper directly on the existing input and check it connected & returned flights (ok:true):\n     cd "C:/Users/Chris Hadley/claude-projects/discord-messenger" && NODE_PATH="$(pwd)/node_modules" node services/flight_scrape.cjs data/tmp/scrape_input.json 2>/dev/null | python -c "import sys,json; d=json.load(sys.stdin); print('ok',d.get('ok'),'results',len(d.get('results',[])), 'flights',[len(r.get('flights',[])) for r in d.get('results',[])])"\n   (If data/tmp/scrape_input.json is missing, write a minimal one: {"cdp":"http://localhost:9222","searches":[{"id":"t","label":"t","origin":"LHR","destination":"HND","outbound":"2027-03-25","return":"2027-04-11","adults":1,"children":[],"maxStops":1}]} )\n   ok must be true and at least one search must return >0 flights.\n2. After it runs, count leftover Google Flights tabs in the shared CDP Chrome — the scraper should have closed its own and any stale ones:\n     curl -s --max-time 8 http://localhost:9222/json/list | python -c "import sys,json; d=json.load(sys.stdin); n=sum(1 for t in d if t.get('type')=='page' and 'travel/flights' in (t.get('url') or '')); print('flight_tabs_open',n)"\n   A small number (<=1) is fine; many (>=4) means the leak persists.\nrefuted=true if ok!=true, zero flights, OR >=4 flight tabs remain open.`,
    { label: 'skeptic:flight-scrape', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
  () => agent(
    `Adversarially verify, with an INDEPENDENT method, this claim:\n  "The Vercel dashboard session is genuinely logged in — the morning 'session expired' alert was a false positive caused by a wedged Chrome, not a real expiry."\nTry hard to REFUTE it. Default refuted=true unless your OWN evidence proves it true.\n\n${RUN_HINT}\n\nIndependent method (drive CDP directly, do NOT run the scraper main):\n  cd "C:/Users/Chris Hadley/claude-projects/hadley-bricks-inventory-management" && python -c "from playwright.sync_api import sync_playwright; \np=sync_playwright().start(); b=p.chromium.connect_over_cdp('http://127.0.0.1:9222'); c=b.contexts[0] if b.contexts else b.new_context(); pg=c.new_page(); pg.goto('https://vercel.com/chrishadley1983s-projects/~/usage', wait_until='domcontentloaded', timeout=40000); pg.wait_for_timeout(3000); u=pg.url; print('final_url', u); print('logged_in', ('/usage' in u and 'login' not in u.lower() and 'sso' not in u.lower())); pg.close(); b.close()"\nrefuted=true if the final URL redirected to a login/sso page (i.e. the session really IS expired and the claim is wrong).`,
    { label: 'skeptic:vercel-session', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
])).filter(Boolean)

phase('Synthesize')
const report = await agent(
  `Write a tight end-to-end verification report (GitHub-flavored markdown) for the 2026-06-22 morning-jobs fixes.\n\nSUBSYSTEM CHECKS:\n${JSON.stringify(checks, null, 2)}\n\nINDEPENDENT ADVERSARIAL VERDICTS:\n${JSON.stringify(verdicts, null, 2)}\n\nProduce:\n- A first line: "**Overall: PASS**" or "**Overall: FAIL**". PASS only if every subsystem check status==PASS AND no adversarial verdict has refuted=true.\n- A markdown table: Subsystem | Status | Key evidence (~12 words).\n- An "Independent cross-check" section: one bullet per verdict — the claim, stood or refuted, the method + key evidence.\n- A "Residual risk / caveats" line — anything still manual (e.g. a real Vercel re-login is only needed if the session-skeptic refutes) or "none".\nReturn ONLY the markdown, no preamble.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return { checks, verdicts, report }

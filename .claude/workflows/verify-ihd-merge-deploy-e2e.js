export const meta = {
  name: 'verify-ihd-merge-deploy-e2e',
  description: 'Verify the IHD integration AFTER fix+merge+deploy: Pi services backed up in the fold, secrets externalized (none committed), local main has only the clean IHD commit (no unrelated WIP, main not damaged), the Pi runs the externalized app from env and still works, and Peter endpoints are live. Adversarially re-proves the no-secret, no-damage, and Pi-works-from-env claims.',
  phases: [
    { title: 'Verify', detail: 'git merge integrity, fold completeness, repo secrets, Pi deploy, Peter endpoints' },
    { title: 'Adversarial re-check', detail: 'no secret committed, main not damaged, Pi genuinely runs from env' },
    { title: 'Synthesize', detail: 'PASS/FAIL' },
  ],
}

const ROOT = 'C:/Users/Chris Hadley/claude-projects/discord-messenger'
const PI = 'chrishadley1983@192.168.0.110'
const API = 'http://localhost:8100'
const IHD_PI = 'http://192.168.0.110:3000'

const HINTS = [
  'ENVIRONMENT: Windows Git Bash + Bash tool. The sandbox BLOCKS network — set the Bash tool',
  'parameter dangerouslyDisableSandbox:true for ALL curl AND ssh calls (else they hang / 000).',
  `SSH to the Pi is KEY-BASED (no password): ssh -o BatchMode=yes ${PI} '<cmd>'  — works from here.`,
  `Git: the IHD work is a single commit on LOCAL main (subject starts "feat(ihd): fold in IHD/Pi dashboard").`,
  'Inspect main without checking it out: git log main, git show main:<path>, git grep <re> main -- <path>.',
].join('\n')

const CHECK_SCHEMA = {
  type: 'object',
  properties: {
    dimension: { type: 'string' },
    status: { type: 'string', enum: ['PASS', 'FAIL'] },
    checks: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, status: { type: 'string', enum: ['PASS', 'FAIL'] }, evidence: { type: 'string' },
    }, required: ['name', 'status', 'evidence'] } },
    summary: { type: 'string' },
  },
  required: ['dimension', 'status', 'checks', 'summary'],
}
const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    claim: { type: 'string' }, refuted: { type: 'boolean' },
    confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
    method: { type: 'string' }, evidence: { type: 'string' },
  },
  required: ['claim', 'refuted', 'confidence', 'evidence'],
}

phase('Verify')
const dims = (await parallel([
  () => agent(
    `Verify the git merge integrity of the IHD commit on local main.\n\n${HINTS}\n\nDimension "git". cwd "${ROOT}". PASS checks:\n1. Local main's HEAD commit subject starts "feat(ihd): fold in IHD/Pi dashboard" (git log -1 main --format=%s).\n2. That commit is a single commit on top of the prior main (its parent subject is the fitness "self-heal dead exercise demo videos"). It did NOT bundle the stale feat/reset-cut-dashboard-redesign branch.\n3. The commit does NOT contain unrelated WIP: git show --stat main must NOT list services/flight_prices.py, domains/peterbot/channel_auth.py, domains/peterbot/scheduler.py, or scripts/verify-oauth-token.sh.\n4. main is NOT damaged: those pre-existing files STILL EXIST on main (git cat-file -e main:domains/peterbot/channel_auth.py && git cat-file -e main:services/flight_prices.py) — the merge added, didn't delete.\nQuote evidence per check.`,
    { label: 'verify:git', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
  () => agent(
    `Verify the on-Pi services were folded in. Read under "${ROOT}/ihd" (no network). Dimension "fold".\nPASS checks:\n1. ihd/pi-services/zigbee-api/server.py exists and is the MQTT->HTTP bridge with SQLite history (grep for "/history" and "sensors.db" / "readings").\n2. ihd/pi-services/screen-control/controller.py exists.\n3. ihd/pi-services/media-overlay/ (launch.sh, close-overlay.py) and ihd/pi-services/network-watchdog.sh exist.\n4. ihd/pi-services/README.md documents the run mechanism (pm2 + cron) and the sensors.db history store.\n5. ihd/PROVENANCE.md now marks the on-Pi services as RETRIEVED (no longer an open gap).\n6. These are committed on main (git show main:ihd/pi-services/zigbee-api/server.py | head).\nQuote evidence per check.`,
    { label: 'verify:fold', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
  () => agent(
    `Verify secrets are externalized in the repo. Dimension "secrets". cwd "${ROOT}".\n\n${HINTS}\n\nPASS checks:\n1. The 3 routes read from env on main: git show main:ihd/ihd-app/src/app/api/hb/route.ts | grep "process.env.SUPABASE_SERVICE_KEY"; same for energy/kids reading process.env.SUPABASE_ANON_KEY.\n2. NO plaintext Supabase/HB secret committed anywhere: git grep -nE "eyJhbGci|08215bd643f242cc" main -- ihd/  must return NOTHING.\n3. ihd/ihd-app/.env.example IS committed (git cat-file -e main:ihd/ihd-app/.env.example) and contains only empty var names (no values).\n4. No .env.local committed: git ls-tree -r --name-only main | grep "\\.env.local" returns nothing.\nQuote evidence per check. FAIL immediately if check 2 finds any committed secret.`,
    { label: 'verify:secrets', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
  () => agent(
    `Verify the DEPLOYED IHD app on the Pi. Dimension "pi-deploy".\n\n${HINTS}\n\nPASS checks (sandbox disabled for ssh/curl):\n1. Running Pi source has NO hardcoded JWT: ssh ${PI} 'grep -rlE "eyJhbGci" ~/ihd-app/src/app/api/ || echo CLEAN' → must be CLEAN.\n2. Pi route files read from env: ssh ${PI} 'grep -h "process.env" ~/ihd-app/src/app/api/hb/route.ts ~/ihd-app/src/app/api/energy/route.ts' shows SUPABASE_SERVICE_KEY / SUPABASE_ANON_KEY.\n3. .env.local on the Pi has the keys AND still has HADLEY_API_URL: ssh ${PI} 'cut -d= -f1 ~/ihd-app/.env.local' lists HADLEY_API_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY, HB_INTERNAL_KEY.\n4. Dashboard live: curl ${IHD_PI} → 200. pm2 ihd online: ssh ${PI} 'pm2 jlist' shows ihd status online.\n5. Env-backed routes return REAL data (proves env wired, not just removed): curl ${IHD_PI}/api/energy (anon key) shows electricity kwh; curl ${IHD_PI}/api/hb (SERVICE key) shows orders/platforms. Both must be non-empty/non-error.\nQuote evidence per check.`,
    { label: 'verify:pi-deploy', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
  () => agent(
    `Verify Peter's endpoints still work post-merge (regression). Dimension "peter".\n\n${HINTS}\n\nAgainst ${API} (sandbox disabled). PASS checks:\n1. GET /home/sensors/trend?days=7 → 200 with rooms[] (Kitchen+Bedroom).\n2. GET /ihd/pocket-money → 200 with a summary string.\n3. GET /ihd/plug, /ihd/pets, /ihd/screen, /ihd/jokes, /ihd/kids → all 200.\n4. POST auth gate intact: POST /ihd/pocket-money and /ihd/plug WITHOUT x-api-key → 401 (no mutation).\nQuote each HTTP code.`,
    { label: 'verify:peter', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
])).filter(Boolean)

phase('Adversarial re-check')
const verdicts = (await parallel([
  () => agent(
    `Adversarially verify and try hard to REFUTE:\n  "No live Supabase/HB secret is committed anywhere in the repo at main HEAD."\nDefault refuted=true unless your own scan proves it true.\n\n${HINTS}\n\nMethod: independently scan the COMMITTED tree (not the working tree) — git grep -nIE "eyJhbgci|eyJhbGci|service_role|08215bd643|sk-[A-Za-z0-9]{20}" main; and git ls-tree -r --name-only main | grep -iE "env.local|secret|credential". Also spot-check git show main:ihd/ihd-app/src/app/api/hb/route.ts for any literal JWT. The claim STANDS only if NO committed file contains a real key value (env-var names and the .env.example template with empty values are fine).`,
    { label: 'skeptic:no-secret', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
  () => agent(
    `Adversarially verify and try hard to REFUTE:\n  "The merge to local main only ADDED the IHD commit and did not damage or revert main's other recent work (morning-jobs/oauth/flight: channel_auth.py, scheduler.py, services/flight_prices.py, the verify-*.js workflows)."\nDefault refuted=true unless proven.\n\n${HINTS}\n\nMethod (cwd ${ROOT}): git log --oneline -3 main (confirm IHD commit sits directly on the previous main tip, no rebase/force of history). For each of domains/peterbot/channel_auth.py, domains/peterbot/scheduler.py, services/flight_prices.py: git cat-file -e main:<path> (exists) AND compare its blob to the pre-IHD parent (git diff main~1 main -- <path> should be EMPTY — the IHD commit didn't touch them). Refute if any is missing on main or was modified/deleted by the IHD commit.`,
    { label: 'skeptic:no-damage', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
  () => agent(
    `Adversarially verify and try hard to REFUTE:\n  "The Pi is genuinely RUNNING the externalized code reading secrets from .env.local — not left broken, and not still secretly hardcoded."\nDefault refuted=true unless proven.\n\n${HINTS}\n\nMethod (ssh, sandbox disabled): (1) Confirm the running source truly has no JWT literal: ssh ${PI} 'grep -rc "eyJhbGci" ~/ihd-app/src/app/api/ | grep -v ":0" || echo NO_LITERALS'. (2) Prove the SERVICE-role key is actually loaded from env and working by hitting the service-key-only route: curl ${IHD_PI}/api/hb — it must return real order/platform data (impossible without the service_role key being present in process.env). (3) Temporarily prove dependence on env WITHOUT breaking anything: just confirm .env.local contains SUPABASE_SERVICE_KEY (ssh grep -c) and that removing it WOULD break /api/hb (do NOT actually remove it — reason from the code that reads process.env.SUPABASE_SERVICE_KEY). The claim STANDS only if no literal remains AND /api/hb returns real data via the env key.`,
    { label: 'skeptic:pi-from-env', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
])).filter(Boolean)

phase('Synthesize')
const report = await agent(
  `Write a tight PASS/FAIL report (GitHub-flavored markdown) for the IHD fix+merge+deploy.\n\nDIMENSIONS:\n${JSON.stringify(dims, null, 2)}\n\nADVERSARIAL VERDICTS:\n${JSON.stringify(verdicts, null, 2)}\n\nProduce:\n- First line "**Overall: PASS**" or "**Overall: FAIL**". PASS only if every dimension is PASS AND no verdict refuted=true.\n- A dimensions table: Dimension | Status | Summary.\n- A checks table: Check | Status | Evidence (~12 words).\n- "Independent cross-check": one bullet per verdict.\n- "Caveats:" — note the plug is physically unplugged (reads offline by design), and that local main was NOT pushed to the remote (left to the user), or "none".\nReturn ONLY the markdown.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return { dims, verdicts, report }

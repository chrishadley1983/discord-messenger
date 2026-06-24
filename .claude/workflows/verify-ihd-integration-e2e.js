export const meta = {
  name: 'verify-ihd-integration-e2e',
  description: 'End-to-end verification of the IHD fold-in + Peter integration: source folded into ihd/, every new Hadley API endpoint live (sensor history/trend + /ihd/* plug, pocket-money, jokes, pets, screen, kids), POST auth-gating, skills+manifest wiring. Adversarially re-proves trend math, pocket-money proxy fidelity + write-protection, and fold-in/secret honesty. Synthesizes PASS/FAIL.',
  phases: [
    { title: 'Verify', detail: 'fold-in, endpoints, skills, code wiring — one agent each' },
    { title: 'Adversarial re-check', detail: 'trend math, pocket-money fidelity+auth, fold-in/secrets honesty' },
    { title: 'Synthesize', detail: 'combine into a PASS/FAIL report' },
  ],
}

const ROOT = 'C:/Users/Chris Hadley/claude-projects/discord-messenger'
const IHD_SRC = 'C:/Users/Chris Hadley/claude-projects/ihd'   // original, for diff
const API = 'http://localhost:8100'
const IHD_APP = 'http://192.168.0.110:3000'
const BRIDGE = 'http://192.168.0.110:5001'

const NET_HINT = [
  'ENVIRONMENT: Windows Git Bash + Bash tool. The sandbox BLOCKS network by default —',
  'every curl (localhost API, the LAN IHD app :3000, the bridge :5001) MUST set the Bash tool',
  'parameter dangerouslyDisableSandbox:true or it times out as HTTP 000. Treat 000 as "could not',
  'connect" (retry once with sandbox disabled), not "endpoint broken".',
].join('\n')

const CHECK_SCHEMA = {
  type: 'object',
  properties: {
    dimension: { type: 'string' },
    status: { type: 'string', enum: ['PASS', 'FAIL'] },
    checks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          status: { type: 'string', enum: ['PASS', 'FAIL'] },
          evidence: { type: 'string' },
        },
        required: ['name', 'status', 'evidence'],
      },
    },
    summary: { type: 'string' },
  },
  required: ['dimension', 'status', 'checks', 'summary'],
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

phase('Verify')
const dims = (await parallel([
  // D1 — fold-in integrity
  () => agent(
    `Verify the IHD project was folded into the repo correctly. Read files under "${ROOT}/ihd" (no network).\n\nDimension "fold-in". PASS checks:\n1. "${ROOT}/ihd" exists with the app source: ihd-app/src/app/page.tsx, ihd-app/src/app/api/sensor/history/route.ts, ihd-app/src/app/api/plug/route.ts, pi-services/sensor/main.py, health-logger/health_logger.py all present.\n2. Heavy/regenerable dirs were EXCLUDED: ihd-app/node_modules and ihd-app/.next do NOT exist; no .png screenshots at the ihd/ top level.\n3. "${ROOT}/ihd/PROVENANCE.md" exists and documents (a) the on-Pi-only :5001 bridge + :5002 screen services not being in the repo, and (b) the hardcoded secrets risk.\n4. Count the folded source files (find "${ROOT}/ihd" -type f | wc -l) — report the number (expect ~90).\nQuote evidence per check. FAIL any that do not hold.`,
    { label: 'verify:fold-in', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
  // D2 — endpoints live + shapes + auth gating
  () => agent(
    `Verify every NEW Hadley API endpoint is live with the right shape.\n\n${NET_HINT}\n\nDimension "endpoints". Against ${API} (sandbox disabled). PASS checks:\n1. GET /home/sensors/trend?days=7 → 200, JSON with rooms[] (each has room, daily[] of {date,temp_min,temp_max,temp_avg}, avg_change_vs_prev_day_c). Only temp-reporting rooms (expect Kitchen+Bedroom, NOT Lounge).\n2. GET /home/sensors/history?room=bedroom&hours=6 → 200, {device:"sensor_bedroom", count>0, points[] with ts+temperature}.\n3. GET /ihd/pocket-money → 200 with a "summary" string (e.g. "Emmie has £.., Max has £.."). Pence-based.\n4. GET /ihd/pocket-money/calculate → 200 with emmie/max totals.\n5. GET /ihd/jokes → 200 {jokes[],count}. GET /ihd/pets → 200 {pets,sleeping}. GET /ihd/screen → 200 (state/display). GET /ihd/plug → 200 (state may be "offline" if Z2M device API is down — that's acceptable, the route still returns 200). GET /ihd/kids → 200.\n6. AUTH GATING (critical, no side effects): POST without x-api-key to each of /ihd/plug, /ihd/pocket-money, /ihd/media, /ihd/screen/wake, /ihd/jokes → must return 401 (or 403). Do NOT send a valid key (don't actually mutate).\nReport each endpoint's HTTP code + a datum. FAIL any GET that isn't 200 (except note plug offline) or any POST that is NOT auth-gated.`,
    { label: 'verify:endpoints', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
  // D3 — skills + manifest wiring
  () => agent(
    `Verify the new Peter skills + manifest. Read files under "${ROOT}/domains/peterbot/wsl_config/skills" (no network).\n\nDimension "skills". PASS checks:\n1. manifest.json is valid JSON and contains entries: home-control, pocket-money, kids-pets, dad-jokes (all conversational:true), and home-sensors now includes trend triggers (e.g. "is it warmer than yesterday").\n2. SKILL.md files exist: home-control/SKILL.md, pocket-money/SKILL.md, kids-pets/SKILL.md, dad-jokes/SKILL.md, and home-sensors/SKILL.md has a "Trends & history" section referencing /home/sensors/trend.\n3. Each new SKILL.md references the correct endpoint(s) under base http://172.19.64.1:8100 and notes mutating calls need x-api-key.\n4. Regression: the pre-existing pocket-money-weekly skill entry still exists and is unchanged (scheduled, not broken by the new conversational pocket-money skill).\nQuote a line per check. FAIL any that do not hold.`,
    { label: 'verify:skills', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
  // D4 — code wiring + compile
  () => agent(
    `Verify the integration code wiring + that it compiles.\n\n${NET_HINT}\n\nDimension "code". cwd "${ROOT}". PASS checks:\n1. py_compile clean: python -m py_compile domains/ihd/service.py hadley_api/peter_routes/ihd.py domains/home_sensors/service.py hadley_api/peter_routes/home_sensors.py → exit 0.\n2. domains/ihd/service.py defines plug_status/plug_set, pocket_money_summary/_full/_add, jokes/_add, pets, kids_summary, media, screen_status/_wake, and IHD_APP base "http://192.168.0.110:3000".\n3. hadley_api/peter_routes/ihd.py defines an APIRouter prefix "/ihd" and gates every POST with Depends(require_auth) (grep: every @router.post has dependencies=[Depends(require_auth)]).\n4. domains/home_sensors/service.py defines get_history + get_trend; hadley_api/peter_routes/home_sensors.py exposes /sensors/history and /sensors/trend.\n5. The auto-discovery in hadley_api/main.py will load these (peter_routes/*.py with a "router" attr) — confirm both files define router.\nQuote evidence per check. FAIL any that do not hold.`,
    { label: 'verify:code', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
])).filter(Boolean)

phase('Adversarial re-check')
const verdicts = (await parallel([
  // S1 — trend math is actually correct vs the raw history
  () => agent(
    `Adversarially verify and try hard to REFUTE:\n  "GET /home/sensors/trend computes daily min/max/avg correctly from the bridge's raw /history points."\nDefault refuted=true unless your OWN recomputation proves it true.\n\n${NET_HINT}\n\nMethod: For room=bedroom, fetch ${API}/home/sensors/trend?days=2 AND the raw ${BRIDGE}/history?device=sensor_bedroom&hours=48&type=readings. Pick the most recent fully-covered date in the trend's daily[]; independently recompute min/max/avg temperature for that date from the raw points (group by ts[:10]); compare to the endpoint's temp_min/temp_max/temp_avg (allow ±0.1 rounding). Also confirm avg_change_vs_prev_day_c equals last two daily temp_avg differenced. Claim STANDS only if your recomputation matches.`,
    { label: 'skeptic:trend-math', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
  // S2 — pocket-money proxy fidelity + write protection
  () => agent(
    `Adversarially verify and try hard to REFUTE:\n  "GET /ihd/pocket-money returns the SAME live data as the IHD app, and the money cannot be changed without the x-api-key."\nDefault refuted=true unless your OWN evidence proves it true.\n\n${NET_HINT}\n\nMethod (NO real mutation): (1) Fidelity — fetch ${API}/ihd/pocket-money?full=true and the IHD app's own ${IHD_APP}/api/kids/pocket-money; the balances for emmie+max must match exactly (the Hadley route is a faithful proxy). (2) Write-protection — record the current balances; POST ${API}/ihd/pocket-money WITHOUT an x-api-key (body {"child":"max","amount_pence":100}); it MUST return 401/403; then re-fetch balances and confirm they are UNCHANGED (no money moved). Do NOT send a valid key. Claim STANDS only if balances match the IHD app AND the unauthenticated POST was rejected AND balances were unchanged.`,
    { label: 'skeptic:pocket-money', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
  // S3 — fold-in & secrets honesty (don't let the fold-in quietly ship secrets / claim completeness)
  () => agent(
    `Adversarially verify and try hard to REFUTE:\n  "The fold-in is honest: it excluded node_modules/.next, it did NOT silently introduce NEW secrets beyond what the original ihd repo already had, and PROVENANCE.md truthfully flags the gaps (on-Pi-only services + hardcoded secrets)."\nDefault refuted=true unless evidence proves it true. No network.\n\nMethod: Read "${ROOT}/ihd/PROVENANCE.md". Grep the folded tree "${ROOT}/ihd" for hardcoded secrets (e.g. service_role JWT in ihd-app/src/app/api/hb/route.ts, supabase anon keys, HB_INTERNAL_KEY) — these EXIST and that is the known risk; confirm PROVENANCE.md explicitly warns not to git-add them until moved to env. Confirm node_modules/.next are absent. Optionally diff a couple of files (e.g. ihd-app/src/app/api/sensor/history/route.ts) against the original at "${IHD_SRC}" to confirm the fold-in is a faithful copy, not a re-write. Refute if PROVENANCE.md omits the secrets warning OR the on-Pi-only services note, OR node_modules got copied, OR the copy diverged from the original. Otherwise the claim STANDS.`,
    { label: 'skeptic:fold-in-honesty', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
])).filter(Boolean)

phase('Synthesize')
const report = await agent(
  `Write a tight end-to-end verification report (GitHub-flavored markdown) for the IHD fold-in + Peter integration.\n\nDIMENSION RESULTS:\n${JSON.stringify(dims, null, 2)}\n\nINDEPENDENT ADVERSARIAL VERDICTS:\n${JSON.stringify(verdicts, null, 2)}\n\nProduce:\n- First line: "**Overall: PASS**" or "**Overall: FAIL**". PASS only if every dimension is PASS AND no verdict has refuted=true. (A plug reading "offline" is NOT a fail — the route works; note it as a caveat.)\n- A dimensions table: Dimension | Status | Summary.\n- A checks table across all dimensions: Check | Status | Evidence (~12 words).\n- "Independent cross-check": one bullet per verdict — claim, stood/refuted, key evidence.\n- "Caveats / residual risks:" — note the plug upstream (Z2M device API) being offline, hardcoded secrets in the folded code (must move to env before commit), and the on-Pi-only :5001/:5002 services not yet backed up. Or "none".\nReturn ONLY the markdown.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return { dims, verdicts, report }

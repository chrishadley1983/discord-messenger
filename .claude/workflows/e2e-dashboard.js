export const meta = {
  name: 'e2e-dashboard',
  description: 'Full end-to-end test of the Reset Cut dashboard: trigger a local refresh (rebuild from Withings/Garmin + redeploy), then verify artifacts, render correctness (Playwright), and data integrity, and report PASS/FAIL',
  whenToUse: 'After changing the dashboard template or build, to prove the whole pipeline works end-to-end including the local refresh button path.',
  phases: [
    { title: 'Refresh', detail: 'trigger POST /fitness/dashboard/refresh and wait for the rebuild' },
    { title: 'Verify', detail: 'artifacts + render (Playwright) + data integrity, in parallel' },
    { title: 'Report', detail: 'aggregate a PASS/FAIL verdict with evidence' },
  ],
}

const ROOT = 'C:/Users/Chris Hadley/claude-projects/discord-messenger'
const API = (args && args.api) || 'http://127.0.0.1:8100'
const SURGE = (args && args.surge) || 'https://chris-reset-cut.surge.sh'
const LOCAL_FILE = `${ROOT}/data/reset-cut-dashboard.html`
const LAN_PAGE = `${API}/fitness/dashboard/page`
const CHECK = `${ROOT}/scripts/dashboard-e2e-check.js`
const NODE_PATH = 'C:/Users/Chris Hadley/AppData/Roaming/npm/node_modules'
const PLACEHOLDERS = ['__PAYLOAD__', '__SALT__', '__IV__', '__ITERS__', '__PLAIN_DATA__', '__GENERATED_AT__']

const REFRESH_SCHEMA = {
  type: 'object',
  properties: {
    triggered: { type: 'boolean' },
    completed: { type: 'boolean', description: 'building returned to false' },
    old_generated_at: { type: 'string' },
    new_generated_at: { type: 'string' },
    changed: { type: 'boolean', description: 'new timestamp differs from old' },
    deployed: { type: 'boolean', description: 'surge deploy reported success (from logs/result if visible)' },
    notes: { type: 'string' },
  },
  required: ['triggered', 'completed', 'changed', 'new_generated_at'],
}

const AREA_SCHEMA = {
  type: 'object',
  properties: {
    area: { type: 'string' },
    pass: { type: 'boolean' },
    evidence: { type: 'array', items: { type: 'string' } },
    failures: { type: 'array', items: { type: 'string' } },
  },
  required: ['area', 'pass', 'evidence'],
}

const REPORT_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['PASS', 'FAIL'] },
    summary: { type: 'string' },
    areas: { type: 'array', items: { type: 'object', properties: { area: { type: 'string' }, pass: { type: 'boolean' }, detail: { type: 'string' } }, required: ['area', 'pass'] } },
    blocking_issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdict', 'summary', 'areas'],
}

// ---- Phase 1: refresh locally (the "refresh button" path) -----------------
phase('Refresh')
const refresh = await agent(
  `Test the LOCAL REFRESH path of the dashboard end-to-end, exactly as the in-page Refresh button does.\n\nSteps (use the Bash tool):\n1. Read current state: \`curl -s --max-time 5 ${API}/fitness/dashboard/refresh/status\` and record old generated_at.\n2. Trigger: \`curl -s --max-time 30 -X POST ${API}/fitness/dashboard/refresh\` (expect {"status":"started"} or "already_building").\n3. Poll every ~8s up to ~25 times: \`curl -s ${API}/fitness/dashboard/refresh/status\`. Use a single bash for-loop with sleep so it does not block. Stop when building=false AND generated_at differs from the old one.\n4. Report old vs new generated_at, whether it changed, and whether it completed (building=false).\n\nIf "already_building", wait for the in-flight build to finish then still confirm a fresh timestamp. Return the structured result.`,
  { label: 'refresh', phase: 'Refresh', schema: REFRESH_SCHEMA },
)
log(`refresh: ${refresh && refresh.old_generated_at} -> ${refresh && refresh.new_generated_at} (changed=${refresh && refresh.changed})`)

// ---- Phase 2: verify artifacts + render + data, in parallel ---------------
phase('Verify')
const [artifacts, render, dataMath] = await parallel([
  () => agent(
    `Verify the dashboard BUILD ARTIFACTS after the refresh.\n\nChecks (Bash tool):\n1. Local file ${LOCAL_FILE} exists and has NO unfilled template placeholders. Grep for each of: ${PLACEHOLDERS.join(', ')} — none should remain. Also confirm there is no literal "undefined" rendered into hero values.\n2. The local file embeds plaintext data (const PLAIN = {...}, NOT null) and contains both "latest_weight" and "current_weight".\n3. LAN page serves: \`curl -s -o /dev/null -w "%{http_code} %{content_type}" ${LAN_PAGE}\` → 200 text/html.\n4. Surge serves: \`curl -s -o /dev/null -w "%{http_code} %{content_type}" ${SURGE}\` → 200 text/html, and the surge HTML has PLAIN = null with a non-empty payload (encrypted), i.e. it is gated.\nReport pass/fail with the actual command outputs as evidence.`,
    { label: 'verify:artifacts', phase: 'Verify', schema: AREA_SCHEMA },
  ),
  () => agent(
    `Verify dashboard RENDER CORRECTNESS with the Playwright check script.\n\nRun (Bash tool):\n\`NODE_PATH="${NODE_PATH}" node "${CHECK}" "${LAN_PAGE}"\`\n\nThis launches headless Chromium and asserts: no console errors, all 5 nav sections populate, the hero shows BOTH the current scale number and the 7-day trend number in DISTINCT colours, the Trends charts actually draw, and the page renders on mobile. It prints a JSON verdict and exits 0 on pass / 1 on fail.\n\nReport the script's JSON 'ok', any 'fails', and the key 'checks' (hero numbers+colours, sections, chartsDrawn, mobileHero) as evidence. If node cannot find playwright, say so explicitly in failures.`,
    { label: 'verify:render', phase: 'Verify', schema: AREA_SCHEMA },
  ),
  () => agent(
    `Verify dashboard DATA INTEGRITY by inspecting the baked-in data.\n\nIn ${LOCAL_FILE}, the line \`const PLAIN = {...};\` holds the full data object. Extract and inspect it (read the file; the JSON is on/after that line). Validate:\n1. hero has numeric current_weight (trend) and latest_weight (scale); they should be plausibly close (within a few kg) but may differ — that's expected.\n2. metrics array has 9 entries, each with label/value/sub/status.\n3. hero.progress_pct is between 0 and 100.\n4. trends.series.weight has data points; plan.days has 7 entries; rationale has targets+rules.\n5. generated_at is today's date.\nReport pass/fail with the actual values seen as evidence. Do NOT trigger another build.`,
    { label: 'verify:data', phase: 'Verify', schema: AREA_SCHEMA },
  ),
])

// ---- Phase 3: report ------------------------------------------------------
phase('Report')
const areas = [artifacts, render, dataMath].filter(Boolean)
const refreshArea = {
  area: 'local-refresh',
  pass: !!(refresh && refresh.completed && refresh.changed),
  evidence: [`old=${refresh && refresh.old_generated_at}`, `new=${refresh && refresh.new_generated_at}`, `deployed=${refresh && refresh.deployed}`],
  failures: (refresh && refresh.completed && refresh.changed) ? [] : ['refresh did not produce a fresh build'],
}
const report = await agent(
  `Aggregate this end-to-end dashboard test into a single PASS/FAIL verdict. PASS only if the local refresh produced a fresh build AND artifacts, render and data all passed. List any blocking issues precisely.\n\nRESULTS (JSON):\n${JSON.stringify([refreshArea, ...areas], null, 1)}`,
  { label: 'report', phase: 'Report', schema: REPORT_SCHEMA },
)

return { refresh: refreshArea, areas, report }

export const meta = {
  name: 'live-test-dashboard',
  description: 'Final live test of the DEPLOYED Reset Cut dashboard: probe the public surge + LAN surfaces, then drive each in a real headless browser (unlocking the passcode-gated surge page via WebCrypto) to prove it renders, and report PASS/FAIL',
  whenToUse: 'After deploying the dashboard, as the last gate before calling it done. Tests what real visitors hit (the encrypted public page + the LAN page), not the build pipeline.',
  phases: [
    { title: 'Probe', detail: 'curl both surfaces: 200, gated vs plain, build stamps' },
    { title: 'Live render', detail: 'headless browser drives surge (passcode unlock) + LAN in parallel' },
    { title: 'Report', detail: 'aggregate a PASS/FAIL verdict' },
  ],
}

const ROOT = 'C:/Users/Chris Hadley/claude-projects/discord-messenger'
const SURGE = (args && args.surge) || 'https://chris-reset-cut.surge.sh'
const LAN = (args && args.lan) || 'http://127.0.0.1:8100/fitness/dashboard/page'
const CHECK = `${ROOT}/scripts/dashboard-live-check.js`
const NODE_PATH = 'C:/Users/Chris Hadley/AppData/Roaming/npm/node_modules'

const PROBE_SCHEMA = {
  type: 'object',
  properties: {
    surge: {
      type: 'object',
      properties: {
        http: { type: 'string' }, content_type: { type: 'string' },
        gated: { type: 'boolean', description: 'true if const PLAIN = null AND a non-empty ENC payload is present' },
        generated_at: { type: 'string', description: 'cleartext const GENERATED_AT value' },
      },
      required: ['http', 'gated', 'generated_at'],
    },
    lan: {
      type: 'object',
      properties: {
        http: { type: 'string' }, content_type: { type: 'string' },
        plaintext: { type: 'boolean', description: 'true if const PLAIN = { (data embedded in the clear)' },
        generated_at: { type: 'string' },
      },
      required: ['http', 'plaintext', 'generated_at'],
    },
    builds_match: { type: 'boolean', description: 'surge and LAN generated_at are equal' },
    pass: { type: 'boolean' },
    notes: { type: 'string' },
  },
  required: ['surge', 'lan', 'pass'],
}

const SURFACE_SCHEMA = {
  type: 'object',
  properties: {
    surface: { type: 'string' },
    ok: { type: 'boolean' },
    unlocked: { type: 'boolean', description: 'surge only: passcode decrypt succeeded (null for LAN)' },
    generated_at: { type: 'string' },
    evidence: { type: 'array', items: { type: 'string' } },
    failures: { type: 'array', items: { type: 'string' } },
  },
  required: ['surface', 'ok', 'evidence'],
}

const REPORT_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['PASS', 'FAIL'] },
    summary: { type: 'string' },
    surfaces: { type: 'array', items: { type: 'object', properties: { surface: { type: 'string' }, ok: { type: 'boolean' }, detail: { type: 'string' } }, required: ['surface', 'ok'] } },
    blocking_issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdict', 'summary', 'surfaces'],
}

// ---- Phase 1: probe both surfaces ----------------------------------------
phase('Probe')
const probe = await agent(
  `Probe the two DEPLOYED dashboard surfaces with curl (Bash tool). The surge page is encrypted-at-rest but its template + \`const GENERATED_AT = "..."\` are CLEARTEXT, so you can read the build stamp without the passcode.\n\n1. SURGE ${SURGE}: \`curl -s -o /tmp/s.html -w "%{http_code} %{content_type}"\` (retry up to 3x if you get 504 — surge cold-starts). Then from /tmp/s.html: confirm it is gated (grep \`const PLAIN = null\` present AND the \`const ENC = { payload:"..."\` has a long non-empty base64 payload), and extract \`const GENERATED_AT = "..."\`.\n2. LAN ${LAN}: \`curl -s -o /tmp/l.html -w "%{http_code} %{content_type}"\` → expect 200 text/html. Confirm it is plaintext (grep \`const PLAIN = {\` present), and extract its \`const GENERATED_AT\`.\n3. Compare the two GENERATED_AT values (builds_match).\n\npass = both 200, surge gated, LAN plaintext. Report the actual values as evidence.`,
  { label: 'probe', phase: 'Probe', schema: PROBE_SCHEMA },
)
log(`probe: surge ${probe && probe.surge && probe.surge.generated_at} / lan ${probe && probe.lan && probe.lan.generated_at} / match=${probe && probe.builds_match}`)

// ---- Phase 2: live render of each surface, in parallel --------------------
phase('Live render')
const [surge, lan] = await parallel([
  () => agent(
    `Live-render test the PUBLIC passcode-gated surge page in a real headless browser.\n\nLoad the passcode from .env without printing it, then run the live check:\n\`\`\`\nPC=$(grep -E "^DASHBOARD_PASSCODE=" .env | head -1 | cut -d= -f2- | tr -d '"'"'"'\\r')\nNODE_PATH="${NODE_PATH}" DASH_PASSCODE="$PC" node "${CHECK}" "${SURGE}"\n\`\`\`\n(run from ${ROOT}). The script navigates to surge, enters the passcode, lets WebCrypto decrypt the AES-GCM payload, and asserts the decrypted page renders: 5 nav sections, BOTH hero numbers in distinct colours, 6 charts drawn, mobile both visible. It prints JSON (ok/unlocked/generated_at/checks/fails) and exits 0 on pass.\n\nReport surface="surge", ok, unlocked, generated_at, and the key checks as evidence. If unlocked=false the decrypt/passcode path is broken — that is a hard failure.`,
    { label: 'live:surge', phase: 'Live render', schema: SURFACE_SCHEMA },
  ),
  () => agent(
    `Live-render test the LAN page (no gate) in a real headless browser:\n\`\`\`\nNODE_PATH="${NODE_PATH}" node "${CHECK}" "${LAN}"\n\`\`\`\n(run from ${ROOT}). Same assertions, but the LAN page has no passcode gate (renders immediately from embedded plaintext). Report surface="lan", ok, generated_at, and the key checks (navItems, sections, hero, chartsDrawn, mobileHero) as evidence.`,
    { label: 'live:lan', phase: 'Live render', schema: SURFACE_SCHEMA },
  ),
])

// ---- Phase 3: report ------------------------------------------------------
phase('Report')
const report = await agent(
  `Aggregate this final LIVE dashboard test into one PASS/FAIL verdict. PASS requires: probe passed (both 200, surge gated, LAN plaintext) AND both surfaces rendered live AND the surge passcode unlock/decrypt succeeded. Call out any blocking issue precisely; note (non-blocking) if the surge/LAN build stamps differ.\n\nPROBE:\n${JSON.stringify(probe, null, 1)}\n\nLIVE RENDER:\n${JSON.stringify([surge, lan], null, 1)}`,
  { label: 'report', phase: 'Report', schema: REPORT_SCHEMA },
)

return { probe, surfaces: [surge, lan], report }

export const meta = {
  name: 'verify-home-sensors-e2e',
  description: 'End-to-end verification of the home temperature-sensor feature: live Zigbee bridge, GET /home/sensors endpoint shape, skill+manifest+docs wiring, and the bridge watchdog in the running bot. Adversarially re-proves the riskiest claims (liveness, down-detection, indoor/outdoor routing), then synthesizes PASS/FAIL.',
  phases: [
    { title: 'Verify', detail: 'one agent per dimension: bridge, endpoint, static wiring, watchdog runtime' },
    { title: 'Adversarial re-check', detail: 'independently refute liveness, down-detection, and routing-disambiguation' },
    { title: 'Synthesize', detail: 'combine into a final PASS/FAIL report' },
  ],
}

const ROOT = 'C:/Users/Chris Hadley/claude-projects/discord-messenger'
const BRIDGE = 'http://192.168.0.110:5001'
const API_LOCAL = 'http://localhost:8100'
const API_WSL = 'http://172.19.64.1:8100'   // the interface Peter (WSL) actually uses

const NET_HINT = [
  'ENVIRONMENT: Windows Git Bash with a Bash tool. The sandbox BLOCKS network by default —',
  'every curl (localhost, the LAN bridge, the WSL-facing IP) MUST be run with the Bash tool',
  'parameter dangerouslyDisableSandbox:true, or it silently times out as HTTP 000.',
  'Use: curl -s --max-time 8 -w "\\n%{http_code}" <url>. Treat 000 as "could not connect", not "down" —',
  'retry once with the sandbox disabled before concluding a service is unreachable.',
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
  // D1 — live Zigbee bridge
  () => agent(
    `Verify the Zigbee sensor bridge is live and exposes temperature data.\n\n${NET_HINT}\n\nDimension "bridge". Run: curl -s --max-time 8 ${BRIDGE} (sandbox disabled). PASS checks:\n1. Bridge reachable (HTTP 200, JSON object body).\n2. At least one device has a numeric "temperature" field (e.g. sensor_kitchen / sensor_bedroom).\n3. At least one device reports "battery" and "linkquality".\nReport each as a check with the concrete value seen (e.g. "sensor_kitchen temperature=27.7"). If the bridge is unreachable, FAIL the dimension and say so plainly (the Pi may be offline again).`,
    { label: 'verify:bridge', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
  // D2 — endpoint shape & reachability (both interfaces)
  () => agent(
    `Verify the GET /home/sensors endpoint on BOTH interfaces.\n\n${NET_HINT}\n\nDimension "endpoint". Hit both:\n  curl -s --max-time 8 -w "\\n%{http_code}" ${API_LOCAL}/home/sensors\n  curl -s --max-time 8 -w "\\n%{http_code}" ${API_WSL}/home/sensors   (this is the interface Peter/WSL uses)\nPASS checks:\n1. Both return HTTP 200.\n2. Body has top-level "sensors" (array), "count" (>0), "bridge" == "${BRIDGE}", and a "fetched_at" ISO timestamp.\n3. Every sensor row has keys: id, room, temperature_c, humidity_pct, occupancy, illuminance_lux, battery_pct, link_quality.\n4. A friendly room name is derived (e.g. "Kitchen", "Bedroom", "Lounge") — NOT the raw key.\n5. Null handling: at least one sensor (the lounge motion sensor) has temperature_c=null but occupancy populated, and is NOT dropped or rendered as 0.\nQuote the rooms + temps seen. FAIL any check that does not hold.`,
    { label: 'verify:endpoint', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
  // D3 — static wiring (skill, manifest, docs, route, service, bot)
  () => agent(
    `Verify the static wiring of the home-sensors feature by reading files under "${ROOT}". Use Read/Grep (no network).\n\nDimension "wiring". PASS checks:\n1. domains/peterbot/wsl_config/skills/manifest.json is valid JSON and has a "home-sensors" entry with a non-empty triggers array, conversational:true.\n2. domains/peterbot/wsl_config/skills/home-sensors/SKILL.md exists and contains an explicit INDOOR-vs-outdoor routing rule that points outdoor questions to the weather skill and references GET /home/sensors.\n3. hadley_api/peter_routes/home_sensors.py exists, defines an APIRouter with prefix "/home" and a GET "/sensors" handler delegating to domains.home_sensors.service.get_sensors.\n4. domains/home_sensors/service.py defines get_sensors, watchdog_once, register_monitor, and BRIDGE_URL.\n5. bot.py imports register_monitor from domains.home_sensors.service and calls it during scheduler setup.\n6. hadley_api/README.md documents GET /home/sensors under "EV & Home".\n7. The existing weather skill STILL owns outdoor triggers in manifest.json (regression check — home-sensors must not have removed/altered it).\nQuote a line of evidence per check. FAIL any that do not hold.`,
    { label: 'verify:wiring', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
  // D4 — watchdog registered in the RUNNING bot + compiles clean
  () => agent(
    `Verify the bridge watchdog is live in the running bot and the code compiles.\n\n${NET_HINT}\n\nDimension "watchdog". Checks:\n1. py_compile clean: run (sandbox disabled, cwd "${ROOT}")  python -m py_compile domains/home_sensors/service.py hadley_api/peter_routes/home_sensors.py bot.py  → exit 0.\n2. The running DiscordBot registered the watchdog: today's log at "%LOCALAPPDATA%/discord-assistant/logs/<YYYY-MM-DD>.log" (resolve via: cd "${ROOT}" && python -c "from config import LOG_DIR;print(LOG_DIR)") contains a recent line "Home-sensors watchdog registered (every 5m)". Grep for it and quote the timestamped line.\n3. No "home_sensors"/"home-sensors" ERROR/traceback lines in that same log.\n4. Failure-path sanity (no real alert spam): run a python one-liner from "${ROOT}" that sets domains.home_sensors.service.BRIDGE_URL to a dead port (e.g. http://127.0.0.1:1) and calls watchdog_once() ONCE — it must return {"ok": false, ...} and NOT raise. (Calling once stays below the 3-strike alert threshold, so nothing is posted.)\nFAIL any check that does not hold.`,
    { label: 'verify:watchdog', phase: 'Verify', schema: CHECK_SCHEMA }
  ),
])).filter(Boolean)

phase('Adversarial re-check')
const verdicts = (await parallel([
  // S1 — is the endpoint serving LIVE bridge data, or a stale/baked snapshot?
  () => agent(
    `Adversarially verify this claim and try hard to REFUTE it:\n  "GET /home/sensors serves data read live from the bridge at request time, not a cached/baked snapshot."\nDefault refuted=true unless your OWN evidence proves it true.\n\n${NET_HINT}\n\nIndependent method:\n1. Hit the bridge directly (${BRIDGE}) and the endpoint (${API_LOCAL}/home/sensors) back-to-back. For each room the bridge reports a temperature, the endpoint's temperature_c must MATCH the bridge value (same number).\n2. The endpoint's "fetched_at" must be within ~60 seconds of now (UTC) — prove it is freshly generated per request, e.g. by calling the endpoint twice a few seconds apart and observing fetched_at advance.\nIf temps match the live bridge AND fetched_at advances between calls, the claim STANDS (refuted=false). Otherwise refuted=true.`,
    { label: 'skeptic:liveness', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
  // S2 — does the watchdog actually DETECT a down bridge (the silent-failure we are fixing)?
  () => agent(
    `Adversarially verify this claim and try hard to REFUTE it:\n  "The watchdog detects an unreachable bridge (get_sensors raises -> watchdog_once returns ok:false) and would alert after 3 consecutive failures."\nDefault refuted=true unless your OWN evidence proves it true.\n\n${NET_HINT}\n\nIndependent method (no real #alerts spam): from "${ROOT}", in a python subprocess, import domains.home_sensors.service as s; set s.BRIDGE_URL='http://127.0.0.1:1' AND s.HADLEY_ALERT_URL='http://127.0.0.1:1/alert' (so even if an alert were attempted it goes nowhere); reset s._fail_count=0; assert get_sensors() raises; then call s.watchdog_once() TWICE and confirm each returns ok:false and s._fail_count increments (1 then 2, staying below the DOWN_ALERT_AFTER=3 threshold so nothing posts). Also read the source to confirm the alert fires exactly when _fail_count==DOWN_ALERT_AFTER and that get_sensors uses a per-request httpx.get (no module-level cache). Report whether the down-detection logic holds.`,
    { label: 'skeptic:down-detect', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
  // S3 — indoor vs outdoor routing won't collide/misroute
  () => agent(
    `Adversarially verify this claim and try hard to REFUTE it:\n  "Peter will route INDOOR temperature questions to home-sensors and OUTDOOR ones to weather, without the new skill breaking the existing weather skill."\nDefault refuted=true unless your OWN evidence proves it true.\n\nNo network. Read under "${ROOT}":\n- domains/peterbot/wsl_config/skills/manifest.json (compare the "weather" and "home-sensors" entries: triggers + descriptions).\n- domains/peterbot/wsl_config/skills/home-sensors/SKILL.md and skills/weather/SKILL.md.\nRefute if: (a) home-sensors and weather share enough identical triggers that routing is genuinely ambiguous with NO disambiguating guidance, OR (b) the home-sensors change altered/removed weather's triggers, OR (c) the SKILL.md lacks a clear indoor/outdoor rule. The claim STANDS only if both skills coexist, home-sensors is clearly scoped to indoor/room/humidity with an explicit "outdoor -> weather" rule, and weather is untouched. Quote the decisive lines.`,
    { label: 'skeptic:routing', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
])).filter(Boolean)

phase('Synthesize')
const report = await agent(
  `Write a tight end-to-end verification report (GitHub-flavored markdown) for the home temperature-sensor feature.\n\nDIMENSION RESULTS:\n${JSON.stringify(dims, null, 2)}\n\nINDEPENDENT ADVERSARIAL VERDICTS:\n${JSON.stringify(verdicts, null, 2)}\n\nProduce:\n- A first line: "**Overall: PASS**" or "**Overall: FAIL**". PASS only if EVERY dimension status is PASS AND no adversarial verdict has refuted=true.\n- A markdown table of dimensions: Dimension | Status | Summary.\n- A markdown table of the individual checks across all dimensions: Check | Status | Evidence (evidence ~12 words).\n- An "Independent cross-check" section: one bullet per verdict — the claim, stood/refuted, and key evidence/method.\n- A final "Discrepancies / caveats:" line — anything the adversarial pass disagreed with, residual risks (e.g. depends on the Pi staying on WiFi), or "none".\nReturn ONLY the markdown, no preamble.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return { dims, verdicts, report }

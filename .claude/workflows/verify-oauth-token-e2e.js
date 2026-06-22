export const meta = {
  name: 'verify-oauth-token-e2e',
  description: 'End-to-end verification of the static OAuth token fix (PR #26): run the check suite, adversarially re-prove the riskiest claims independently, synthesize a PASS/FAIL report',
  phases: [
    { title: 'Run suite', detail: 'execute scripts/verify-oauth-token.sh and parse each check' },
    { title: 'Adversarial re-check', detail: 'independently re-prove the riskiest claims with different methods' },
    { title: 'Synthesize', detail: 'combine into a final PASS/FAIL report' },
  ],
}

const SCRIPT = '/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/scripts/verify-oauth-token.sh'

const RUN_HINT = [
  'Environment: Windows Git Bash with a Bash tool; the services run in WSL.',
  "Run WSL commands as: wsl -d Ubuntu -- bash -lc '<cmd>'.",
  'CRITICAL gotcha: literal /mnt/c/... paths (they contain a space) get MANGLED by Git Bash inside command strings and silently blank out.',
  '- For WSL-native paths (/proc, $HOME/.claude, localhost curl, tmux) inline `wsl bash -lc` is safe.',
  '- When you MUST reference a /mnt/c path (e.g. the suite script), run it as a file with MSYS_NO_PATHCONV=1:',
  `    MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash "${SCRIPT}"`,
  'Ignore any "your ... screen size is bogus" warning line.',
].join('\n')

const SUITE_SCHEMA = {
  type: 'object',
  properties: {
    overall: { type: 'string', enum: ['PASS', 'FAIL'] },
    pass_count: { type: 'number' },
    fail_count: { type: 'number' },
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
    raw_result_line: { type: 'string' },
  },
  required: ['overall', 'pass_count', 'fail_count', 'checks'],
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

phase('Run suite')
const suite = await agent(
  `Run the end-to-end verification suite and report its results verbatim.\n\n${RUN_HINT}\n\nExecute exactly:\n  MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash "${SCRIPT}"\n\nIt prints one line per check ("  PASS  <name>" / "  FAIL  <name>") grouped under "== [n] <section> ==" headers, then a final "RESULT pass=N fail=M overall=PASS|FAIL" line. Parse EVERY check line into {name, status, evidence} (fold the section header into evidence for context), set pass_count/fail_count/overall from the RESULT line, and put that line in raw_result_line. Do not editorialize — report exactly what the script output.`,
  { label: 'suite', phase: 'Run suite', schema: SUITE_SCHEMA }
)

phase('Adversarial re-check')
const verdicts = (await parallel([
  () => agent(
    `Adversarially verify, WITHOUT running scripts/verify-oauth-token.sh, this claim:\n  "All 5 WSL channel claude processes authenticate via the STATIC token (CLAUDE_CODE_OAUTH_TOKEN env var), NOT the old rotating ~/.claude/.credentials.json."\nTry hard to REFUTE it. Default refuted=true unless your OWN evidence proves it true.\n\n${RUN_HINT}\n\nIndependent method (all WSL-native — no /mnt/c literals):\n1. Scan /proc for the 5 channel claude processes by matching "server:<name>" in /proc/<pid>/cmdline for: peter-channel, whatsapp-channel, jobs-channel, jobs-channel-sonnet, extract-channel. For each, confirm CLAUDE_CODE_OAUTH_TOKEN is present in /proc/<pid>/environ (tr '\\0' '\\n' < /proc/<pid>/environ | grep). All 5 must be present.\n2. Extract the token VALUE from one channel process's environ, then prove THAT token authenticates by itself in an isolated empty config dir:\n   wsl -d Ubuntu -- bash -lc 'export PATH=$HOME/.local/bin:$PATH; T=$(mktemp -d); CLAUDE_CONFIG_DIR="$T" CLAUDE_CODE_OAUTH_TOKEN="<paste-token>" timeout 120 claude -p --model claude-haiku-4-5 --permission-mode bypassPermissions "Reply with exactly: TOKEN_OK" </dev/null; rm -rf "$T"'  → expect TOKEN_OK.\n3. Confirm ~/.claude/.credentials.json mtime is NOT recent (channels are not rewriting it): stat -c %Y on it vs now.\nReturn the verdict (refuted true means the claim FAILED).`,
    { label: 'skeptic:token-source', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
  () => agent(
    `Adversarially verify, WITHOUT running scripts/verify-oauth-token.sh, this claim:\n  "The live scheduled-job path authenticates end-to-end right now."\nTry hard to REFUTE it. Default refuted=true unless your OWN evidence proves it true.\n\n${RUN_HINT}\n\nIndependent method (localhost / WSL-native — no /mnt/c literals):\n1. Fresh POST to the jobs channel:\n   wsl -d Ubuntu -- bash -lc 'curl -s --max-time 30 -X POST http://localhost:8103/job -H "Content-Type: application/json" --data-raw "{\\"skill\\":\\"auth-test\\",\\"context\\":\\"Reply with exactly AUTH_OK and nothing else.\\"}"'  → expect a JSON body containing AUTH_OK.\n2. Same against the Sonnet jobs channel on port 8105.\n3. Grep each channel tmux pane tail (peter/whatsapp/jobs/jobs-channel-sonnet/extract) for "Please run /login" or "401 Invalid authentication credentials" — there should be NONE.\nReturn the verdict (refuted true means the claim FAILED).`,
    { label: 'skeptic:e2e-jobs', phase: 'Adversarial re-check', schema: VERDICT_SCHEMA }
  ),
])).filter(Boolean)

phase('Synthesize')
const report = await agent(
  `Write a tight end-to-end verification report (GitHub-flavored markdown) for the static OAuth token fix (PR #26).\n\nSUITE RESULT (scripts/verify-oauth-token.sh):\n${JSON.stringify(suite, null, 2)}\n\nINDEPENDENT ADVERSARIAL VERDICTS:\n${JSON.stringify(verdicts, null, 2)}\n\nProduce:\n- A first line: "**Overall: PASS**" or "**Overall: FAIL**". PASS only if the suite overall is PASS AND no adversarial verdict has refuted=true.\n- A markdown table of the suite checks: Check | Status | Evidence (keep evidence to ~10 words).\n- A short "Independent cross-check" section: one bullet per verdict — the claim, whether it stood (not refuted) or was refuted, and the key evidence/method.\n- A final "Discrepancies / caveats:" line — note any place the independent method disagreed with the suite, or "none".\nReturn ONLY the markdown, no preamble.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return { suite, verdicts, report }

export const meta = {
  name: 'verify-changes',
  description: 'Adversarially verify recent changes: one agent per change area, regression checks for removals',
  whenToUse: 'After implementing a batch of changes (features, fixes, deletions) — before declaring them done. Pass a commit range or description as args, e.g. "HEAD~5..HEAD" or "the daily-batch feature and the keepalive removal". Defaults to uncommitted changes + last 3 commits.',
  phases: [
    { title: 'Scope', detail: 'map the change set into independent areas' },
    { title: 'Verify', detail: 'one adversarial verifier per area' },
    { title: 'Synthesize', detail: 'merge verdicts, list blockers/warnings' },
  ],
}

const SCOPE_SCHEMA = {
  type: 'object',
  required: ['areas'],
  properties: {
    areas: {
      type: 'array',
      items: {
        type: 'object',
        required: ['key', 'kind', 'summary'],
        properties: {
          key: { type: 'string', description: 'short kebab-case id' },
          kind: { type: 'string', enum: ['feature', 'fix', 'removal', 'refactor', 'config', 'docs'] },
          summary: { type: 'string', description: '2-4 sentences: what changed, which files/commits, what correct behaviour looks like' },
          files: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['item', 'pass', 'findings'],
  properties: {
    item: { type: 'string' },
    pass: { type: 'boolean' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'description'],
        properties: {
          severity: { type: 'string', enum: ['blocker', 'warning', 'info'] },
          description: { type: 'string' },
          file: { type: 'string' },
        },
      },
    },
    evidence: { type: 'string', description: 'what you actually ran/checked' },
  },
}

const scope = (typeof args === 'string' && args.trim())
  ? `the changes described as: "${args.trim()}" (resolve this against git log/diff yourself)`
  : 'all uncommitted changes plus the last 3 commits (git status --short; git log -3 --stat; git diff HEAD~3)'

phase('Scope')
const scoped = await agent(
  `You are scoping a verification pass over a repo's recent changes. Examine ${scope} in the current repository using git (log, diff, show) and the files themselves. Group the change set into INDEPENDENT areas that can each be verified by a separate agent — one area per feature/fix/removal, not per file. For each area, write a summary precise enough that a verifier who has NOT seen this conversation can test it: what changed, where, and what correct behaviour looks like. Mark deletions/removals as kind=removal — they get regression checks (dangling references) rather than feature checks. Keep it to at most 10 areas; merge trivial ones.`,
  { label: 'scope-changes', phase: 'Scope', schema: SCOPE_SCHEMA }
)

const COMMON = `You are ADVERSARIALLY verifying a recent change in the current repository. Actively try to prove it broken, half-wired, or quietly harmful — do not rubber-stamp. Run real commands (python/node/grep/git, syntax checks, live HTTP probes where the project exposes them) rather than just reading code; on Windows use PYTHONIOENCODING=utf-8 and quote paths. Do NOT modify any files. Severity: blocker = actually broken or regressed; warning = works but fragile/incomplete; info = observation.`

phase('Verify')
const results = await parallel((scoped?.areas || []).map(a => () =>
  agent(
    a.kind === 'removal'
      ? `${COMMON}\nREGRESSION-TEST this removal: ${a.summary}\nFiles/areas: ${(a.files || []).join(', ')}\nChecks: grep the whole repo (excluding docs/__pycache__/node_modules/worktrees) for dangling references to the removed names — registries, schedules, configs, imports, scripts; import/compile every module that referenced them; confirm whatever replaced the removed thing actually covers its job; check nothing consumed the removed thing's output.`
      : `${COMMON}\nVERIFY this ${a.kind}: ${a.summary}\nFiles: ${(a.files || []).join(', ')}\nChecks: does it actually do what the summary says (execute it or its tests where possible); edge cases (empty input, error paths, malformed data); is it fully wired (registries, schedules, docs the project treats as config); could it silently no-op (verify the success path produces a real observable effect, not just an absence of errors)?`,
    { label: `verify:${a.key}`, phase: 'Verify', schema: VERDICT_SCHEMA }
  )
))

phase('Synthesize')
const all = results.filter(Boolean)
const blockers = all.flatMap(r => (r.findings || []).filter(f => f.severity === 'blocker').map(f => ({ item: r.item, ...f })))
const warnings = all.flatMap(r => (r.findings || []).filter(f => f.severity === 'warning').map(f => ({ item: r.item, ...f })))
log(`${all.length} areas verified: ${all.filter(r => r.pass).length} pass, ${blockers.length} blockers, ${warnings.length} warnings`)
return { areas: scoped?.areas?.length || 0, results: all, blockers, warnings }

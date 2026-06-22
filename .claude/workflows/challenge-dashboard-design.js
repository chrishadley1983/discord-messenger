export const meta = {
  name: 'challenge-dashboard-design',
  description: 'Adversarially challenge the Reset Cut dashboard redesign across 7 design lenses, independently verify each finding, synthesize a prioritized punch-list + an honest "does it still look AI-generated" verdict',
  whenToUse: 'After redesigning the fitness dashboard, to stress-test the visual design before shipping. Reads rendered screenshots (desktop+mobile) + the template source.',
  phases: [
    { title: 'Critique', detail: 'one senior-designer critic per lens, in parallel' },
    { title: 'Verify', detail: 'independently confirm each finding is real and worth acting on' },
    { title: 'Synthesize', detail: 'dedupe + rank into an actionable punch-list' },
  ],
}

// ---- inputs (override via args) -------------------------------------------
const ROOT = 'C:/Users/Chris Hadley/claude-projects/discord-messenger'
const SHOTS = (args && args.shotsDir) || `${ROOT}/data/tmp/dashboard-shots`
const TEMPLATE = (args && args.template) || `${ROOT}/domains/fitness/dashboard_template.html`
const DESKTOP = ['today', 'progress', 'trends', 'training', 'targets'].map(s => `${SHOTS}/desktop-${s}.png`)
const MOBILE = ['today', 'progress'].map(s => `${SHOTS}/mobile-${s}.png`)
const SHOTLIST = [...DESKTOP, ...MOBILE].join('\n')

const GOALS = [
  'DESIGN GOALS for the "Reset Cut" personal fitness dashboard:',
  '- Modern, EDITORIAL aesthetic; must NOT look like a generic AI-generated dark dashboard or a template.',
  '- Latest status, trends, and progress must be readable at a glance (<5s).',
  '- Highly motivational/supportive — the user is tapering an antidepressant, so framing must be encouraging, never guilt-trippy.',
  '- KEY STEER: the CURRENT scale reading and the 7-DAY TREND must BOTH be super clear AND visually distinct (never confusable).',
].join('\n')

const LENSES = [
  { key: 'hierarchy', brief: 'Visual hierarchy & glanceability — can a user read latest status, trend and progress within 5 seconds? Is the eye guided? Any competing focal points or dead zones?' },
  { key: 'ai-slop', brief: 'AI-slop detector — does ANY part look generic, templated or AI-generated? Be ruthless: call out default-looking spacing, component shapes, predictable layouts, stock patterns, anything that betrays a non-bespoke origin.' },
  { key: 'motivation', brief: 'Motivational psychology — does it motivate WITHOUT guilt-tripping (antidepressant taper context)? How does it frame an up-day, a "behind" status, and "0 kg lost" in week 1? Flag any demotivating or clinical-cold moment.' },
  { key: 'current-vs-trend', brief: 'THE KEY STEER — are the current scale reading and the 7-day trend BOTH super clear AND unmistakably distinct (colour, label, size, position)? Could a tired user at a glance confuse which is which? Is the gap between them explained?' },
  { key: 'typography', brief: 'Editorial craft — the Fraunces (serif) + Archivo pairing, type scale, vertical rhythm, alignment, colour discipline, use of hairline rules and whitespace. Does it feel intentionally art-directed or accidental?' },
  { key: 'a11y', brief: 'Accessibility & contrast — paper/ink body contrast and status-colour contrast vs WCAG AA; status conveyed by colour alone; tap-target sizes; mobile stacking; legibility of the smallest text.' },
  { key: 'dataviz', brief: 'Data-viz integrity — the raw-vs-trend weight overlay (is the distinction legible?), chart axis legibility, delta badges (is up/down coloured as good/bad correctly per metric?), the small-multiple charts.' },
]

const FINDING_SCHEMA = {
  type: 'object',
  properties: {
    lens_summary: { type: 'string', description: '1-2 sentences: overall read on this lens' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          section: { type: 'string', description: 'which view/element, e.g. "Today hero", "Progress weight chart", "mobile masthead"' },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
          problem: { type: 'string' },
          fix: { type: 'string', description: 'concrete, implementable fix (CSS/markup level where possible)' },
          confidence: { type: 'number' },
        },
        required: ['title', 'section', 'severity', 'problem', 'fix'],
      },
    },
    strengths: { type: 'array', items: { type: 'string' }, description: 'what genuinely works on this lens — preserve these' },
  },
  required: ['lens_summary', 'findings'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    title: { type: 'string' },
    is_real: { type: 'boolean', description: 'true only if a real user would genuinely benefit from the fix' },
    actionable: { type: 'boolean' },
    severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
    verdict: { type: 'string', description: 'why you confirmed or rejected it, citing what you saw' },
    fix: { type: 'string', description: 'the sharpest version of the fix (may refine the proposed one)' },
  },
  required: ['title', 'is_real', 'severity', 'verdict'],
}

const SYNTH_SCHEMA = {
  type: 'object',
  properties: {
    overall: { type: 'string', description: '3-5 sentence verdict on the redesign' },
    looks_ai_generated: { type: 'string', enum: ['no', 'borderline', 'yes'] },
    ai_reasoning: { type: 'string' },
    meets_current_vs_trend_steer: { type: 'boolean' },
    strengths: { type: 'array', items: { type: 'string' } },
    punch_list: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          rank: { type: 'number' },
          title: { type: 'string' },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
          section: { type: 'string' },
          fix: { type: 'string' },
          effort: { type: 'string', enum: ['trivial', 'small', 'medium', 'large'] },
        },
        required: ['rank', 'title', 'severity', 'fix'],
      },
    },
  },
  required: ['overall', 'looks_ai_generated', 'punch_list'],
}

// ---- Phase 1: critique (parallel, one lens each) --------------------------
phase('Critique')
const crit = (await parallel(LENSES.map(L => () =>
  agent(
    `You are a senior product designer doing a critical review of a personal fitness dashboard redesign through ONE lens only:\n\n${L.brief}\n\n${GOALS}\n\nRENDERED SCREENSHOTS to read (desktop 1280px + mobile 390px):\n${SHOTLIST}\n\nSOURCE for implementation detail (read after the images): ${TEMPLATE}\n\nReturn 2-6 concrete findings through your lens. Name the exact section/element. Each finding needs an implementable fix. Be honest about what already works (strengths). Only raise issues a real user would feel — quality over quantity.`,
    { label: `critique:${L.key}`, phase: 'Critique', schema: FINDING_SCHEMA },
  ),
))).filter(Boolean)

const findings = crit.flatMap((c, i) => (c.findings || []).map(f => ({ ...f, lens: LENSES[i].key })))
log(`${findings.length} findings across ${crit.length} lenses`)

// ---- Phase 2: independent verification (barrier before synthesis) ---------
phase('Verify')
const verds = (await parallel(findings.map(f => () =>
  agent(
    `Independently verify this design finding against the actual screenshots + source. Be SKEPTICAL — confirm is_real only if a real user would genuinely benefit. Reject vague, contradictory, or taste-only nits that don't fit the editorial direction.\n\nFINDING: ${f.title}\nLENS: ${f.lens}\nSECTION: ${f.section}\nPROBLEM: ${f.problem}\nPROPOSED FIX: ${f.fix}\n\n${GOALS}\n\nScreenshots:\n${SHOTLIST}\nSource: ${TEMPLATE}`,
    { label: `verify:${(f.section || f.lens).slice(0, 16)}`, phase: 'Verify', schema: VERDICT_SCHEMA },
  ).then(v => v && ({ ...v, lens: f.lens, section: f.section })),
))).filter(Boolean)

const confirmed = verds.filter(v => v.is_real)
log(`${confirmed.length}/${verds.length} findings confirmed real`)

// ---- Phase 3: synthesize a ranked punch-list ------------------------------
phase('Synthesize')
const synth = await agent(
  `You are the design director making the final call on the dashboard redesign. Below are independently-verified findings. Produce: an overall verdict, an HONEST call on whether it still looks AI-generated (no/borderline/yes) with reasoning, whether the current-vs-trend steer is met, the strengths to preserve, and a prioritized punch-list (highest user-impact first, with effort estimates).\n\n${GOALS}\n\nCONFIRMED FINDINGS (JSON):\n${JSON.stringify(confirmed, null, 1)}\n\nSTRENGTHS NOTED BY CRITICS:\n${JSON.stringify(crit.flatMap(c => c.strengths || []))}`,
  { label: 'synthesize', phase: 'Synthesize', schema: SYNTH_SCHEMA },
)

return {
  findings_total: findings.length,
  confirmed_real: confirmed.length,
  synthesis: synth,
}

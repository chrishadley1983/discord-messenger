export const meta = {
  name: 'verify-fitness-health-e2e',
  description: 'End-to-end validation of the fitness check-in trend/protein fix, the weekly-health nutrition averaging, and the Garmin per-row sync (partial-day non-clobber). Probes the live system + runs the tests, then adversarially re-proves the riskiest claims by an independent method and synthesises PASS/FAIL.',
  phases: [
    { title: 'Verify', detail: 'one agent per fixed behaviour, against the live system + tests' },
    { title: 'Adversarial', detail: 're-prove the two riskiest claims by an independent method' },
    { title: 'Synthesize', detail: 'consolidate verdicts into a PASS/FAIL report' },
  ],
}

const PROJ = "C:/Users/Chris Hadley/claude-projects/discord-messenger"

const VERDICT = {
  type: 'object',
  additionalProperties: false,
  properties: {
    claim: { type: 'string' },
    status: { type: 'string', enum: ['PASS', 'FAIL', 'WARN'] },
    evidence: { type: 'string', description: 'concrete numbers / command output that prove the verdict' },
    notes: { type: 'string' },
  },
  required: ['claim', 'status', 'evidence'],
}

const CHECKS = [
  {
    key: 'nutrition-averaging',
    prompt: `Validate an end-to-end fix in the repo at ${PROJ} (run commands in Git Bash).

FIX UNDER TEST: the weekly health summary now (a) EXCLUDES incomplete-tracking days (under 600 kcal logged) from the nutrition averages, surfacing them under incomplete_days, and (b) counts "protein days hit" against the LIVE programme protein target (~125 g), not a hardcoded 144 g.

Run:
cd '${PROJ}' && timeout 170 python -c "
import asyncio, json
from dotenv import load_dotenv; load_dotenv('.env')
from domains.peterbot.data_fetchers import get_weekly_health_data
async def m():
    d = await get_weekly_health_data(); n = d['nutrition']; t = d['targets']
    print(json.dumps({'days_tracked': n.get('days_tracked'), 'avg_calories': n.get('avg_calories'), 'avg_protein': n.get('avg_protein'), 'protein_days_hit': n.get('protein_days_hit'), 'protein_target_used': n.get('protein_target_used'), 'incomplete_days': n.get('incomplete_days'), 'live_protein_target': t.get('protein_g')}))
asyncio.run(m())
"

PASS criteria: protein_target_used == live_protein_target (~125) and is NOT 144 or 160; every entry in incomplete_days has calories < 600; days_tracked counts only properly-logged days (no <600 kcal day counted). status=FAIL if protein_target_used is 144/160, if a <600 kcal day is in days_tracked, or the call errors. Evidence = the actual numbers.`,
  },
  {
    key: 'garmin-populated',
    prompt: `Validate that garmin_daily_summary is populated for the past week in repo ${PROJ}. The bug was it being EMPTY, so the weekly summary said "No data this week" for Activity/Sleep/Resting HR even though Garmin had the data.

Run:
cd '${PROJ}' && python -c "
import os, httpx, json
from datetime import datetime, timedelta
from dotenv import load_dotenv; load_dotenv('.env')
u=os.environ['SUPABASE_URL']; k=os.environ['SUPABASE_KEY']; h={'apikey':k,'Authorization':'Bearer '+k}
since=(datetime.now()-timedelta(days=8)).date().isoformat()
r=httpx.get(u+'/rest/v1/garmin_daily_summary', headers=h, params={'select':'date,steps,sleep_hours,sleep_score,resting_hr','user_id':'eq.chris','date':'gte.'+since,'order':'date.asc'}, timeout=20)
print(json.dumps(r.json()))
"

PASS criteria: rows exist for most of the last ~7 days, and every PAST day (all rows except possibly the latest/today) has non-null sleep_hours AND resting_hr AND steps. It is fine for the most recent/today row to have steps=null. FAIL if the table is empty or past days have null sleep/HR/steps. Evidence = the row list.`,
  },
  {
    key: 'garmin-non-clobber',
    prompt: `Adversarially prove the Garmin sync does NOT clobber already-stored data when it re-runs — the partial-day safety guarantee. The sync must upsert ONE row per day sending only non-null fields, so re-running (including for a partial 'today') never nulls a value a prior sync stored. Repo: ${PROJ}.

1) Read a recent PAST day's stored values (3 days ago):
cd '${PROJ}' && python -c "
import os, httpx, json
from datetime import datetime, timedelta
from dotenv import load_dotenv; load_dotenv('.env')
u=os.environ['SUPABASE_URL']; k=os.environ['SUPABASE_KEY']; h={'apikey':k,'Authorization':'Bearer '+k}
d=(datetime.now()-timedelta(days=3)).date().isoformat()
r=httpx.get(u+'/rest/v1/garmin_daily_summary', headers=h, params={'select':'date,steps,sleep_hours,resting_hr','user_id':'eq.chris','date':'eq.'+d}, timeout=20)
print('BEFORE', d, json.dumps(r.json()))
"

2) Re-run the sync, then re-read the same day:
cd '${PROJ}' && timeout 150 python -c "
import asyncio, os, httpx, json
from datetime import datetime, timedelta
from dotenv import load_dotenv; load_dotenv('.env')
from domains.peterbot.data_fetchers import _sync_garmin_to_supabase
async def m():
    await _sync_garmin_to_supabase('e2e', days=8)
    u=os.environ['SUPABASE_URL']; k=os.environ['SUPABASE_KEY']; h={'apikey':k,'Authorization':'Bearer '+k}
    d=(datetime.now()-timedelta(days=3)).date().isoformat()
    r=httpx.get(u+'/rest/v1/garmin_daily_summary', headers=h, params={'select':'date,steps,sleep_hours,resting_hr','user_id':'eq.chris','date':'eq.'+d}, timeout=20)
    print('AFTER', d, json.dumps(r.json()))
asyncio.run(m())
"

3) Confirm the implementation in domains/peterbot/data_fetchers.py drops null fields per row (look for: payload = {k: v for k, v in rec.items() if v is not None}) and posts ONE record at a time (NOT a bulk list/array).

PASS if the past day's steps/sleep_hours/resting_hr are non-null and IDENTICAL before vs after, AND the code drops nulls per row. FAIL if any value changed/nulled, or the code bulk-posts the array. Evidence = BEFORE/AFTER numbers + the code line.`,
  },
  {
    key: 'checkin-protein-trend',
    prompt: `Validate the daily fitness check-in (advisor) in repo ${PROJ}. Run:
curl -s http://localhost:8100/fitness/advice

From the JSON:
- snapshot.protein.target must be 125 (the live fat-loss floor), NOT 180.
- NO item in advice[] may have a headline containing 'too fast' (the spurious "losing too fast" warning must be gone in week 1).
- snapshot.slope_kg_per_week must be null (gated — too few days since programme start) OR, if non-null, correspond to a >=10-day window.
Also confirm domains/fitness/trend.py defines MIN_SLOPE_DAYS = 10 and only computes the slope when the window clears it.

PASS if all hold. FAIL otherwise. Evidence = protein target, slope value, and the list of advice headlines.`,
  },
  {
    key: 'dashboard-consistency',
    prompt: `Validate that the dashboard and the check-in now AGREE on the weight trend in repo ${PROJ}. The bug: the check-in said "-1.3 kg/wk losing too fast" while the dashboard hero said "+0.3 / settling".

Run all three:
curl -s http://localhost:8100/fitness/advice          (read snapshot.slope_kg_per_week)
curl -s http://localhost:8100/fitness/dashboard        (read weight.slope_kg_per_week)
curl -s http://localhost:8100/fitness/dashboard/page    (find the hero "slope" value in the embedded JSON / HTML)

PASS if the advice slope and dashboard JSON slope are EQUAL (both null in week 1) AND the rendered page hero slope is consistent (shows an em-dash "—" / no weekly rate when slope is null). FAIL if they disagree in sign/magnitude as before. Evidence = the three slope values.`,
  },
  {
    key: 'tests',
    prompt: `Run the fitness test suite from ${PROJ}:
cd '${PROJ}' && python -m pytest tests/fitness/ -q

PASS if every test passes (expect ~157). Then confirm these three regression tests specifically exist and passed (use -k or grep the files):
- test_short_window_reports_no_slope (tests/fitness/test_trend.py)
- test_sync_upserts_each_record (tests/fitness/test_advisor_integration.py)
- test_sync_omits_null_fields_so_partial_days_dont_clobber (tests/fitness/test_advisor_integration.py)
Evidence = the pytest summary line + confirmation the 3 named tests ran/passed. FAIL on any failure.`,
  },
]

phase('Verify')
const verdicts = await parallel(
  CHECKS.map(c => () => agent(c.prompt, { label: `verify:${c.key}`, phase: 'Verify', schema: VERDICT }))
)

phase('Adversarial')
const adversarial = await parallel([
  () => agent(
    `Independently re-prove (do NOT trust the application code) that the weekly nutrition average EXCLUDES sub-600-kcal partial days, in repo ${PROJ}. Query raw nutrition_logs for the last 7 days, aggregate per day yourself, then compute TWO averages: over ALL days, and over only days with >=600 kcal.

cd '${PROJ}' && python -c "
import os, httpx, json
from datetime import datetime, timedelta
from dotenv import load_dotenv; load_dotenv('.env')
u=os.environ['SUPABASE_URL']; k=os.environ['SUPABASE_KEY']; h={'apikey':k,'Authorization':'Bearer '+k}
start=(datetime.now()-timedelta(days=7)).date().isoformat(); end=datetime.now().date().isoformat()
r=httpx.get(u+'/rest/v1/nutrition_logs', headers=h, params={'select':'logged_at,calories','and':'(logged_at.gte.'+start+'T00:00:00,logged_at.lt.'+end+'T00:00:00)'}, timeout=20)
daily={}
for x in r.json():
    d=x['logged_at'][:10]; daily.setdefault(d,0.0); daily[d]+=x.get('calories') or 0
allv=list(daily.values()); logged=[v for v in allv if v>=600]
print('per_day', json.dumps({d:round(v) for d,v in sorted(daily.items())}))
print('avg_all', round(sum(allv)/len(allv)) if allv else None, '| avg_logged_only', round(sum(logged)/len(logged)) if logged else None, '| excluded', [round(v) for v in allv if v<600])
"

Then get the app's reported avg_calories via get_weekly_health_data (domains.peterbot.data_fetchers). PASS if the app's avg_calories matches YOUR avg_logged_only (NOT avg_all), proving exclusion is real. If there are no sub-600 days in the current window, PASS only if avg_all == avg_logged_only == app avg (nothing to exclude) and note that. Evidence = your two averages + the app's.`,
    { label: 'adversarial:nutrition-recompute', phase: 'Adversarial', schema: VERDICT }
  ),
  () => agent(
    `Independently confirm the user-visible weekly summary will NOT show "No data this week" for Activity/Sleep/Resting HR, in repo ${PROJ}. Call the weekly fetchers directly:

cd '${PROJ}' && timeout 150 python -c "
import asyncio, json
from dotenv import load_dotenv; load_dotenv('.env')
from jobs.weekly_health import _get_steps_week, _get_sleep_week, _get_heart_rate_week
async def m():
    s=await _get_steps_week(); sl=await _get_sleep_week(); hr=await _get_heart_rate_week()
    print(json.dumps({'steps_days':s.get('days'),'steps_avg':s.get('avg'),'sleep_days':sl.get('days'),'sleep_avg_hours':sl.get('avg_hours'),'hr_days':hr.get('days'),'hr_avg':hr.get('avg')}))
asyncio.run(m())
"

PASS if steps, sleep AND heart_rate ALL return non-empty (days>0 and a non-null avg) — i.e. none would render "No data this week". FAIL if any is empty/None. Evidence = the days+avg for each section.`,
    { label: 'adversarial:garmin-uservisible', phase: 'Adversarial', schema: VERDICT }
  ),
])

phase('Synthesize')
const all = [...verdicts, ...adversarial].filter(Boolean)
const report = await agent(
  `You are the E2E referee for the fitness check-in / weekly-health / Garmin-sync fixes. Below are independent verification verdicts as JSON:

${JSON.stringify(all, null, 2)}

Write a CONCISE markdown report:
- First line: "**E2E: PASS**" or "**E2E: FAIL**" — FAIL if ANY verdict is FAIL; PASS if all are PASS; WARN entries are allowed in a PASS but must be called out.
- A table: Check | Status | Evidence (one tight line each).
- Then 1-3 bullets: anything needing attention (WARN/FAIL), or if all clean, the single most important thing proven.
Keep it under ~25 lines. Do not invent results not present in the verdicts.`,
  { label: 'synthesize', phase: 'Synthesize' }
)
return report

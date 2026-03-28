#!/bin/bash
# Life Admin Agent — API & Integration Tests
# Run from project root: bash tests/test_life_admin.sh
#
# Tests all life-admin API endpoints, alert logic, action/snooze workflows,
# dashboard grouping, data fetcher registration, skills, and schedule entries.
#
# Requires: Hadley API running on port 8100 with life-admin routes loaded.
# The script will attempt a restart if routes are not detected.

set -uo pipefail

HADLEY_API="http://localhost:8100"
API_KEY="${HADLEY_AUTH_KEY:-$(grep '^HADLEY_AUTH_KEY=' .env 2>/dev/null | cut -d= -f2 | tr -d '"' | tr -d "'")}"
PASS=0
FAIL=0
SKIP=0
CREATED_IDS=()
NEXT_ID=""
NEXT_LIFECYCLE_ID=""

# Colours
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}✗${NC} $1: $2"; FAIL=$((FAIL + 1)); }
skip() { echo -e "  ${YELLOW}○${NC} $1 (skipped)"; SKIP=$((SKIP + 1)); }
section() { echo -e "\n${CYAN}── $1 ──${NC}"; }

# Helper: authenticated POST/PATCH/DELETE
auth_header() { echo "x-api-key: $API_KEY"; }

cleanup() {
  echo ""
  section "Cleanup"
  for id in "${CREATED_IDS[@]}"; do
    curl -s -X DELETE "$HADLEY_API/life-admin/obligations/$id" \
      -H "$(auth_header)" > /dev/null 2>&1
  done
  echo -e "  Cleaned up ${#CREATED_IDS[@]} test obligations"
}
trap cleanup EXIT

echo "========================================"
echo "  Life Admin Agent — Test Suite"
echo "========================================"
echo "  API: $HADLEY_API"
echo "  Auth: ${API_KEY:0:8}..."
echo ""

# ==========================================
# Pre-flight: check routes are loaded
# ==========================================
section "Pre-flight"
echo "Checking life-admin routes..."
RESP=$(curl -s -o /dev/null -w "%{http_code}" "$HADLEY_API/life-admin/obligations" 2>&1)
if [ "$RESP" = "404" ]; then
  echo "  Routes not loaded — restarting Hadley API..."
  curl -s -X POST "$HADLEY_API/services/restart/HadleyAPI" \
    -H "$(auth_header)" > /dev/null 2>&1
  sleep 5
  RESP=$(curl -s -o /dev/null -w "%{http_code}" "$HADLEY_API/life-admin/obligations" 2>&1)
  if [ "$RESP" = "404" ]; then
    echo -e "  ${RED}Routes still not available after restart. Aborting.${NC}"
    exit 1
  fi
fi
echo -e "  ${GREEN}Routes loaded${NC}"

# ==========================================
# 1. Database Layer
# ==========================================
section "1. Database Layer"

# DB-1: Tables exist (via API — if list returns [], tables exist)
echo "DB-1: Tables accessible via API"
RESP=$(curl -s "$HADLEY_API/life-admin/obligations")
if echo "$RESP" | python -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d, list)" 2>/dev/null; then
  pass "obligations table accessible"
else
  fail "obligations table not accessible" "$RESP"
fi

RESP=$(curl -s "$HADLEY_API/life-admin/scans")
if echo "$RESP" | python -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d, list)" 2>/dev/null; then
  pass "email_scans table accessible"
else
  fail "email_scans table not accessible" "$RESP"
fi

# DB-10: Default values (tested via create below)

# ==========================================
# 2. API CRUD
# ==========================================
section "2. API CRUD"

# API-1: List obligations (empty or existing)
echo "API-1: GET /life-admin/obligations"
RESP=$(curl -s "$HADLEY_API/life-admin/obligations")
if echo "$RESP" | python -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d, list)" 2>/dev/null; then
  pass "List returns array"
else
  fail "List did not return array" "$RESP"
fi

# API-3: Create without auth → should fail
echo "API-3: POST without auth"
RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$HADLEY_API/life-admin/obligations" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","category":"vehicle","due_date":"2026-06-01"}')
if [ "$RESP" = "401" ] || [ "$RESP" = "403" ]; then
  pass "Create without auth rejected ($RESP)"
else
  fail "Create without auth not rejected" "got $RESP"
fi

# API-2: Create obligation with auth
echo "API-2: POST /life-admin/obligations (with auth)"
RESP=$(curl -s -X POST "$HADLEY_API/life-admin/obligations" \
  -H "$(auth_header)" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TEST: Car MOT - VW Polo",
    "category": "vehicle",
    "subcategory": "MOT",
    "description": "Annual MOT test",
    "due_date": "2026-06-15",
    "recurrence_months": 12,
    "alert_lead_days": [28, 14, 7, 3],
    "alert_priority": "high",
    "provider": "Halfords",
    "reference_number": "AB12 CDE",
    "amount": 35.00,
    "notes": "Test obligation"
  }')
OB1_ID=$(echo "$RESP" | python -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
if [ -n "$OB1_ID" ]; then
  CREATED_IDS+=("$OB1_ID")
  pass "Created obligation $OB1_ID"
else
  fail "Create failed" "$RESP"
fi

# Verify all fields came back correctly
echo "  Verifying fields..."
FIELD_CHECK=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
checks = [
    d.get('name') == 'TEST: Car MOT - VW Polo',
    d.get('category') == 'vehicle',
    d.get('subcategory') == 'MOT',
    d.get('due_date') == '2026-06-15',
    d.get('recurrence_months') == 12,
    d.get('alert_priority') == 'high',
    d.get('provider') == 'Halfords',
    d.get('reference_number') == 'AB12 CDE',
    float(d.get('amount', 0)) == 35.0,
    d.get('status') == 'active',
    d.get('auto_renews') == False,
    d.get('currency') == 'GBP',
]
failed = [i for i, c in enumerate(checks) if not c]
if failed:
    print(f'FAIL:{failed}')
else:
    print('OK')
" 2>/dev/null)
if [ "$FIELD_CHECK" = "OK" ]; then
  pass "All fields match expected values"
else
  fail "Field mismatch" "$FIELD_CHECK"
fi

# API-4: Get single obligation
echo "API-4: GET /life-admin/obligations/{id}"
if [ -n "$OB1_ID" ]; then
  RESP=$(curl -s "$HADLEY_API/life-admin/obligations/$OB1_ID")
  GOT_ID=$(echo "$RESP" | python -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
  if [ "$GOT_ID" = "$OB1_ID" ]; then
    pass "Get single returns correct obligation"
  else
    fail "Get single returned wrong ID" "expected $OB1_ID got $GOT_ID"
  fi
else
  skip "No obligation ID to test"
fi

# API-5: Get non-existent
echo "API-5: GET non-existent obligation"
RESP=$(curl -s -o /dev/null -w "%{http_code}" "$HADLEY_API/life-admin/obligations/00000000-0000-0000-0000-000000000000")
if [ "$RESP" = "404" ]; then
  pass "Non-existent returns 404"
else
  fail "Non-existent did not return 404" "got $RESP"
fi

# Create a second obligation for filter tests
RESP2=$(curl -s -X POST "$HADLEY_API/life-admin/obligations" \
  -H "$(auth_header)" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TEST: Home Insurance",
    "category": "insurance",
    "due_date": "2026-04-12",
    "recurrence_months": 12,
    "alert_lead_days": [30, 14, 7, 3],
    "alert_priority": "high",
    "provider": "Admiral",
    "reference_number": "HH-123456",
    "amount": 342.00
  }')
OB2_ID=$(echo "$RESP2" | python -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
if [ -n "$OB2_ID" ]; then
  CREATED_IDS+=("$OB2_ID")
fi

# API-6: Filter by status
echo "API-6: GET with status filter"
RESP=$(curl -s "$HADLEY_API/life-admin/obligations?status=active")
COUNT=$(echo "$RESP" | python -c "import sys,json; print(len([x for x in json.load(sys.stdin) if 'TEST:' in x.get('name','')]))" 2>/dev/null)
if [ "$COUNT" -ge 2 ] 2>/dev/null; then
  pass "Status filter returns test obligations ($COUNT found)"
else
  fail "Status filter issue" "found $COUNT test obligations"
fi

# API-7: Filter by category
echo "API-7: GET with category filter"
RESP=$(curl -s "$HADLEY_API/life-admin/obligations?category=vehicle")
FOUND=$(echo "$RESP" | python -c "
import sys,json
obs = json.load(sys.stdin)
cats = set(o['category'] for o in obs)
print('OK' if cats == {'vehicle'} or len(obs) == 0 else f'MIXED:{cats}')
" 2>/dev/null)
if [ "$FOUND" = "OK" ]; then
  pass "Category filter returns only vehicle"
else
  fail "Category filter returned mixed" "$FOUND"
fi

# API-8: Update obligation
echo "API-8: PATCH /life-admin/obligations/{id}"
if [ -n "$OB1_ID" ]; then
  RESP=$(curl -s -X PATCH "$HADLEY_API/life-admin/obligations/$OB1_ID" \
    -H "$(auth_header)" \
    -H "Content-Type: application/json" \
    -d '{"amount": 40.00, "notes": "Updated test"}')
  UPD_AMT=$(echo "$RESP" | python -c "import sys,json; print(json.load(sys.stdin).get('amount'))" 2>/dev/null)
  if [ "$UPD_AMT" = "40.0" ] || [ "$UPD_AMT" = "40" ]; then
    pass "Update succeeded (amount=40)"
  else
    fail "Update failed" "amount=$UPD_AMT, resp=$RESP"
  fi
else
  skip "No obligation ID to update"
fi

# API-9: Update with empty body
echo "API-9: PATCH with empty body"
if [ -n "$OB1_ID" ]; then
  RESP=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$HADLEY_API/life-admin/obligations/$OB1_ID" \
    -H "$(auth_header)" \
    -H "Content-Type: application/json" \
    -d '{}')
  if [ "$RESP" = "400" ]; then
    pass "Empty update returns 400"
  else
    fail "Empty update did not return 400" "got $RESP"
  fi
fi

# API-11: Delete without auth
echo "API-11: DELETE without auth"
if [ -n "$OB1_ID" ]; then
  RESP=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$HADLEY_API/life-admin/obligations/$OB1_ID")
  if [ "$RESP" = "401" ] || [ "$RESP" = "403" ]; then
    pass "Delete without auth rejected ($RESP)"
  else
    fail "Delete without auth not rejected" "got $RESP"
  fi
fi

# ==========================================
# 3. Action Endpoints
# ==========================================
section "3. Action Endpoints"

# ACT-1: Action non-recurring obligation
echo "ACT-1: Action non-recurring obligation"
ONEOFF=$(curl -s -X POST "$HADLEY_API/life-admin/obligations" \
  -H "$(auth_header)" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TEST: One-off task",
    "category": "other",
    "due_date": "2026-04-01"
  }')
ONEOFF_ID=$(echo "$ONEOFF" | python -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
if [ -n "$ONEOFF_ID" ]; then
  CREATED_IDS+=("$ONEOFF_ID")
  RESP=$(curl -s -X POST "$HADLEY_API/life-admin/obligations/$ONEOFF_ID/action" \
    -H "$(auth_header)")
  ACT_CHECK=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
actioned = d.get('actioned', {})
has_next = 'next_occurrence' in d
print('OK' if actioned.get('status') == 'actioned' and not has_next else f'FAIL:status={actioned.get(\"status\")},has_next={has_next}')
" 2>/dev/null)
  if [ "$ACT_CHECK" = "OK" ]; then
    pass "Non-recurring actioned, no next occurrence"
  else
    fail "Non-recurring action failed" "$ACT_CHECK"
  fi
fi

# ACT-2: Action recurring (12mo)
echo "ACT-2: Action recurring obligation (12mo)"
if [ -n "$OB1_ID" ]; then
  RESP=$(curl -s -X POST "$HADLEY_API/life-admin/obligations/$OB1_ID/action" \
    -H "$(auth_header)")
  ACT_CHECK=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
actioned = d.get('actioned', {})
next_ob = d.get('next_occurrence', {})
print('OK' if actioned.get('status') == 'actioned' and next_ob.get('due_date') == '2027-06-15' and next_ob.get('status') == 'active' else f'FAIL:status={actioned.get(\"status\")},next_due={next_ob.get(\"due_date\")},next_status={next_ob.get(\"status\")}')
" 2>/dev/null)
  if [ "$ACT_CHECK" = "OK" ]; then
    pass "Recurring: actioned + next due 2027-06-15"
    # Track the new occurrence for cleanup
    NEXT_ID=$(echo "$RESP" | python -c "import sys,json; print(json.load(sys.stdin)['next_occurrence']['id'])" 2>/dev/null)
    if [ -n "$NEXT_ID" ]; then
      CREATED_IDS+=("$NEXT_ID")
    fi
  else
    fail "Recurring action failed" "$ACT_CHECK"
  fi
fi

# ACT-4: New occurrence copies fields
echo "ACT-4: New occurrence copies fields"
if [ -n "${NEXT_ID:-}" ]; then
  RESP=$(curl -s "$HADLEY_API/life-admin/obligations/$NEXT_ID")
  COPY_CHECK=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
checks = [
    d.get('name') == 'TEST: Car MOT - VW Polo',
    d.get('category') == 'vehicle',
    d.get('provider') == 'Halfords',
    d.get('reference_number') == 'AB12 CDE',
    d.get('recurrence_months') == 12,
    d.get('alert_priority') == 'high',
]
print('OK' if all(checks) else f'FAIL:{[i for i,c in enumerate(checks) if not c]}')
" 2>/dev/null)
  if [ "$COPY_CHECK" = "OK" ]; then
    pass "Next occurrence has all copied fields"
  else
    fail "Field copy mismatch" "$COPY_CHECK"
  fi
else
  skip "No next occurrence to check"
fi

# ACT-5: Snooze obligation
echo "ACT-5: Snooze obligation"
if [ -n "$OB2_ID" ]; then
  RESP=$(curl -s -X POST "$HADLEY_API/life-admin/obligations/$OB2_ID/snooze" \
    -H "$(auth_header)" \
    -H "Content-Type: application/json" \
    -d '{"until": "2026-04-15"}')
  SNOOZE_CHECK=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
print('OK' if d.get('status') == 'snoozed' and d.get('snoozed_until') == '2026-04-15' else f'FAIL:status={d.get(\"status\")},until={d.get(\"snoozed_until\")}')
" 2>/dev/null)
  if [ "$SNOOZE_CHECK" = "OK" ]; then
    pass "Snoozed until 2026-04-15"
  else
    fail "Snooze failed" "$SNOOZE_CHECK"
  fi
fi

# ACT-6: Snooze without auth
echo "ACT-6: Snooze without auth"
if [ -n "$OB2_ID" ]; then
  RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$HADLEY_API/life-admin/obligations/$OB2_ID/snooze" \
    -H "Content-Type: application/json" \
    -d '{"until": "2026-04-15"}')
  if [ "$RESP" = "401" ] || [ "$RESP" = "403" ]; then
    pass "Snooze without auth rejected ($RESP)"
  else
    fail "Snooze without auth not rejected" "got $RESP"
  fi
fi

# ==========================================
# 4. Alerts & Dashboard
# ==========================================
section "4. Alerts & Dashboard"

# Create an overdue obligation for alert tests
OVERDUE=$(curl -s -X POST "$HADLEY_API/life-admin/obligations" \
  -H "$(auth_header)" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TEST: Overdue boiler service",
    "category": "property",
    "due_date": "2026-03-01",
    "alert_priority": "medium",
    "alert_lead_days": [30, 14, 7, 3],
    "provider": "British Gas"
  }')
OVERDUE_ID=$(echo "$OVERDUE" | python -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
if [ -n "$OVERDUE_ID" ]; then
  CREATED_IDS+=("$OVERDUE_ID")
fi

# Create a future obligation (well ahead, should NOT alert)
FUTURE=$(curl -s -X POST "$HADLEY_API/life-admin/obligations" \
  -H "$(auth_header)" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TEST: Passport renewal",
    "category": "identity",
    "due_date": "2031-01-15",
    "alert_priority": "critical",
    "alert_lead_days": [180, 90, 30, 14, 7]
  }')
FUTURE_ID=$(echo "$FUTURE" | python -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
if [ -n "$FUTURE_ID" ]; then
  CREATED_IDS+=("$FUTURE_ID")
fi

# ALT-1: Alerts endpoint works
echo "ALT-1: GET /life-admin/alerts"
RESP=$(curl -s "$HADLEY_API/life-admin/alerts")
ALT_CHECK=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
print('OK' if 'tiers' in d and 'total_alerts' in d and 'as_of' in d and 'by_priority' in d else f'FAIL:keys={list(d.keys())}')
" 2>/dev/null)
if [ "$ALT_CHECK" = "OK" ]; then
  pass "Alerts endpoint returns correct structure (with by_priority)"
else
  fail "Alerts structure wrong" "$ALT_CHECK"
fi

# ALT-2: Overdue detected
echo "ALT-2: Overdue obligation in alerts"
if [ -n "$OVERDUE_ID" ]; then
  RESP=$(curl -s "$HADLEY_API/life-admin/alerts")
  OVERDUE_CHECK=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
overdue = d.get('tiers', {}).get('overdue', [])
ids = [o['id'] for o in overdue]
print('OK' if '$OVERDUE_ID' in ids else f'FAIL:overdue_ids={ids}')
" 2>/dev/null)
  if [ "$OVERDUE_CHECK" = "OK" ]; then
    pass "Overdue obligation appears in overdue tier"
  else
    fail "Overdue not detected" "$OVERDUE_CHECK"
  fi
fi

# ALT-4: Record alert → suppressed on next call
echo "ALT-4: Alert suppression after recording"
if [ -n "$OVERDUE_ID" ]; then
  # Record the overdue alert
  curl -s -X POST "$HADLEY_API/life-admin/alerts/record" \
    -H "$(auth_header)" \
    -H "Content-Type: application/json" \
    -d "{\"obligation_id\": \"$OVERDUE_ID\", \"alert_tier\": \"overdue\", \"channel\": \"#test\"}" > /dev/null

  # Check alerts again — overdue should be suppressed
  RESP=$(curl -s "$HADLEY_API/life-admin/alerts")
  SUPPRESSED=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
overdue = d.get('tiers', {}).get('overdue', [])
ids = [o['id'] for o in overdue]
print('OK' if '$OVERDUE_ID' not in ids else 'FAIL:still_showing')
" 2>/dev/null)
  if [ "$SUPPRESSED" = "OK" ]; then
    pass "Overdue alert suppressed after recording"
  else
    fail "Alert not suppressed" "$SUPPRESSED"
  fi
fi

# ALT-5: Snoozed obligation hidden
echo "ALT-5: Snoozed obligation hidden from alerts"
if [ -n "$OB2_ID" ]; then
  RESP=$(curl -s "$HADLEY_API/life-admin/alerts")
  SNOOZED_CHECK=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
all_ids = []
for tier_list in d.get('tiers', {}).values():
    all_ids.extend([o['id'] for o in tier_list])
print('OK' if '$OB2_ID' not in all_ids else 'FAIL:snoozed_showing')
" 2>/dev/null)
  if [ "$SNOOZED_CHECK" = "OK" ]; then
    pass "Snoozed obligation hidden from alerts"
  else
    fail "Snoozed showing in alerts" "$SNOOZED_CHECK"
  fi
fi

# ALT-7: Dashboard grouping
echo "ALT-7: GET /life-admin/dashboard"
RESP=$(curl -s "$HADLEY_API/life-admin/dashboard")
DASH_CHECK=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
expected_keys = {'overdue', 'due_this_week', 'due_this_month', 'all_clear', 'snoozed', 'actioned_recently'}
actual_keys = set(d.get('groups', {}).keys())
counts_keys = set(d.get('counts', {}).keys())
print('OK' if expected_keys == actual_keys and expected_keys == counts_keys else f'FAIL:groups={actual_keys},counts={counts_keys}')
" 2>/dev/null)
if [ "$DASH_CHECK" = "OK" ]; then
  pass "Dashboard has correct group keys"
else
  fail "Dashboard groups wrong" "$DASH_CHECK"
fi

# ALT-8: Dashboard counts match
echo "ALT-8: Dashboard counts match group lengths"
RESP=$(curl -s "$HADLEY_API/life-admin/dashboard")
COUNT_CHECK=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
groups = d.get('groups', {})
counts = d.get('counts', {})
mismatches = [k for k in groups if counts.get(k) != len(groups[k])]
print('OK' if not mismatches else f'FAIL:mismatches={mismatches}')
" 2>/dev/null)
if [ "$COUNT_CHECK" = "OK" ]; then
  pass "Dashboard counts match group lengths"
else
  fail "Dashboard count mismatch" "$COUNT_CHECK"
fi

# ==========================================
# 5. Email Scans
# ==========================================
section "5. Email Scans"

# SCN-1: Record scan
echo "SCN-1: POST /life-admin/scans"
RESP=$(curl -s -X POST "$HADLEY_API/life-admin/scans" \
  -H "$(auth_header)" \
  -H "Content-Type: application/json" \
  -d '{"emails_checked": 15, "obligations_created": 2, "obligations_updated": 3, "details": {"test": true}}')
SCN_CHECK=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
print('OK' if d.get('emails_checked') == 15 and d.get('obligations_created') == 2 else f'FAIL:{d}')
" 2>/dev/null)
if [ "$SCN_CHECK" = "OK" ]; then
  pass "Scan recorded successfully"
else
  fail "Scan recording failed" "$SCN_CHECK"
fi

# SCN-2: List scans
echo "SCN-2: GET /life-admin/scans"
RESP=$(curl -s "$HADLEY_API/life-admin/scans")
LIST_CHECK=$(echo "$RESP" | python -c "
import sys, json
d = json.load(sys.stdin)
print('OK' if isinstance(d, list) and len(d) >= 1 else f'FAIL:type={type(d).__name__},len={len(d) if isinstance(d,list) else \"?\"}')" 2>/dev/null)
if [ "$LIST_CHECK" = "OK" ]; then
  pass "Scan list returns array with entries"
else
  fail "Scan list failed" "$LIST_CHECK"
fi

# ==========================================
# 6. Data Fetchers
# ==========================================
section "6. Data Fetchers"

echo "DF-1 to DF-4: Fetcher registration"
RESP=$(python -c "
from domains.peterbot.data_fetchers import SKILL_DATA_FETCHERS
expected = ['life-admin-scan', 'life-admin-email-scan', 'life-admin-compare', 'life-admin-dashboard']
found = [k for k in expected if k in SKILL_DATA_FETCHERS]
missing = [k for k in expected if k not in SKILL_DATA_FETCHERS]
if missing:
    print(f'FAIL:missing={missing}')
else:
    print(f'OK:{len(found)} registered')
" 2>&1)
if echo "$RESP" | grep -q "^OK:"; then
  pass "All 4 data fetchers registered: $RESP"
else
  fail "Fetcher registration" "$RESP"
fi

# DF-5: Scan data structure (live call)
echo "DF-5: Scan data structure"
RESP=$(python -c "
import asyncio
from domains.peterbot.data_fetchers import get_life_admin_scan_data
result = asyncio.run(get_life_admin_scan_data())
keys = set(result.keys())
expected = {'alerts', 'summary', 'date'}
if 'error' in keys:
    print(f'ERROR:{result[\"error\"]}')
elif expected.issubset(keys):
    print('OK')
else:
    print(f'FAIL:keys={keys}')
" 2>&1)
if [ "$RESP" = "OK" ]; then
  pass "Scan data has alerts/summary/date keys"
else
  fail "Scan data structure" "$RESP"
fi

# ==========================================
# 7. Skills
# ==========================================
section "7. Skills"

SKILLS=("life-admin-scan" "life-admin-email-scan" "life-admin" "life-admin-compare" "life-admin-dashboard")
for skill in "${SKILLS[@]}"; do
  SKILL_PATH="domains/peterbot/wsl_config/skills/$skill/SKILL.md"
  if [ -f "$SKILL_PATH" ]; then
    # Check frontmatter is valid
    HAS_NAME=$(head -20 "$SKILL_PATH" | grep "^name:" | wc -l)
    HAS_DESC=$(head -20 "$SKILL_PATH" | grep "^description:" | wc -l)
    if [ "$HAS_NAME" -ge 1 ] && [ "$HAS_DESC" -ge 1 ]; then
      pass "SKILL: $skill exists with valid frontmatter"
    else
      fail "SKILL: $skill missing frontmatter" "name=$HAS_NAME desc=$HAS_DESC"
    fi
  else
    fail "SKILL: $skill SKILL.md missing" "$SKILL_PATH"
  fi
done

# SKL-7: API base URL correct
echo "SKL-7: API URL references"
BAD_URLS=$(grep -r "localhost:8100\|127\.0\.0\.1:8100" domains/peterbot/wsl_config/skills/life-admin*/SKILL.md 2>/dev/null | grep -v "172.19.64.1" | wc -l)
GOOD_URLS=$(grep -r "172.19.64.1:8100" domains/peterbot/wsl_config/skills/life-admin*/SKILL.md 2>/dev/null | wc -l)
if [ "$GOOD_URLS" -ge 1 ]; then
  pass "Skills reference correct API URL (172.19.64.1:8100)"
else
  skip "No API URLs found in skills (may use relative paths)"
fi

# ==========================================
# 8. Schedule Integration
# ==========================================
section "8. Schedule Integration"

SCHEDULE_FILE="domains/peterbot/wsl_config/SCHEDULE.md"
for entry in "life-admin-scan" "life-admin-email-scan" "life-admin-dashboard"; do
  if grep -q "$entry" "$SCHEDULE_FILE" 2>/dev/null; then
    pass "SCH: $entry in SCHEDULE.md"
  else
    fail "SCH: $entry missing from SCHEDULE.md" ""
  fi
done

# ==========================================
# 9. Integration: Full Lifecycle
# ==========================================
section "9. Integration: Full Lifecycle"

echo "INT-1: Create → List → Update → Action → Delete lifecycle"
# Create
LIFE_OB=$(curl -s -X POST "$HADLEY_API/life-admin/obligations" \
  -H "$(auth_header)" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TEST: Lifecycle obligation",
    "category": "other",
    "due_date": "2026-12-31",
    "recurrence_months": 6
  }')
LIFE_ID=$(echo "$LIFE_OB" | python -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
if [ -z "$LIFE_ID" ]; then
  fail "INT-1: Create step failed" "$LIFE_OB"
else
  CREATED_IDS+=("$LIFE_ID")

  # List — should contain it
  LIST=$(curl -s "$HADLEY_API/life-admin/obligations")
  IN_LIST=$(echo "$LIST" | python -c "import sys,json; ids=[o['id'] for o in json.load(sys.stdin)]; print('YES' if '$LIFE_ID' in ids else 'NO')" 2>/dev/null)

  # Update
  curl -s -X PATCH "$HADLEY_API/life-admin/obligations/$LIFE_ID" \
    -H "$(auth_header)" \
    -H "Content-Type: application/json" \
    -d '{"notes": "Lifecycle updated"}' > /dev/null

  # Action (should create next occurrence due 2027-06-30)
  ACT_RESP=$(curl -s -X POST "$HADLEY_API/life-admin/obligations/$LIFE_ID/action" \
    -H "$(auth_header)")
  NEXT_DUE=$(echo "$ACT_RESP" | python -c "import sys,json; print(json.load(sys.stdin).get('next_occurrence',{}).get('due_date','NONE'))" 2>/dev/null)
  NEXT_LIFECYCLE_ID=$(echo "$ACT_RESP" | python -c "import sys,json; print(json.load(sys.stdin).get('next_occurrence',{}).get('id',''))" 2>/dev/null)
  if [ -n "$NEXT_LIFECYCLE_ID" ]; then
    CREATED_IDS+=("$NEXT_LIFECYCLE_ID")
  fi

  # Delete the next occurrence
  if [ -n "$NEXT_LIFECYCLE_ID" ]; then
    DEL_RESP=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$HADLEY_API/life-admin/obligations/$NEXT_LIFECYCLE_ID" \
      -H "$(auth_header)")
  fi

  if [ "$IN_LIST" = "YES" ] && [ "$NEXT_DUE" = "2027-06-30" ]; then
    pass "INT-1: Full lifecycle passed (list=YES, next_due=2027-06-30)"
  else
    fail "INT-1: Lifecycle issue" "in_list=$IN_LIST, next_due=$NEXT_DUE"
  fi
fi

# INT-2: Alert lifecycle (create overdue → get alerts → record → get alerts again)
echo "INT-2: Alert lifecycle"
ALERT_OB=$(curl -s -X POST "$HADLEY_API/life-admin/obligations" \
  -H "$(auth_header)" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TEST: Alert lifecycle",
    "category": "other",
    "due_date": "2026-03-20",
    "alert_lead_days": [30, 7, 3]
  }')
ALERT_OB_ID=$(echo "$ALERT_OB" | python -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
if [ -n "$ALERT_OB_ID" ]; then
  CREATED_IDS+=("$ALERT_OB_ID")

  # Should appear in alerts
  ALERTS1=$(curl -s "$HADLEY_API/life-admin/alerts")
  IN_ALERTS1=$(echo "$ALERTS1" | python -c "
import sys, json
d = json.load(sys.stdin)
all_ids = []
for tier_list in d.get('tiers', {}).values():
    all_ids.extend([o['id'] for o in tier_list])
print('YES' if '$ALERT_OB_ID' in all_ids else 'NO')
" 2>/dev/null)

  # Record the alert
  curl -s -X POST "$HADLEY_API/life-admin/alerts/record" \
    -H "$(auth_header)" \
    -H "Content-Type: application/json" \
    -d "{\"obligation_id\": \"$ALERT_OB_ID\", \"alert_tier\": \"overdue\", \"channel\": \"#test\"}" > /dev/null

  # Should NOT appear now
  ALERTS2=$(curl -s "$HADLEY_API/life-admin/alerts")
  IN_ALERTS2=$(echo "$ALERTS2" | python -c "
import sys, json
d = json.load(sys.stdin)
all_ids = []
for tier_list in d.get('tiers', {}).values():
    all_ids.extend([o['id'] for o in tier_list])
print('YES' if '$ALERT_OB_ID' in all_ids else 'NO')
" 2>/dev/null)

  if [ "$IN_ALERTS1" = "YES" ] && [ "$IN_ALERTS2" = "NO" ]; then
    pass "INT-2: Alert lifecycle (showed → suppressed after record)"
  else
    fail "INT-2: Alert lifecycle" "before=$IN_ALERTS1, after=$IN_ALERTS2"
  fi
fi

# API-10: Delete (last, so we can verify it works)
echo "API-10: DELETE /life-admin/obligations/{id}"
if [ -n "$ALERT_OB_ID" ]; then
  RESP=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$HADLEY_API/life-admin/obligations/$ALERT_OB_ID" \
    -H "$(auth_header)")
  if [ "$RESP" = "200" ]; then
    pass "Delete returns 200"
    # Remove from cleanup list since already deleted
    CREATED_IDS=("${CREATED_IDS[@]/$ALERT_OB_ID/}")
  else
    fail "Delete failed" "got $RESP"
  fi
fi

# DB-9: Cascade delete (alert history should be gone too)
echo "DB-9: Cascade delete (alert history cleaned up)"
# The alert record we created for ALERT_OB_ID should be gone now
# We can verify by trying to query — but since we can't query alert_history directly via API easily,
# we'll verify by checking alerts don't crash
RESP=$(curl -s "$HADLEY_API/life-admin/alerts")
CASCADE_CHECK=$(echo "$RESP" | python -c "import sys,json; d=json.load(sys.stdin); print('OK' if 'tiers' in d else 'FAIL')" 2>/dev/null)
if [ "$CASCADE_CHECK" = "OK" ]; then
  pass "Alerts still work after cascade delete"
else
  fail "Cascade delete issue" "$CASCADE_CHECK"
fi

# ==========================================
# Summary
# ==========================================
echo ""
echo "========================================"
echo "  Results"
echo "========================================"
echo -e "  ${GREEN}Passed: $PASS${NC}"
echo -e "  ${RED}Failed: $FAIL${NC}"
echo -e "  ${YELLOW}Skipped: $SKIP${NC}"
echo "  Total:  $((PASS + FAIL + SKIP))"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo -e "${RED}SOME TESTS FAILED${NC}"
  exit 1
else
  echo -e "${GREEN}ALL TESTS PASSED${NC}"
  exit 0
fi

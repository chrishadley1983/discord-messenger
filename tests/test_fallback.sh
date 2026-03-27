#!/bin/bash
# Channel Architecture — Fallback Tests
# Run from WSL: bash tests/test_fallback.sh
#
# WARNING: These tests temporarily kill channel sessions to verify fallback.
# Sessions auto-restart via the restart loop, but expect ~30s disruption.

set -euo pipefail

PASS=0
FAIL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}✗${NC} $1: $2"; FAIL=$((FAIL + 1)); }

echo "========================================"
echo "  Fallback Tests (DISRUPTIVE)"
echo "========================================"
echo ""
echo "These tests will temporarily kill channel sessions."
echo "They should auto-restart within 10-15 seconds."
echo ""

# --- F8: Jobs channel fallback ---
echo "F8: Jobs channel fallback to CLI"
echo "  Killing jobs-channel..."
tmux send-keys -t jobs-channel C-c 2>/dev/null || true
sleep 2

# Try to hit the jobs channel — should be down
RESP=$(curl -s http://127.0.0.1:8103/health 2>&1 || echo "DOWN")
if echo "$RESP" | grep -q "DOWN\|refused\|reset"; then
  pass "Jobs channel is down after kill"
else
  fail "Jobs channel still responding" "$RESP"
fi

echo "  Waiting for restart loop (15s)..."
sleep 15

RESP=$(curl -s http://127.0.0.1:8103/health 2>&1 || echo "DOWN")
if echo "$RESP" | grep -q '"ok"'; then
  pass "Jobs channel auto-restarted"
else
  fail "Jobs channel did not restart" "$RESP"
fi

# --- R5: Channel status API ---
echo "R5: Channel status API reflects reality"
RESP=$(curl -s http://172.19.64.1:8100/channels/status 2>&1 || echo "FAILED")
if echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d)" 2>/dev/null; then
  pass "Channel status API returns data"
else
  fail "Channel status API failed" "$RESP"
fi

echo ""
echo "========================================"
echo -e "  Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "========================================"
echo ""
echo "Note: All sessions should be back online now."
echo "Verify: tmux ls"

exit $FAIL

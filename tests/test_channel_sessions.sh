#!/bin/bash
# Channel Architecture — Session Integration Tests
# Run from WSL: bash tests/test_channel_sessions.sh
#
# Tests channel session health, HTTP endpoints, restart loops.
# Requires: All three channel tmux sessions running.

set -euo pipefail

PASS=0
FAIL=0
SKIP=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}✗${NC} $1: $2"; FAIL=$((FAIL + 1)); }
skip() { echo -e "  ${YELLOW}○${NC} $1 (skipped)"; SKIP=$((SKIP + 1)); }

echo "========================================"
echo "  Channel Sessions — Integration Tests"
echo "========================================"
echo ""

# --- S1: All three tmux sessions exist ---
echo "S1: tmux sessions exist"
for session in peter-channel whatsapp-channel jobs-channel; do
  if tmux has-session -t "$session" 2>/dev/null; then
    pass "$session is running"
  else
    fail "$session not found" "tmux has-session failed"
  fi
done

# --- S2: WhatsApp channel health endpoint ---
echo "S2: WhatsApp channel HTTP health"
RESP=$(curl -s http://127.0.0.1:8102/health 2>&1 || echo "UNREACHABLE")
if echo "$RESP" | grep -q '"ok"'; then
  pass "WhatsApp channel :8102 healthy"
else
  fail "WhatsApp channel unreachable" "$RESP"
fi

# --- S3: Jobs channel health endpoint ---
echo "S3: Jobs channel HTTP health"
RESP=$(curl -s http://127.0.0.1:8103/health 2>&1 || echo "UNREACHABLE")
if echo "$RESP" | grep -q '"ok"'; then
  pass "Jobs channel :8103 healthy"
else
  fail "Jobs channel unreachable" "$RESP"
fi

# --- S4: Jobs channel synchronous execution ---
echo "S4: Jobs channel synchronous job"
RESP=$(curl -s -X POST http://127.0.0.1:8103/job \
  -H "Content-Type: application/json" \
  -d '{"skill":"test","context":"Reply with exactly: TEST_OK"}' \
  --max-time 30 2>&1 || echo "TIMEOUT")
if echo "$RESP" | grep -q "TEST_OK"; then
  pass "Synchronous job returned expected output"
else
  fail "Unexpected response" "$RESP"
fi

# --- S5: WhatsApp channel message forwarding ---
echo "S5: WhatsApp channel message forward"
RESP=$(curl -s -X POST http://127.0.0.1:8102/whatsapp/message \
  -H "Content-Type: application/json" \
  -d '{"sender_name":"Test","sender_number":"000","reply_to":"000","is_group":false,"text":"test ping","is_voice":false}' \
  --max-time 5 2>&1 || echo "TIMEOUT")
if echo "$RESP" | grep -q "forwarded"; then
  pass "WhatsApp message forwarded to session"
else
  fail "Forward failed" "$RESP"
fi

# --- S6: Discord channel app log exists ---
echo "S6: Discord channel app log"
if [ -f /tmp/peter-channel-app.log ]; then
  LINES=$(wc -l < /tmp/peter-channel-app.log)
  if [ "$LINES" -gt 0 ]; then
    pass "App log has $LINES lines"
  else
    fail "App log is empty" ""
  fi
else
  fail "App log not found" "/tmp/peter-channel-app.log missing"
fi

# --- S7: Channel restart logs exist ---
echo "S7: Restart logs"
for log in peter-channel whatsapp-channel jobs-channel; do
  if [ -f "/tmp/${log}-restarts.log" ]; then
    pass "${log} restart log exists"
  else
    skip "${log} restart log not yet created (no restarts)"
  fi
done

# --- S8: MCP servers connected ---
echo "S8: MCP servers in channel sessions"
# Check the most recent debug log for connected servers
for log in /tmp/pc-debug*.log /tmp/wa-debug*.log /tmp/jobs-debug*.log; do
  if [ -f "$log" ]; then
    CONNECTED=$(grep "Successfully connected" "$log" 2>/dev/null | wc -l)
    if [ "$CONNECTED" -gt 0 ]; then
      pass "$(basename $log): $CONNECTED MCP servers connected"
    fi
    break
  fi
done

echo ""
echo "========================================"
echo -e "  Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, ${YELLOW}$SKIP skipped${NC}"
echo "========================================"

exit $FAIL

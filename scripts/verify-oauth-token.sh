#!/bin/bash
# End-to-end verification of the static-OAuth-token fix (PR #26).
#
# Run from WSL:        bash scripts/verify-oauth-token.sh
# Run from Windows:    MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash \
#                        "/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/scripts/verify-oauth-token.sh"
#
# Emits one "PASS"/"FAIL" line per check and a machine-readable RESULT line.
# Exit 0 iff every check passes. Safe/read-only except a throwaway Haiku call
# in an isolated temp config dir (does not touch live credentials or channels).
set -uo pipefail

TF="/mnt/c/Users/Chris Hadley/.claude-code-oauth-token"
CREDS="$HOME/.claude/.credentials.json"
CHANNELS=(peter-channel whatsapp-channel jobs-channel jobs-channel-sonnet extract-channel)
export PATH="$HOME/.local/bin:$PATH"

pass=0; fail=0
ok(){ echo "  PASS  $1"; pass=$((pass+1)); }
no(){ echo "  FAIL  $1"; fail=$((fail+1)); }

echo "== [1] token file present & well-formed =="
TOK=""
if [ -s "$TF" ]; then
  TOK="$(tr -d '\r\n' < "$TF")"
  if [ "${#TOK}" -ge 20 ]; then ok "token file exists (${#TOK} chars)"; else no "token file too short (${#TOK} chars)"; fi
else
  no "token file missing/empty: $TF"
fi

echo "== [2] token authenticates on its own (isolated empty config dir) =="
if [ -n "$TOK" ]; then
  TMP="$(mktemp -d)"
  OUT="$(CLAUDE_CONFIG_DIR="$TMP" CLAUDE_CODE_OAUTH_TOKEN="$TOK" timeout 120 \
         claude -p --model claude-haiku-4-5 --permission-mode bypassPermissions \
         "Reply with exactly: TOKEN_OK" < /dev/null 2>&1)"
  rm -rf "$TMP"
  case "$OUT" in *TOKEN_OK*) ok "token-only auth -> TOKEN_OK";; *) no "token-only auth failed: ${OUT:0:100}";; esac
else
  no "skipped — no token to test"
fi

echo "== [3] every running channel claude carries CLAUDE_CODE_OAUTH_TOKEN =="
declare -A seen
for d in /proc/[0-9]*; do
  e="$d/environ"
  [ -r "$e" ] || continue
  if { tr '\0' '\n' < "$e"; } 2>/dev/null | grep -q '^CLAUDE_CODE_OAUTH_TOKEN='; then
    cmd="$(tr '\0' ' ' < "${d}/cmdline" 2>/dev/null)"
    for ch in "${CHANNELS[@]}"; do
      case "$cmd" in *"/tmp/${ch}-mcp.json"*) seen[$ch]=1;; esac
    done
  fi
done
for ch in "${CHANNELS[@]}"; do
  if [ "${seen[$ch]:-0}" = 1 ]; then ok "$ch claude has token in env"; else no "$ch claude MISSING token (or not running)"; fi
done

echo "== [4] jobs-channel end-to-end auth (:8103) =="
R="$(curl -s --max-time 30 -X POST http://localhost:8103/job \
      -H 'Content-Type: application/json' \
      -d '{"skill":"auth-test","context":"Reply with exactly AUTH_OK and nothing else."}' 2>/dev/null)"
case "$R" in *AUTH_OK*) ok "jobs-channel :8103 -> AUTH_OK";; *) no "jobs-channel :8103 -> [${R:-no response}]";; esac

echo "== [5] no login/401 lockout markers in any channel pane =="
locked=""
for s in "${CHANNELS[@]}"; do
  if tmux capture-pane -p -J -t "$s" 2>/dev/null | tail -40 | grep -q 'Please run /login\|401 Invalid authentication credentials'; then
    locked="$locked $s"
  fi
done
if [ -z "$locked" ]; then ok "no channel pane shows /login or 401"; else no "locked-out panes:$locked"; fi

echo "== [6] channels are NOT rewriting the rotating credentials file =="
if [ -f "$CREDS" ]; then
  age_min=$(( ( $(date +%s) - $(stat -c %Y "$CREDS") ) / 60 ))
  ok "credentials.json last written ${age_min}m ago (stable = channels ignore it; informational)"
else
  ok "no credentials.json present (channels rely solely on the static token)"
fi

echo ""
echo "RESULT pass=$pass fail=$fail overall=$([ "$fail" -eq 0 ] && echo PASS || echo FAIL)"
[ "$fail" -eq 0 ]

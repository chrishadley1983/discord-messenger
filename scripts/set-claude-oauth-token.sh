#!/bin/bash
# Provision the STATIC, non-rotating Claude Code OAuth token that every WSL
# Claude session shares — the permanent fix for the shared-credentials
# refresh-token race that logs sessions out (incident 2026-06-20).
#
# Why a static token: Claude Code 2.1.183 rotates the OAuth *refresh* token on
# every refresh. With ~5 channel sessions sharing one ~/.claude/.credentials.json
# they invalidate each other and the file gets blanked → every job 401s. A token
# from `claude setup-token` (Max plan) is valid ~1 year and does NOT rotate, so
# all sessions can share it safely. Setting CLAUDE_CODE_OAUTH_TOKEN makes Claude
# Code use it directly and ignore the rotating credentials file entirely.
#
# Usage (run in WSL):
#   1. On a machine with a browser:   claude setup-token
#   2. Paste the printed token here:
#        scripts/set-claude-oauth-token.sh '<token>'
#      or pipe it:
#        echo '<token>' | scripts/set-claude-oauth-token.sh
#
# Writes the token to the file scripts/claude-oauth-env.sh reads, then restarts
# the channel sessions so they reload with CLAUDE_CODE_OAUTH_TOKEN set.
set -uo pipefail

TOKEN_FILE="/mnt/c/Users/Chris Hadley/.claude-code-oauth-token"
BASE="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger"
CHANNELS=(peter-channel whatsapp-channel jobs-channel jobs-channel-sonnet extract-channel)

# Token from $1, else stdin (so it can be piped and not land in shell history).
TOKEN="${1:-}"
if [ -z "$TOKEN" ] && [ ! -t 0 ]; then
  TOKEN="$(cat)"
fi
TOKEN="$(printf '%s' "$TOKEN" | tr -d '\r\n')"

if [ -z "$TOKEN" ]; then
  echo "ERROR: no token provided. Run 'claude setup-token' first, then pass its output." >&2
  exit 1
fi
if [ "${#TOKEN}" -lt 20 ]; then
  echo "WARNING: token looks unexpectedly short (${#TOKEN} chars) — writing it anyway." >&2
fi

umask 077
printf '%s\n' "$TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE" 2>/dev/null || true
echo "Wrote token (${#TOKEN} chars) -> $TOKEN_FILE"

echo "Restarting channel sessions so they pick up CLAUDE_CODE_OAUTH_TOKEN..."
for name in "${CHANNELS[@]}"; do
  script="$BASE/$name/launch.sh"
  if [ ! -f "$script" ]; then
    echo "  skip $name (no launch.sh)"; continue
  fi
  if tmux kill-session -t "$name" 2>/dev/null; then echo "  killed $name"; else echo "  $name was not running"; fi
  tmux new-session -d -s "$name" -c "$HOME/peterbot" "bash \"$script\""
  echo "  relaunched $name"
done

sleep 2
echo ""
echo "Live channel sessions:"
tmux ls 2>/dev/null | grep -E "$(IFS='|'; echo "${CHANNELS[*]}")" || \
  echo "  (none yet — bot.py's channel watchdog also relaunches dead sessions within ~60s)"
echo ""
echo "Done. After a session has fully started you can confirm it's authed with:"
echo "  tmux capture-pane -p -t jobs-channel | tail"

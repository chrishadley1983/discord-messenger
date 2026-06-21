#!/bin/bash
# Source me to give the current shell a STATIC, non-rotating Claude Code OAuth
# token, shared by every WSL channel session + the router_v2 fallback.
#
# Why this exists
# ---------------
# All WSL Claude Code instances share one ~/.claude/.credentials.json. Since
# Claude Code 2.1.183 (auto-installed 2026-06-19) the OAuth *refresh* token
# rotates on every refresh — each refresh mints a new refresh token and
# invalidates the previous one. With ~5 channel sessions (+ the fallback)
# sharing that one file, they invalidate each other's cached tokens and the
# loser of a write race can blank the file, after which every session 401s and
# scheduled jobs return "empty response" (incident 2026-06-20).
#
# A token from `claude setup-token` (Max plan) is valid ~1 year and does NOT
# rotate on use, so all instances can safely share it. When
# CLAUDE_CODE_OAUTH_TOKEN is set, Claude Code uses it directly and never touches
# the rotating .credentials.json — which removes the race entirely.
#
# Provisioning (run once, then restart the channel sessions):
#   1. On a machine with a browser:  claude setup-token
#   2. Paste the printed token:       scripts/set-claude-oauth-token.sh <token>
# That writes the token file below; this include picks it up on next launch.
#
# Until the token file exists and is non-empty this is a NO-OP, so the existing
# OAuth login keeps working unchanged in the meantime. Safe under `set -euo
# pipefail` — the only command that can "fail" is the `[ -s ]` test, and it
# only gates the if-block (never triggers errexit).

# Single source of truth, readable from both Windows and WSL (Windows home dir,
# outside the git repo so it can't be committed).
_cc_token_file="/mnt/c/Users/Chris Hadley/.claude-code-oauth-token"
if [ -s "$_cc_token_file" ]; then
  CLAUDE_CODE_OAUTH_TOKEN="$(tr -d '\r\n' < "$_cc_token_file")"
  export CLAUDE_CODE_OAUTH_TOKEN
fi
unset _cc_token_file

#!/bin/bash
# Launch Claude Code with the Sonnet jobs channel connected.
# Mirror of jobs-channel/launch.sh — same plumbing, different model + port.
#
# Usage: bash /mnt/c/Users/Chris\ Hadley/claude-projects/discord-messenger/jobs-channel-sonnet/launch.sh

# Prefer the user-space native Claude Code install (2.1.170+, dynamic
# workflows) over the stale root-owned npm one at /usr/bin/claude.
export PATH="$HOME/.local/bin:$PATH"
# Static, non-rotating Claude Code OAuth token (see scripts/claude-oauth-env.sh):
# shared by all WSL sessions so the rotating-refresh-token race can't log them
# out. No-op until provisioned via scripts/set-claude-oauth-token.sh.
source "/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/scripts/claude-oauth-env.sh"
set -euo pipefail

CHANNEL_DIR="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/jobs-channel-sonnet"
# Reuse jobs-channel's node_modules — same dependency set
SHARED_NODE_MODULES="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/jobs-channel/node_modules"
WORKING_DIR="$HOME/peterbot"
ENVFILE="$CHANNEL_DIR/.env"
RESTART_LOG="/tmp/jobs-channel-sonnet-restarts.log"

# Optional channel-specific .env (defaults used if absent)
HTTP_PORT=""
JOB_TIMEOUT_MS=""
if [ -f "$ENVFILE" ]; then
  HTTP_PORT=$(grep HTTP_PORT "$ENVFILE" | cut -d= -f2 | tr -d "\r\n" || true)
  JOB_TIMEOUT_MS=$(grep JOB_TIMEOUT_MS "$ENVFILE" | cut -d= -f2 | tr -d "\r\n" || true)
fi

# Node ESM resolution ignores NODE_PATH — it walks the importing file's own
# node_modules tree. So we need a real node_modules dir alongside src/index.ts.
# Symlink to jobs-channel's (deps are identical) — idempotent, self-heals if
# the channel dir is freshly cloned or the link gets removed.
if [ ! -e "$CHANNEL_DIR/node_modules" ]; then
  ln -sfn "$SHARED_NODE_MODULES" "$CHANNEL_DIR/node_modules"
  echo "[$(date)] Created node_modules symlink -> jobs-channel/node_modules"
fi

cat > /tmp/jobs-channel-sonnet-mcp.json <<EOF
{
  "mcpServers": {
    "jobs-channel-sonnet": {
      "command": "$SHARED_NODE_MODULES/.bin/tsx",
      "args": ["$CHANNEL_DIR/src/index.ts"],
      "env": {
        "HTTP_PORT": "${HTTP_PORT:-8105}",
        "JOB_TIMEOUT_MS": "${JOB_TIMEOUT_MS:-180000}",
        "NODE_PATH": "$SHARED_NODE_MODULES"
      }
    }
  }
}
EOF

cd "$WORKING_DIR"

PROJECT_ROOT="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger"
source "$PROJECT_ROOT/scripts/channel-resilience.sh"

RESTART_COUNT=0
while true; do
  RESTART_COUNT=$((RESTART_COUNT + 1))
  echo "[$(date)] Starting Sonnet jobs channel session (attempt $RESTART_COUNT)..."
  echo "[$(date)] START attempt=$RESTART_COUNT" >> "$RESTART_LOG"

  bash "$PROJECT_ROOT/scripts/auto-accept-prompts.sh" jobs-channel-sonnet &

  START_TIME=$(date +%s)
  set +e
  claude \
    --mcp-config /tmp/jobs-channel-sonnet-mcp.json \
    --dangerously-load-development-channels server:jobs-channel-sonnet \
    --model claude-opus-4-8 \
    --effort medium \
    --permission-mode bypassPermissions
  EXIT_CODE=$?
  set -e
  END_TIME=$(date +%s)
  UPTIME=$((END_TIME - START_TIME))
  echo "[$(date)] EXIT code=$EXIT_CODE uptime=${UPTIME}s attempt=$RESTART_COUNT" >> "$RESTART_LOG"

  if [ "$UPTIME" -ge 300 ]; then
    mark_healthy
  fi

  check_context_exhaustion "jobs-channel-sonnet" "$UPTIME" "$RESTART_COUNT"
  handle_restart "jobs-channel-sonnet" "$EXIT_CODE" "$RESTART_COUNT"
done

#!/bin/bash
# Launch Claude Code with the Extract Channel connected.
# Replaces `claude -p` subprocess in hadley_api/claude_routes.py.
# Haiku 4.5 — cheap, fast one-shot extractions.
#
# Usage: bash /mnt/c/Users/Chris\ Hadley/claude-projects/discord-messenger/extract-channel/launch.sh

set -euo pipefail

CHANNEL_DIR="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/extract-channel"
# Reuse jobs-channel's node_modules — same dependency set
SHARED_NODE_MODULES="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/jobs-channel/node_modules"
WORKING_DIR="$HOME/peterbot"
ENVFILE="$CHANNEL_DIR/.env"
RESTART_LOG="/tmp/extract-channel-restarts.log"

HTTP_PORT=""
REQUEST_TIMEOUT_MS=""
if [ -f "$ENVFILE" ]; then
  HTTP_PORT=$(grep HTTP_PORT "$ENVFILE" | cut -d= -f2 | tr -d "\r\n" || true)
  REQUEST_TIMEOUT_MS=$(grep REQUEST_TIMEOUT_MS "$ENVFILE" | cut -d= -f2 | tr -d "\r\n" || true)
fi

cat > /tmp/extract-channel-mcp.json <<EOF
{
  "mcpServers": {
    "extract-channel": {
      "command": "$SHARED_NODE_MODULES/.bin/tsx",
      "args": ["$CHANNEL_DIR/src/index.ts"],
      "env": {
        "HTTP_PORT": "${HTTP_PORT:-8106}",
        "REQUEST_TIMEOUT_MS": "${REQUEST_TIMEOUT_MS:-90000}",
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
  echo "[$(date)] Starting extract-channel session (attempt $RESTART_COUNT)..."
  echo "[$(date)] START attempt=$RESTART_COUNT" >> "$RESTART_LOG"

  bash "$PROJECT_ROOT/scripts/auto-accept-prompts.sh" extract-channel &

  START_TIME=$(date +%s)
  set +e
  claude \
    --mcp-config /tmp/extract-channel-mcp.json \
    --dangerously-load-development-channels server:extract-channel \
    --model claude-haiku-4-5 \
    --effort low \
    --permission-mode bypassPermissions
  EXIT_CODE=$?
  set -e
  END_TIME=$(date +%s)
  UPTIME=$((END_TIME - START_TIME))
  echo "[$(date)] EXIT code=$EXIT_CODE uptime=${UPTIME}s attempt=$RESTART_COUNT" >> "$RESTART_LOG"

  if [ "$UPTIME" -ge 300 ]; then
    mark_healthy
  fi

  check_context_exhaustion "extract-channel" "$UPTIME" "$RESTART_COUNT"
  handle_restart "extract-channel" "$EXIT_CODE" "$RESTART_COUNT"
done

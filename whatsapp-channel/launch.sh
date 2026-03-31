#!/bin/bash
# Launch Claude Code with the WhatsApp Channel connected.
# Auto-restarts on crash. Run in a tmux session.
#
# Usage: bash /mnt/c/Users/Chris\ Hadley/claude-projects/discord-messenger/whatsapp-channel/launch.sh

set -euo pipefail

CHANNEL_DIR="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/whatsapp-channel"
PROJECT_ROOT="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger"
WORKING_DIR="$HOME/peterbot"
ENVFILE="$CHANNEL_DIR/.env"
ROOT_ENVFILE="$PROJECT_ROOT/.env"
RESTART_LOG="/tmp/whatsapp-channel-restarts.log"

# Channel-specific config from local .env
HTTP_PORT=$(grep HTTP_PORT "$ENVFILE" | cut -d= -f2 | tr -d "\r\n")
HADLEY_API=$(grep HADLEY_API "$ENVFILE" | cut -d= -f2 | tr -d "\r\n")
# Shared secrets from root .env (single source of truth)
HADLEY_AUTH_KEY=$(grep HADLEY_AUTH_KEY "$ROOT_ENVFILE" | cut -d= -f2 | tr -d "\r\n")

cat > /tmp/whatsapp-channel-mcp.json <<EOF
{
  "mcpServers": {
    "whatsapp-channel": {
      "command": "$CHANNEL_DIR/node_modules/.bin/tsx",
      "args": ["$CHANNEL_DIR/src/index.ts"],
      "env": {
        "HTTP_PORT": "${HTTP_PORT:-8102}",
        "HADLEY_API": "${HADLEY_API:-http://172.19.64.1:8100}",
        "HADLEY_AUTH_KEY": "${HADLEY_AUTH_KEY:-}",
        "NODE_PATH": "$CHANNEL_DIR/node_modules"
      }
    }
  }
}
EOF

cd "$WORKING_DIR"

source "$PROJECT_ROOT/scripts/channel-resilience.sh"

RESTART_COUNT=0
while true; do
  RESTART_COUNT=$((RESTART_COUNT + 1))
  echo "[$(date)] Starting WhatsApp channel session (attempt $RESTART_COUNT)..."
  echo "[$(date)] START attempt=$RESTART_COUNT" >> "$RESTART_LOG"

  # Auto-accept startup prompts in background
  bash "$PROJECT_ROOT/scripts/auto-accept-prompts.sh" whatsapp-channel &

  START_TIME=$(date +%s)
  set +e
  claude \
    --mcp-config /tmp/whatsapp-channel-mcp.json \
    --dangerously-load-development-channels server:whatsapp-channel \
    --model claude-opus-4-6 \
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

  check_context_exhaustion "whatsapp-channel" "$UPTIME" "$RESTART_COUNT"
  handle_restart "whatsapp-channel" "$EXIT_CODE" "$RESTART_COUNT"
done

#!/bin/bash
# Launch Claude Code with the Jobs Channel connected.
# Auto-restarts on crash. Run in a tmux session.
#
# Usage: bash /mnt/c/Users/Chris\ Hadley/claude-projects/discord-messenger/jobs-channel/launch.sh

set -euo pipefail

CHANNEL_DIR="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/jobs-channel"
WORKING_DIR="$HOME/peterbot"
ENVFILE="$CHANNEL_DIR/.env"
RESTART_LOG="/tmp/jobs-channel-restarts.log"

HTTP_PORT=$(grep HTTP_PORT "$ENVFILE" | cut -d= -f2 | tr -d "\r\n")
JOB_TIMEOUT_MS=$(grep JOB_TIMEOUT_MS "$ENVFILE" | cut -d= -f2 | tr -d "\r\n")

cat > /tmp/jobs-channel-mcp.json <<EOF
{
  "mcpServers": {
    "jobs-channel": {
      "command": "npx",
      "args": ["--yes", "tsx", "$CHANNEL_DIR/src/index.ts"],
      "env": {
        "HTTP_PORT": "${HTTP_PORT:-8103}",
        "JOB_TIMEOUT_MS": "${JOB_TIMEOUT_MS:-180000}",
        "NODE_PATH": "$CHANNEL_DIR/node_modules"
      }
    }
  }
}
EOF

cd "$WORKING_DIR"

RESTART_COUNT=0
while true; do
  RESTART_COUNT=$((RESTART_COUNT + 1))
  echo "[$(date)] Starting Jobs channel session (attempt $RESTART_COUNT)..."
  echo "[$(date)] START attempt=$RESTART_COUNT" >> "$RESTART_LOG"

  claude \
    --mcp-config /tmp/jobs-channel-mcp.json \
    --dangerously-load-development-channels server:jobs-channel \
    --model claude-opus-4-6 \
    --effort medium \
    --dangerously-skip-permissions || true

  EXIT_CODE=$?
  echo "[$(date)] Session exited (code $EXIT_CODE), restarting in 10s..."
  echo "[$(date)] EXIT code=$EXIT_CODE attempt=$RESTART_COUNT" >> "$RESTART_LOG"
  sleep 10
done

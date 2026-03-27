#!/bin/bash
# Launch Claude Code with the WhatsApp Channel connected.
# Auto-restarts on crash. Run in a tmux session.
#
# Usage: bash /mnt/c/Users/Chris\ Hadley/claude-projects/discord-messenger/whatsapp-channel/launch.sh

set -euo pipefail

CHANNEL_DIR="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/whatsapp-channel"
WORKING_DIR="$HOME/peterbot"
ENVFILE="$CHANNEL_DIR/.env"
RESTART_LOG="/tmp/whatsapp-channel-restarts.log"

HTTP_PORT=$(grep HTTP_PORT "$ENVFILE" | cut -d= -f2 | tr -d "\r\n")
HADLEY_API=$(grep HADLEY_API "$ENVFILE" | cut -d= -f2 | tr -d "\r\n")
HADLEY_AUTH_KEY=$(grep HADLEY_AUTH_KEY "$ENVFILE" | cut -d= -f2 | tr -d "\r\n")

cat > /tmp/whatsapp-channel-mcp.json <<EOF
{
  "mcpServers": {
    "whatsapp-channel": {
      "command": "npx",
      "args": ["--yes", "tsx", "$CHANNEL_DIR/src/index.ts"],
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

RESTART_COUNT=0
while true; do
  RESTART_COUNT=$((RESTART_COUNT + 1))
  echo "[$(date)] Starting WhatsApp channel session (attempt $RESTART_COUNT)..."
  echo "[$(date)] START attempt=$RESTART_COUNT" >> "$RESTART_LOG"

  # Auto-accept startup prompts in background
  bash "/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/scripts/auto-accept-prompts.sh" whatsapp-channel &

  claude \
    --mcp-config /tmp/whatsapp-channel-mcp.json \
    --dangerously-load-development-channels server:whatsapp-channel \
    --model claude-opus-4-6 \
    --effort medium \
    --permission-mode bypassPermissions || true

  EXIT_CODE=$?
  echo "[$(date)] Session exited (code $EXIT_CODE), restarting in 10s..."
  echo "[$(date)] EXIT code=$EXIT_CODE attempt=$RESTART_COUNT" >> "$RESTART_LOG"
  sleep 10
done

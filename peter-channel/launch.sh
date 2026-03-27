#!/bin/bash
# Launch Claude Code with the Peter Discord Channel connected.
# Auto-restarts on crash. Run in a tmux session.
#
# Usage: bash /mnt/c/Users/Chris\ Hadley/claude-projects/discord-messenger/peter-channel/launch.sh

set -euo pipefail

CHANNEL_DIR="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/peter-channel"
WORKING_DIR="$HOME/peterbot"
ENVFILE="$CHANNEL_DIR/.env"
RESTART_LOG="/tmp/peter-channel-restarts.log"

# Read .env (handles Windows line endings)
DISCORD_BOT_TOKEN=$(grep DISCORD_BOT_TOKEN "$ENVFILE" | cut -d= -f2 | tr -d "\r\n")
DISCORD_CHANNEL_IDS=$(grep DISCORD_CHANNEL_IDS "$ENVFILE" | cut -d= -f2 | tr -d "\r\n")
ALLOWED_DISCORD_IDS=$(grep ALLOWED_DISCORD_IDS "$ENVFILE" | cut -d= -f2 | tr -d "\r\n")

for var in DISCORD_BOT_TOKEN DISCORD_CHANNEL_IDS ALLOWED_DISCORD_IDS; do
  if [ -z "${!var}" ]; then
    echo "ERROR: $var not set in .env" >&2
    exit 1
  fi
done

cat > /tmp/peter-channel-mcp.json <<EOF
{
  "mcpServers": {
    "peter-channel": {
      "command": "npx",
      "args": ["--yes", "tsx", "$CHANNEL_DIR/src/index.ts"],
      "env": {
        "DISCORD_BOT_TOKEN": "$DISCORD_BOT_TOKEN",
        "DISCORD_CHANNEL_IDS": "$DISCORD_CHANNEL_IDS",
        "ALLOWED_DISCORD_IDS": "$ALLOWED_DISCORD_IDS",
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
  echo "[$(date)] Starting Discord channel session (attempt $RESTART_COUNT)..."
  echo "[$(date)] START attempt=$RESTART_COUNT" >> "$RESTART_LOG"

  claude \
    --mcp-config /tmp/peter-channel-mcp.json \
    --dangerously-load-development-channels server:peter-channel \
    --model claude-opus-4-6 \
    --effort medium \
    --dangerously-skip-permissions || true

  EXIT_CODE=$?
  echo "[$(date)] Session exited (code $EXIT_CODE), restarting in 10s..."
  echo "[$(date)] EXIT code=$EXIT_CODE attempt=$RESTART_COUNT" >> "$RESTART_LOG"
  sleep 10
done

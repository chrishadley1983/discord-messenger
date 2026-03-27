#!/bin/bash
# Auto-accept Claude Code startup prompts by sending Enter keys to the tmux session.
# Called by launch scripts: auto-accept-prompts.sh <session-name>
#
# Watches the tmux pane for "Enter to confirm" and sends Enter.
# Runs in background, exits after 60s or when Claude Code is fully started.

SESSION="${1:?Usage: auto-accept-prompts.sh <session-name>}"
MAX_WAIT=60
WAITED=0

while [ $WAITED -lt $MAX_WAIT ]; do
  sleep 2
  WAITED=$((WAITED + 2))

  PANE=$(tmux capture-pane -t "$SESSION" -p 2>/dev/null || echo "")

  if echo "$PANE" | grep -q "Enter to confirm"; then
    tmux send-keys -t "$SESSION" Enter
    echo "[auto-accept] Sent Enter for prompt in $SESSION (${WAITED}s)"
    sleep 2
    continue  # Check again in case there's a second prompt
  fi

  # If we see the Claude Code prompt (❯), startup is complete
  if echo "$PANE" | grep -q "❯"; then
    echo "[auto-accept] $SESSION startup complete (${WAITED}s)"
    exit 0
  fi
done

echo "[auto-accept] $SESSION timed out after ${MAX_WAIT}s"

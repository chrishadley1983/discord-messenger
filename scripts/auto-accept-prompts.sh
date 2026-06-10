#!/bin/bash
# Persistent auto-accept watcher for a Claude Code channel tmux pane.
# Called by launch scripts: auto-accept-prompts.sh <session-name>
#
# Handles two prompt classes that block unattended channel sessions:
#   1. Startup prompts ("Enter to confirm" — dev-channel + initial permission).
#   2. Mid-session file-edit modals ("Do you want to make this edit ...").
#      bypassPermissions does NOT auto-clear these when the target lives under
#      .claude/ (skills, settings, hooks): Claude Code treats them as
#      self-/settings edits and prompts even in bypass mode. Peter's skills live
#      at ~/peterbot/.claude/skills/*, so editing them used to freeze the turn
#      indefinitely with nobody to press a key. When the modal offers
#      "...allow Claude to edit its own settings for this session" we pick that
#      (option 2) so the rest of the session's .claude/ edits don't re-prompt.
#
# Runs for the lifetime of the tmux session (not just 60s at startup).
# Singleton per session via flock — safe to call on every channel restart;
# a second invocation exits while the first keeps serving.

SESSION="${1:?Usage: auto-accept-prompts.sh <session-name>}"
LOCK="/tmp/auto-accept-${SESSION}.lock"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[auto-accept] watcher already running for $SESSION; exiting"
  exit 0
fi

echo "[auto-accept] persistent watcher started for $SESSION (pid $$)"

while true; do
  sleep 2

  PANE=$(tmux capture-pane -t "$SESSION" -p 2>/dev/null) || { sleep 5; continue; }

  # File-edit / create / write confirmation modal (the .claude/ self-edit gate)
  if echo "$PANE" | grep -qE "Do you want to make this edit|Do you want to create|Do you want to (write|overwrite)"; then
    if echo "$PANE" | grep -q "allow Claude to edit its own settings"; then
      # Option 2: allow .claude/ self-edits for the rest of the session
      tmux send-keys -t "$SESSION" "2"
      tmux send-keys -t "$SESSION" Enter
      echo "[auto-accept] $(date +%T) edit modal: sent 2 (allow self-edit for session) to $SESSION"
    else
      # Accept the highlighted default (Yes)
      tmux send-keys -t "$SESSION" Enter
      echo "[auto-accept] $(date +%T) edit modal: sent Enter to $SESSION"
    fi
    sleep 2
    continue
  fi

  # Startup confirmation prompts (dev channels + initial permission grant)
  if echo "$PANE" | grep -q "Enter to confirm"; then
    tmux send-keys -t "$SESSION" Enter
    echo "[auto-accept] $(date +%T) startup prompt: sent Enter to $SESSION"
    sleep 2
    continue
  fi
done

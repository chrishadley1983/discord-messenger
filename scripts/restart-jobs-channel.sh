#!/bin/bash
# One-shot: cleanly restart the jobs-channel tmux session so it reloads
# ~/.claude/.credentials.json (token re-auth 2026-06-20).
set -u
NAME="jobs-channel"
SCRIPT="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/jobs-channel/launch.sh"
tmux kill-session -t "$NAME" 2>/dev/null && echo "killed old $NAME" || echo "no existing $NAME"
sleep 1
tmux new-session -d -s "$NAME" -c "$HOME/peterbot" "bash \"$SCRIPT\""
echo "relaunched $NAME"
sleep 2
tmux ls | grep "$NAME"

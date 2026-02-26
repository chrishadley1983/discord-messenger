#!/bin/bash
# Kill orphaned Claude subagents and chroma-mcp processes in WSL
echo "Before:"
free -h
echo "---"

# Kill Claude subagent processes (spawned by claude-mem worker)
echo "Killing Claude subagents..."
for pid in $(ps -eo pid,args | grep 'claude.*disallowedTools' | grep -v grep | awk '{print $1}'); do
    kill -9 "$pid" 2>/dev/null
done

# Kill chroma-mcp processes
echo "Killing chroma-mcp..."
for pid in $(ps -eo pid,args | grep 'chroma-mcp' | grep -v grep | awk '{print $1}'); do
    kill -9 "$pid" 2>/dev/null
done

# Kill stale peter tmux session
tmux kill-session -t peter 2>/dev/null

sleep 3

echo "---"
echo "After:"
free -h
echo "---"
echo "Remaining claude processes:"
ps aux | grep claude | grep -v grep | wc -l

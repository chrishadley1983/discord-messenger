#!/bin/bash
# Kill orphaned claude-mem worker processes
pids=$(ps aux | grep 'claude.*stream-json.*disallowedTools' | grep -v grep | awk '{print $2}')
count=$(echo "$pids" | grep -c '[0-9]')
echo "Found $count orphaned claude-mem processes"
if [ "$count" -gt 0 ]; then
    echo "$pids" | xargs kill -9 2>/dev/null
    sleep 1
    remaining=$(ps aux | grep 'claude.*stream-json.*disallowedTools' | grep -v grep | wc -l)
    echo "Killed. Remaining: $remaining"
else
    echo "None to kill"
fi

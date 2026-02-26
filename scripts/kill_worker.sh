#!/bin/bash
# Kill the claude-mem worker daemon and all its children
WORKER_PID=576826

echo "Killing worker daemon $WORKER_PID and children..."
kill -9 $WORKER_PID 2>/dev/null

# Kill any remaining children
for pid in $(ps -eo pid,ppid | awk -v ppid=$WORKER_PID '$2==ppid {print $1}'); do
    kill -9 "$pid" 2>/dev/null
done

sleep 2
echo "Memory after cleanup:"
free -h
echo "---"
echo "Remaining claude processes:"
ps aux | grep claude | grep -v grep | wc -l

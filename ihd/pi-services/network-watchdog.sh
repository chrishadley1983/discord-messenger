#!/bin/bash
# Network watchdog — restarts WiFi if DNS/connectivity is lost
# Runs every 2 minutes via cron

LOG="/home/chrishadley1983/network-watchdog.log"
MAX_LOG_LINES=500

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"
}

# Trim log if it gets too long
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt "$MAX_LOG_LINES" ]; then
    tail -n 200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

# Test 1: Can we ping the gateway?
GATEWAY=$(ip route | awk '/default/ {print $3}' | head -1)
ping -c 2 -W 3 "$GATEWAY" > /dev/null 2>&1
GATEWAY_OK=$?

# Test 2: Can we resolve DNS?
ping -c 2 -W 3 1.1.1.1 > /dev/null 2>&1
DNS_PING_OK=$?

# Test 3: Can we actually resolve a hostname?
nslookup google.com 1.1.1.1 > /dev/null 2>&1
DNS_RESOLVE_OK=$?

if [ $GATEWAY_OK -eq 0 ] && [ $DNS_PING_OK -eq 0 ] && [ $DNS_RESOLVE_OK -eq 0 ]; then
    # All good — no log spam, just exit
    exit 0
fi

# Something's wrong — log what failed
log "FAILURE DETECTED: gateway=$GATEWAY_OK dns_ping=$DNS_PING_OK dns_resolve=$DNS_RESOLVE_OK"

# Try restarting the WiFi connection
log "Restarting WiFi connection..."
nmcli device disconnect wlan0 2>> "$LOG"
sleep 3
nmcli device connect wlan0 2>> "$LOG"
sleep 5

# Verify recovery
ping -c 2 -W 3 1.1.1.1 > /dev/null 2>&1
if [ $? -eq 0 ]; then
    log "RECOVERED: WiFi restart successful"
else
    log "STILL DOWN after WiFi restart — trying full NetworkManager restart"
    sudo systemctl restart NetworkManager 2>> "$LOG"
    sleep 10
    ping -c 2 -W 3 1.1.1.1 > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        log "RECOVERED: NetworkManager restart successful"
    else
        log "STILL DOWN after NetworkManager restart — may need manual intervention"
    fi
fi

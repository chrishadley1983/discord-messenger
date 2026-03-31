#!/bin/bash
# Shared resilience functions for channel launch scripts.
# Source this file from launch.sh: source "$PROJECT_ROOT/scripts/channel-resilience.sh"
#
# Provides:
#   - Crash loop detection with exponential backoff
#   - Discord #alerts webhook alerting
#   - Restart tracking

# --- Config ---
CRASH_LOOP_WINDOW=600        # 10 minutes (seconds)
CRASH_LOOP_THRESHOLD=5       # Max restarts before circuit-breaking
CRASH_LOOP_COOLDOWN=300      # 5 minutes cooldown after circuit break
BACKOFF_INITIAL=10           # Starting backoff (seconds)
BACKOFF_MAX=300              # Max backoff cap (5 minutes)
BACKOFF_MULTIPLIER=2         # Exponential multiplier

# --- State ---
_restart_timestamps=()
_current_backoff=$BACKOFF_INITIAL
_circuit_broken=false

# --- Discord alerting ---
_send_alert() {
  local message="$1"
  local webhook_url="${DISCORD_WEBHOOK_ALERTS:-}"

  if [ -z "$webhook_url" ]; then
    # Try to read from root .env
    local root_env="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/.env"
    if [ -f "$root_env" ]; then
      webhook_url=$(grep DISCORD_WEBHOOK_ALERTS "$root_env" | cut -d= -f2- | tr -d "\r\n")
    fi
  fi

  if [ -z "$webhook_url" ]; then
    echo "[ALERT] No webhook URL — logging only: $message"
    return
  fi

  # Fire-and-forget curl (don't block restart loop)
  curl -s -H "Content-Type: application/json" \
    -d "{\"content\": \"$message\"}" \
    "$webhook_url" > /dev/null 2>&1 &
}

# --- Crash loop detection ---
_record_restart() {
  local now
  now=$(date +%s)
  _restart_timestamps+=("$now")

  # Prune timestamps older than the window
  local cutoff=$((now - CRASH_LOOP_WINDOW))
  local pruned=()
  for ts in "${_restart_timestamps[@]}"; do
    if [ "$ts" -ge "$cutoff" ]; then
      pruned+=("$ts")
    fi
  done
  _restart_timestamps=("${pruned[@]}")
}

_is_crash_loop() {
  if [ "${#_restart_timestamps[@]}" -ge "$CRASH_LOOP_THRESHOLD" ]; then
    return 0  # true — crash loop detected
  fi
  return 1  # false
}

_get_backoff() {
  echo "$_current_backoff"
}

_increase_backoff() {
  _current_backoff=$(( _current_backoff * BACKOFF_MULTIPLIER ))
  if [ "$_current_backoff" -gt "$BACKOFF_MAX" ]; then
    _current_backoff=$BACKOFF_MAX
  fi
}

_reset_backoff() {
  _current_backoff=$BACKOFF_INITIAL
}

# --- Main restart handler ---
# Call this instead of a simple `sleep 10` after Claude exits.
# Usage: handle_restart "$CHANNEL_NAME" "$EXIT_CODE" "$RESTART_COUNT"
handle_restart() {
  local channel_name="$1"
  local exit_code="$2"
  local restart_count="$3"

  _record_restart

  if _is_crash_loop; then
    if [ "$_circuit_broken" = false ]; then
      _circuit_broken=true
      local msg="🔴 **${channel_name}** crash loop detected — ${#_restart_timestamps[@]} restarts in ${CRASH_LOOP_WINDOW}s. Pausing for ${CRASH_LOOP_COOLDOWN}s."
      echo "[$(date)] CRASH LOOP: $msg"
      _send_alert "$msg"
    fi

    echo "[$(date)] Circuit broken — cooling down for ${CRASH_LOOP_COOLDOWN}s..."
    sleep "$CRASH_LOOP_COOLDOWN"

    # Reset after cooldown
    _restart_timestamps=()
    _circuit_broken=false
    _reset_backoff
    echo "[$(date)] Cooldown complete — resuming with fresh backoff"
    return
  fi

  # Normal restart with exponential backoff
  local backoff
  backoff=$(_get_backoff)

  echo "[$(date)] Session exited (code $exit_code), restarting in ${backoff}s (attempt $restart_count)..."

  # Alert on repeated failures (but not crash loop — that has its own alert)
  if [ "$restart_count" -ge 3 ] && [ "$(( restart_count % 3 ))" -eq 0 ]; then
    _send_alert "⚠️ **${channel_name}** has restarted ${restart_count} times. Last exit code: ${exit_code}. Backoff: ${backoff}s."
  fi

  sleep "$backoff"
  _increase_backoff
}

# Call this when a session has been running successfully for a while
# (e.g., after receiving first message). Resets backoff.
mark_healthy() {
  _reset_backoff
  _circuit_broken=false
}

# Call after session exits with uptime info to detect context exhaustion.
# Usage: check_context_exhaustion "$CHANNEL_NAME" "$UPTIME_SECONDS" "$RESTART_COUNT"
check_context_exhaustion() {
  local channel_name="$1"
  local uptime="$2"
  local restart_count="$3"

  # If session ran for >1 hour then exited, likely context window exhaustion
  if [ "$uptime" -ge 3600 ]; then
    _send_alert "🟡 **${channel_name}** session ended after ${uptime}s ($(( uptime / 3600 ))h $(( (uptime % 3600) / 60 ))m). Likely context window exhaustion — restarting with fresh context."
  fi

  # Log restart event to a JSON file for dashboard visibility
  local events_file="/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/data/channel_restarts.jsonl"
  echo "{\"channel\":\"${channel_name}\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"uptime_s\":${uptime},\"restart_count\":${restart_count},\"reason\":\"$([ $uptime -ge 3600 ] && echo 'context_exhaustion' || echo 'crash')\"}" >> "$events_file"
}

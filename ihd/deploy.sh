#!/bin/bash
# Deploy IHD dashboard to Raspberry Pi
# Usage: bash deploy.sh

set -e

PI="chrishadley1983@192.168.0.110"
APP_DIR="ihd-app"
SSH="ssh -o ServerAliveInterval=60 -o ConnectTimeout=5"
TEMP_TAR=$(mktemp).tar.gz

echo "📦 Packaging..."
tar --exclude='node_modules' --exclude='.next' --exclude='.git' --exclude='.data' --exclude='screenshot-*.png' \
  -czf "$TEMP_TAR" -C "$(dirname "$0")/$APP_DIR" .

echo "🚀 Uploading to Pi..."
scp -o ServerAliveInterval=60 "$TEMP_TAR" "$PI:~/ihd-app.tar.gz"
rm "$TEMP_TAR"

echo "📂 Extracting on Pi..."
$SSH "$PI" "cd ~/ihd-app && tar -xzf ~/ihd-app.tar.gz && rm ~/ihd-app.tar.gz"

echo "🔨 Building on Pi (this takes a minute)..."
$SSH "$PI" "cd ~/ihd-app && npm install --prefer-offline && npx next build"

echo "♻️  Restarting dashboard..."
$SSH "$PI" "pm2 restart ihd"

echo "🔄 Refreshing kiosk browser..."
sleep 3
$SSH "$PI" "WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/\$(id -u) wtype -k F5" 2>/dev/null || echo "  (browser refresh skipped — wtype not available)"

echo "✅ Deployed! Dashboard at http://192.168.0.110:3000"

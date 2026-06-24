#!/bin/bash
# Run this on the Pi to set up the sensor API
# Usage: bash setup.sh

set -e

INSTALL_DIR="$HOME/sensor-api"

echo "Setting up sensor API in $INSTALL_DIR..."

mkdir -p "$INSTALL_DIR"
cp main.py requirements.txt "$INSTALL_DIR/"

cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "Installing systemd service..."
sudo cp dashboard-sensor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dashboard-sensor
sudo systemctl start dashboard-sensor

echo "Done! Sensor API running on port 5000"
echo "Test: curl http://localhost:5000/sensor"

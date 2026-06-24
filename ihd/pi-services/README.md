# Pi-side services (on the dashboard Pi `chrishadley1983@192.168.0.110`)

These run on the Raspberry Pi 5 that serves the IHD kitchen dashboard. Pulled off
the Pi via SSH on 2026-06-24 so they're version-controlled (previously they lived
only on the Pi — changes had been SSH'd to the Pi directly after the initial build).

| Service | Port | Runs via | What it does |
|---------|------|----------|--------------|
| `zigbee-api/server.py` | **5001** | pm2 (`zigbee-api`) | MQTT→HTTP bridge. Subscribes to `zigbee2mqtt/sensor_kitchen|sensor_bedroom|motion_lounge`, keeps the latest reading in memory (served at `/`), and **logs to SQLite `~/.data/sensors.db`** (tables `readings` + `motion_events`, throttled to 1 row / 5 min / device). Serves `/history?device=&hours=&type=readings|motion` — **this is the ~30-day store that feeds Peter's `/home/sensors/trend`** and the dashboard trend chart. |
| `screen-control/controller.py` | **5002** | pm2 (`screen-control`) | Motion sensor → display on/off/dim state. Serves `/` (state) and `POST /wake`. |
| `media-overlay/` | — | launched on demand by the IHD app's `/api/media` | `launch.sh` + `close-overlay.py` + `close.html` — the floating "close" button overlaid on the Chromium media kiosk (Netflix/YouTube/NowTV). |
| `sensor/main.py` | 5000 | systemd `dashboard-sensor.service` | BME280 I2C temp/humidity/pressure API (a *separate*, history-less sensor; not consumed by the current dashboard). |
| `network-watchdog.sh` | — | **cron** `*/2 * * * *` | Every 2 min: ping gateway + DNS; on failure, bounces `wlan0` via `nmcli`. Logs to `~/network-watchdog.log`. (Note: did not recover the full WiFi drop on 2026-06-23 — see [[home-sensors-and-pi-recovery]] for the cloud-init recovery.) |
| `test_bme280.py` | — | manual | One-off BME280 read test. |

## Run mechanism

- **pm2** runs `ihd` (the Next.js app, port 3000), `zigbee-api` (5001) and
  `screen-control` (5002). `pm2 list` on the Pi shows all three. Restart a
  service: `pm2 restart zigbee-api`. Resurrect on boot: `pm2 save` + `pm2 startup`.
- **cron** runs `network-watchdog.sh` every 2 minutes (`crontab -l`).
- **systemd** runs only `dashboard-sensor.service` (the BME280 `:5000` API) and
  `zigbee2mqtt.service` (the Z2M stack itself, `/opt/zigbee2mqtt`).

## Not copied
- `~/.data/sensors.db` — the live history DB (stays on the Pi; it's data, not code).
- Python virtualenvs / `node_modules` (regenerable). `server.py`/`controller.py`
  depend on `paho-mqtt`.

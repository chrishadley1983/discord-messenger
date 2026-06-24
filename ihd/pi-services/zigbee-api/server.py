"""Lightweight MQTT→HTTP bridge for Zigbee2MQTT sensor data with SQLite logging."""
import json
import os
import sqlite3
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import paho.mqtt.client as mqtt

# Latest readings stored in memory
sensors = {}
lock = threading.Lock()

DB_PATH = os.path.expanduser("~/.data/sensors.db")

TOPICS = [
    "zigbee2mqtt/sensor_kitchen",
    "zigbee2mqtt/sensor_bedroom",
    "zigbee2mqtt/motion_lounge",
]

# ── SQLite setup ─────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            device TEXT NOT NULL,
            temperature REAL,
            humidity REAL,
            battery INTEGER,
            linkquality INTEGER
        );
        CREATE TABLE IF NOT EXISTS motion_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            device TEXT NOT NULL,
            occupancy INTEGER NOT NULL,
            illuminance REAL,
            battery INTEGER,
            linkquality INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_readings_device_ts ON readings(device, ts);
        CREATE INDEX IF NOT EXISTS idx_motion_device_ts ON motion_events(device, ts);
    """)
    conn.close()

# ── Throttle: only log temp/humidity every 5 minutes per device ──────

last_logged = {}
LOG_INTERVAL = 300  # seconds

def should_log_reading(device):
    now = time.time()
    key = device
    if key not in last_logged or (now - last_logged[key]) >= LOG_INTERVAL:
        last_logged[key] = now
        return True
    return False

# ── Motion dedup: only log when occupancy state actually changes ─────

last_occupancy = {}

def occupancy_changed(device, new_occ):
    prev = last_occupancy.get(device)
    last_occupancy[device] = new_occ
    return prev is None or prev != new_occ

# ── MQTT handlers ────────────────────────────────────────────────────

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload)
        name = msg.topic.split("/")[-1]

        with lock:
            sensors[name] = {
                "temperature": data.get("temperature"),
                "humidity": data.get("humidity"),
                "battery": data.get("battery"),
                "linkquality": data.get("linkquality"),
                "occupancy": data.get("occupancy"),
                "illuminance": data.get("illuminance"),
            }

        # Log to SQLite
        if name.startswith("motion_"):
            occ = 1 if data.get("occupancy") else 0
            if occupancy_changed(name, occ):
                try:
                    conn = get_db()
                    conn.execute(
                        "INSERT INTO motion_events (device,occupancy,illuminance,battery,linkquality) VALUES (?,?,?,?,?)",
                        (name, occ, data.get("illuminance"), data.get("battery"), data.get("linkquality")),
                    )
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
        elif name.startswith("sensor_") and should_log_reading(name):
            try:
                conn = get_db()
                conn.execute(
                    "INSERT INTO readings (device,temperature,humidity,battery,linkquality) VALUES (?,?,?,?,?)",
                    (name, data.get("temperature"), data.get("humidity"), data.get("battery"), data.get("linkquality")),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    except Exception:
        pass

def on_connect(client, userdata, flags, reason_code, properties):
    for t in TOPICS:
        client.subscribe(t)

# ── HTTP handler ─────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/history":
            self._handle_history(parse_qs(parsed.query))
        else:
            # Default: return latest readings
            with lock:
                data = dict(sensors)
            self._json_response(data)

    def _handle_history(self, params):
        device = params.get("device", [None])[0]
        hours = int(params.get("hours", ["24"])[0])
        kind = params.get("type", ["readings"])[0]  # readings or motion

        try:
            conn = get_db()
            if kind == "motion":
                query = "SELECT ts, device, occupancy, illuminance, battery FROM motion_events WHERE ts >= datetime('now', ?)"
                args = [f"-{hours} hours"]
                if device:
                    query += " AND device = ?"
                    args.append(device)
                query += " ORDER BY ts ASC"
                rows = conn.execute(query, args).fetchall()
                result = [dict(r) for r in rows]
            else:
                query = "SELECT ts, device, temperature, humidity, battery FROM readings WHERE ts >= datetime('now', ?)"
                args = [f"-{hours} hours"]
                if device:
                    query += " AND device = ?"
                    args.append(device)
                query += " ORDER BY ts ASC"
                rows = conn.execute(query, args).fetchall()
                result = [dict(r) for r in rows]
            conn.close()
            self._json_response(result)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _json_response(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # suppress request logs

# ── Cleanup old data (runs daily) ────────────────────────────────────

def cleanup_old_data():
    """Delete readings older than 90 days."""
    while True:
        time.sleep(86400)
        try:
            conn = get_db()
            conn.execute("DELETE FROM readings WHERE ts < datetime('now', '-90 days')")
            conn.execute("DELETE FROM motion_events WHERE ts < datetime('now', '-90 days')")
            conn.commit()
            conn.close()
        except Exception:
            pass

# ── Main ─────────────────────────────────────────────────────────────

init_db()

cleanup_thread = threading.Thread(target=cleanup_old_data, daemon=True)
cleanup_thread.start()

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect("localhost", 1883)
mqtt_client.loop_start()

print("Zigbee sensor API running on :5001 (with SQLite logging + motion dedup)")
HTTPServer(("", 5001), Handler).serve_forever()

"""Screen controller: motion sensor → display state management."""
import json
import time
import threading
import subprocess
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import paho.mqtt.client as mqtt

# --- Config ---
# The lounge motion sensor (motion_lounge) has been dead since ~Mar 2026, so
# this is touch-driven only. Resting state is the clock face ("dim"), never a
# fully-black "off" screen — that was indistinguishable from a crashed kiosk and
# gave no power saving anyway (the LCD backlight stays on regardless of content).
REST_TIMEOUT = 180      # seconds of no touch → revert to clock face
NIGHT_START = 23        # 23:00
NIGHT_END = 6           # 06:00
DISPLAY = "HDMI-A-1"
MQTT_RETRY_INTERVAL = 30  # seconds between MQTT reconnection attempts

# Wayland env for wlopm/wlr-randr
WENV = dict(os.environ)
WENV["WAYLAND_DISPLAY"] = "wayland-0"
WENV["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

# --- State ---
state = "active"  # active | dim | off
last_motion = time.time()
lock = threading.Lock()
mqtt_connected = False

def run_cmd(cmd):
    """Run a shell command with Wayland env."""
    try:
        subprocess.run(cmd, shell=True, env=WENV, capture_output=True, timeout=5)
    except Exception as e:
        print(f"CMD error: {e}")

def is_night():
    """Check if current time is in night mode (23:00 - 06:00)."""
    h = time.localtime().tm_hour
    return h >= NIGHT_START or h < NIGHT_END

def get_target_state(idle_secs):
    """Show the dashboard while in use; rest on the clock face after REST_TIMEOUT.

    Never returns "off" — the screen always shows at least the clock, so a black
    frame unambiguously means a crashed/frozen kiosk (which the kiosk-watchdog
    recovers). A touch resets the idle timer and brings the dashboard back.
    """
    if idle_secs < REST_TIMEOUT:
        return "active"
    return "dim"  # clock face

def transition(new_state):
    """Transition to a new screen state."""
    global state
    if new_state == state:
        return

    old = state
    state = new_state
    print(f"State: {old} → {new_state}")

def wake():
    """Simulate motion to wake the screen."""
    global last_motion
    with lock:
        last_motion = time.time()
    print("Wake triggered (touch)")

# --- MQTT with reconnection ---
def on_connect(client, userdata, flags, reason_code, properties):
    global mqtt_connected
    mqtt_connected = True
    client.subscribe("zigbee2mqtt/motion_lounge")
    print("Subscribed to motion_lounge")

def on_disconnect(client, userdata, flags, reason_code, properties):
    global mqtt_connected
    mqtt_connected = False
    print(f"MQTT disconnected (rc={reason_code})")

def on_message(client, userdata, msg):
    global last_motion
    try:
        data = json.loads(msg.payload)
        if data.get("occupancy"):
            with lock:
                last_motion = time.time()
                print(f"Motion detected (illuminance: {data.get('illuminance', '?')})")
    except Exception:
        pass

def mqtt_loop(client):
    """MQTT connection loop with auto-reconnect."""
    while True:
        if not mqtt_connected:
            try:
                client.connect("localhost", 1883)
                client.loop_start()
                print("MQTT connected")
            except Exception as e:
                print(f"MQTT connect failed: {e} — retrying in {MQTT_RETRY_INTERVAL}s")
                time.sleep(MQTT_RETRY_INTERVAL)
                continue
        time.sleep(MQTT_RETRY_INTERVAL)

# --- State loop ---
def state_loop():
    """Check idle time and transition states every 2 seconds."""
    while True:
        time.sleep(2)
        with lock:
            idle = time.time() - last_motion
        target = get_target_state(idle)
        transition(target)

# --- HTTP API ---
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        with lock:
            idle = time.time() - last_motion
        body = json.dumps({
            "state": state,
            "idle_seconds": round(idle),
            "night_mode": is_night(),
            "mqtt_connected": mqtt_connected,
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_POST(self):
        wake()
        body = json.dumps({"ok": True})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        pass

# --- Main ---
if __name__ == "__main__":
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_message

    # MQTT connection in background thread (retries if broker not ready)
    t_mqtt = threading.Thread(target=mqtt_loop, args=(mqtt_client,), daemon=True)
    t_mqtt.start()

    t_state = threading.Thread(target=state_loop, daemon=True)
    t_state.start()

    print("Screen controller running on :5002")
    HTTPServer(("", 5002), Handler).serve_forever()

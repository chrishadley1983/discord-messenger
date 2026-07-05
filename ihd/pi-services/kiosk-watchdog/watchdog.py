#!/usr/bin/env python3
"""
Kiosk watchdog for the IHD dashboard Pi.

Why this exists
---------------
The dashboard is a single Chromium tab (labwc autostart, no respawn loop) pointed
at http://localhost:3000. Over long uptimes the renderer can freeze or crash
("Aw, Snap!"), leaving a black/blank screen that ignores touch. The Next.js
server on :3000 stays healthy the whole time, so an HTTP health check can't see
the fault. The only reliable signal is what's actually on the framebuffer.

On 2026-07-05 the kiosk had been up ~9d20h and its renderer hung on the black
"screen off" overlay — tapping did nothing because the page's JS was dead.
Recovery was: kill the renderer -> Ctrl+R reload. This watchdog automates that.

Detection
---------
We only judge health when the screen-controller (:5002) reports state == "active",
because in that state the dashboard MUST be visible (large, image-rich frame).
When dim/off a black frame is legitimate, so we don't act. This also matches the
user-facing symptom exactly: someone walks up / taps -> state goes active -> if the
tab is frozen it stays black instead of showing the dashboard.

A grim screenshot of a healthy dashboard is ~120 KB; a pure-black frame is ~2.4 KB;
the "Aw, Snap!" crash page is ~18 KB. So when active, size < CONTENT_MIN_BYTES means
the tab is black / crashed / blank. We require two consecutive bad reads (to ride out
a genuine reload/paint) before recovering.

Recovery escalates: reload -> kill renderer + reload -> full Chromium relaunch.
A once-daily proactive reload keeps the tab from rotting over multi-day uptimes.
"""

import os
import subprocess
import sys
import time
import json
import urllib.request

# ---- Config ----
POLL_SECONDS = 60
CONTENT_MIN_BYTES = 40000      # healthy dashboard ~120KB; black ~2.4KB; aw-snap ~18KB
FAULT_THRESHOLD = 2            # consecutive bad reads before recovery
SCREEN_API = "http://localhost:5002/"
DAILY_RELOAD_HOUR = 4          # proactive reload at 04:xx local time
SHOT = "/tmp/kiosk_watchdog.png"

CHROMIUM_CMD = [
    "chromium",
    "--app=http://localhost:3000",
    "--start-maximized",
    "--enable-wayland-ime",
    "--noerrdialogs",
    "--disable-infobars",
    "--disable-session-crashed-bubble",
    "--disable-component-update",
    "--check-for-update-interval=31536000",
    "--no-first-run",
    "--autoplay-policy=no-user-gesture-required",
    "--password-store=basic",
    "--load-extension=/home/chrishadley1983/kiosk-touch-ext",
    "--ozone-platform=wayland",
]

# Wayland env so grim / wtype / chromium can reach the compositor when this
# process is launched by pm2 rather than from the graphical session.
WENV = dict(os.environ)
WENV.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
WENV.setdefault("WAYLAND_DISPLAY", "wayland-0")


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run(cmd, timeout=15):
    """Run a shell/argv command with the Wayland env; return (rc, out)."""
    try:
        p = subprocess.run(
            cmd, shell=isinstance(cmd, str), env=WENV,
            capture_output=True, timeout=timeout, text=True,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:  # noqa: BLE001
        return 1, f"exception: {e}"


def get_state():
    """Return screen-controller state string, or None if unreachable."""
    try:
        with urllib.request.urlopen(SCREEN_API, timeout=5) as r:
            return json.loads(r.read().decode()).get("state")
    except Exception:  # noqa: BLE001
        return None


def wake():
    """Tell the screen-controller we have activity (POST)."""
    try:
        req = urllib.request.Request(SCREEN_API, method="POST", data=b"")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:  # noqa: BLE001
        pass


def screenshot_size():
    """grim the output and return the PNG byte size, or -1 on failure."""
    try:
        if os.path.exists(SHOT):
            os.remove(SHOT)
    except OSError:
        pass
    rc, out = run(["grim", SHOT], timeout=15)
    if rc != 0 or not os.path.exists(SHOT):
        log(f"grim failed rc={rc} {out.strip()[:120]}")
        return -1
    return os.path.getsize(SHOT)


def content_healthy():
    """
    True if the framebuffer currently shows real content, False if it looks
    black/crashed, None if we can't tell (grim failed).
    """
    size = screenshot_size()
    if size < 0:
        return None
    return size >= CONTENT_MIN_BYTES


def reload_tab():
    log("recovery: sending Ctrl+R reload")
    wake()
    run(["wtype", "-M", "ctrl", "r", "-m", "ctrl"], timeout=10)


def kill_renderer():
    log("recovery: killing frozen chromium renderer")
    run("pkill -f 'chromium.*type=renderer'", timeout=10)


def relaunch_chromium():
    log("recovery: full chromium relaunch")
    run("pkill -f 'chromium --app'", timeout=10)
    time.sleep(2)
    try:
        subprocess.Popen(
            CHROMIUM_CMD, env=WENV, start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as e:  # noqa: BLE001
        log(f"relaunch failed: {e}")


def verify_recovered(wait_s):
    """Wake, wait for paint, screenshot; return True if content is back."""
    time.sleep(wait_s)
    wake()
    time.sleep(3)
    ok = content_healthy()
    return ok is True


def recover():
    """Escalating recovery. Returns True once content is restored."""
    reload_tab()
    if verify_recovered(12):
        log("recovered via reload")
        return True

    kill_renderer()
    time.sleep(3)
    reload_tab()
    if verify_recovered(12):
        log("recovered via renderer-kill + reload")
        return True

    relaunch_chromium()
    if verify_recovered(20):
        log("recovered via full relaunch")
        return True

    log("CRITICAL: kiosk still unhealthy after full recovery escalation")
    return False


def main():
    log(f"kiosk-watchdog starting (poll={POLL_SECONDS}s, "
        f"content_min={CONTENT_MIN_BYTES}B, wayland={WENV['WAYLAND_DISPLAY']})")
    faults = 0
    last_daily_reload_day = None

    while True:
        try:
            now = time.localtime()
            # Proactive daily reload to avoid multi-day tab rot.
            if now.tm_hour == DAILY_RELOAD_HOUR and last_daily_reload_day != now.tm_yday:
                last_daily_reload_day = now.tm_yday
                log("proactive daily reload")
                reload_tab()
                time.sleep(POLL_SECONDS)
                continue

            state = get_state()
            if state != "active":
                # dim/off (black is legitimate) or controller unreachable -> don't judge.
                faults = 0
                time.sleep(POLL_SECONDS)
                continue

            healthy = content_healthy()
            if healthy is None:
                # grim hiccup — inconclusive, don't count.
                time.sleep(POLL_SECONDS)
                continue

            if healthy:
                if faults:
                    log("kiosk healthy again")
                faults = 0
            else:
                faults += 1
                log(f"kiosk looks black/crashed while active "
                    f"(fault {faults}/{FAULT_THRESHOLD})")
                if faults >= FAULT_THRESHOLD:
                    recover()
                    faults = 0
        except Exception as e:  # noqa: BLE001
            log(f"loop error: {e}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

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

Data-wedge detection (2026-07-07 / 2026-07-10)
----------------------------------------------
The renderer can also wedge with an intact-looking frame: the UI shell (or the
rest-state clock) keeps displaying but the page's JS/network layer is frozen, so
widgets stop updating and taps do nothing. The screenshot-size check is blind to
this (the frame is large), and when it happens on the clock face the state is
"dim" so the size check never even runs. So the kiosk page POSTs a liveness
heartbeat to the screen-controller every ~20s (ScreenOverlay in the app's root
layout), and the controller reports heartbeat_age_seconds. A stale heartbeat in
ANY state, twice in a row, means the tab's JS is dead. Plain Ctrl+R does not
clear a wedge (proven 2026-07-07), so wedge recovery goes straight to
kill-renderer + reload, then full relaunch.

Display-stall detection (2026-07-15..17)
----------------------------------------
Third variant: Chromium stops PRESENTING frames while the page's JS stays fully
alive — heartbeat fresh, touches register wakes, daily reloads run, but the
compositor keeps showing the last submitted frame (found frozen at "20:08 Wed
15 July" ~35h later). Both existing probes are blind: the frame is large and
the heartbeat never goes stale. But the clock face shows minutes in EVERY
state (active dashboard and dim clock), so the framebuffer must change every
minute. N consecutive identical grim hashes therefore mean the presentation
path is frozen. Skipped while the media overlay is up (paused video is
legitimately static). The renderer was only a day old when this first struck
(the 21-day-old GPU process was the suspect), so stall recovery goes straight
to a full Chromium relaunch (proven fix 2026-07-17).

Recovery escalates: reload -> kill renderer + reload -> full Chromium relaunch.
A once-daily proactive reload keeps the tab from rotting over multi-day uptimes.
"""

import hashlib
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
HEARTBEAT_STALE_SECONDS = 75   # page beats every ~20s; >75s = 3 missed beats
STALL_THRESHOLD = 3            # identical frames ~60s apart; 3 spans >=2 clock minutes
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


def get_screen():
    """Return the screen-controller status dict, or None if unreachable."""
    try:
        with urllib.request.urlopen(SCREEN_API, timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        return None


def wake():
    """Tell the screen-controller we have activity (POST)."""
    try:
        req = urllib.request.Request(SCREEN_API, method="POST", data=b"")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:  # noqa: BLE001
        pass


def screenshot_frame():
    """grim the output; return (png_size, md5_hex), or (-1, None) on failure."""
    try:
        if os.path.exists(SHOT):
            os.remove(SHOT)
    except OSError:
        pass
    rc, out = run(["grim", SHOT], timeout=15)
    if rc != 0 or not os.path.exists(SHOT):
        log(f"grim failed rc={rc} {out.strip()[:120]}")
        return -1, None
    with open(SHOT, "rb") as f:
        data = f.read()
    return len(data), hashlib.md5(data).hexdigest()


def screenshot_size():
    """grim the output and return the PNG byte size, or -1 on failure."""
    return screenshot_frame()[0]


def media_overlay_active():
    """True while a media session (Netflix/YouTube/NowTV) is on screen."""
    # [.] stops pgrep -f matching the shell that carries this very pattern.
    rc, _ = run("pgrep -f 'close-overlay[.]py'", timeout=5)
    return rc == 0


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


def heartbeat_fresh(wait_s):
    """Wait for the reloaded page to boot and beat, then re-read the age."""
    time.sleep(wait_s)
    screen = get_screen()
    if screen is None:
        return False
    age = screen.get("heartbeat_age_seconds")
    return age is not None and age < HEARTBEAT_STALE_SECONDS


def recover_wedge():
    """
    Recovery for a wedged renderer (frame intact, JS dead). Plain Ctrl+R does
    not clear this state, so start at kill-renderer + reload. Verified by the
    heartbeat resuming, since the screenshot looks healthy throughout.
    """
    kill_renderer()
    time.sleep(3)
    reload_tab()
    if heartbeat_fresh(35):
        log("recovered wedge via renderer-kill + reload")
        return True

    relaunch_chromium()
    if heartbeat_fresh(45):
        log("recovered wedge via full relaunch")
        return True

    log("CRITICAL: kiosk heartbeat still stale after full recovery escalation")
    return False


def recover_stall(stalled_md5):
    """
    Recovery for a frozen presentation path (frame stale, JS/heartbeat alive).
    Reload and renderer-kill are unproven against this; the fix proven
    2026-07-17 is a full relaunch, so go straight there. Verified by the
    framebuffer actually changing, since every other signal looks healthy.
    """
    log("recovery: display stalled -> full chromium relaunch")
    relaunch_chromium()
    time.sleep(30)
    _, md5 = screenshot_frame()
    if md5 is not None and md5 != stalled_md5:
        log("recovered stalled display via full relaunch")
        return True
    log("CRITICAL: display still stalled after full relaunch")
    return False


def main():
    log(f"kiosk-watchdog starting (poll={POLL_SECONDS}s, "
        f"content_min={CONTENT_MIN_BYTES}B, hb_stale={HEARTBEAT_STALE_SECONDS}s, "
        f"stall={STALL_THRESHOLD}x, wayland={WENV['WAYLAND_DISPLAY']})")
    faults = 0
    hb_faults = 0
    stalls = 0
    last_frame_md5 = None
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

            screen = get_screen()
            if screen is None:
                # Controller unreachable -> can't judge anything.
                faults = 0
                hb_faults = 0
                time.sleep(POLL_SECONDS)
                continue

            # --- Wedge check: stale heartbeat means the tab's JS is dead,
            # regardless of what the frame looks like or the screen state.
            hb_age = screen.get("heartbeat_age_seconds")
            if hb_age is not None and hb_age > HEARTBEAT_STALE_SECONDS:
                hb_faults += 1
                log(f"kiosk heartbeat stale ({hb_age}s, state={screen.get('state')}) "
                    f"(fault {hb_faults}/{FAULT_THRESHOLD})")
                if hb_faults >= FAULT_THRESHOLD:
                    recover_wedge()
                    hb_faults = 0
                    faults = 0
                time.sleep(POLL_SECONDS)
                continue
            if hb_faults:
                log("kiosk heartbeat fresh again")
            hb_faults = 0

            size, frame_md5 = screenshot_frame()
            if frame_md5 is None:
                # grim hiccup — inconclusive, don't count anything this cycle.
                time.sleep(POLL_SECONDS)
                continue

            # --- Display-stall check: the clock changes every minute in every
            # state, so identical consecutive frames mean chromium has stopped
            # presenting even though its JS (and heartbeat) may still be alive.
            if media_overlay_active():
                # Paused video is legitimately static — don't judge.
                stalls = 0
                last_frame_md5 = None
            elif frame_md5 == last_frame_md5:
                stalls += 1
                log(f"display frame unchanged ({stalls}/{STALL_THRESHOLD}, "
                    f"state={screen.get('state')})")
                if stalls >= STALL_THRESHOLD:
                    recover_stall(frame_md5)
                    stalls = 0
                    faults = 0
                    last_frame_md5 = None
                    time.sleep(POLL_SECONDS)
                    continue
            else:
                if stalls:
                    log("display frame advancing again")
                stalls = 0
                last_frame_md5 = frame_md5

            if screen.get("state") != "active":
                # dim/off -> a black frame is legitimate, don't judge content.
                faults = 0
                time.sleep(POLL_SECONDS)
                continue

            healthy = size >= CONTENT_MIN_BYTES
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

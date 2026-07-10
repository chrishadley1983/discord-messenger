# kiosk-watchdog

Auto-recovers the IHD dashboard Chromium kiosk when its renderer freezes or crashes —
either a black/blank screen that ignores touch, or a "data-wedge" where the frame
looks fine but the page's JS is dead (the Next.js server on :3000 stays healthy
throughout, so an HTTP health check can't see either fault).

## How it works

Two independent checks, polled from the screen-controller (`:5002`) every 60s:

**Black/crash check** (active state only — in `dim`/`off` a black frame is legitimate):
- Takes a `grim` screenshot and checks its byte size: healthy dashboard ~120 KB,
  black frame ~2.4 KB, "Aw, Snap!" crash ~18 KB. `< 40 KB` while active = fault.
- Two consecutive faults, then escalating recovery:
  1. `Ctrl+R` reload (`wtype`)
  2. kill the frozen renderer (`pkill -f 'chromium.*type=renderer'`) + reload
  3. full Chromium relaunch (the labwc autostart has no respawn loop)

**Heartbeat / data-wedge check** (any state — the 2026-07-07 and 2026-07-10 wedges
froze the widgets and the rest-state clock respectively, with a healthy-looking frame):
- The kiosk page (`ScreenOverlay` in the app's root layout) POSTs
  `/api/screen/heartbeat` → controller `POST /heartbeat` every 20s while its JS
  runs; the controller reports `heartbeat_age_seconds`.
- Age > 75s (3 missed beats) twice in a row = wedged. Plain Ctrl+R does not clear
  a wedge, so recovery starts at kill-renderer + reload (verified by the heartbeat
  resuming), then full relaunch.
- Caveat: any browser with the dashboard open (e.g. a laptop viewing :3000)
  also beats, which would mask a wedged kiosk while that tab stays open.

Also runs a once-daily proactive reload at 04:xx to prevent multi-day tab rot
(the original 2026-07-05 freeze was a ~9-day-old tab).

## Deploy (on the Pi)

```bash
# from repo: ihd/pi-services/kiosk-watchdog/
scp watchdog.py chrishadley1983@192.168.0.110:~/kiosk-watchdog/watchdog.py
ssh chrishadley1983@192.168.0.110 \
  "pm2 start ~/kiosk-watchdog/watchdog.py --name kiosk-watchdog --interpreter python3 && pm2 save"
```

Needs the graphical session's Wayland socket; the script sets
`XDG_RUNTIME_DIR=/run/user/1000` and `WAYLAND_DISPLAY=wayland-0` itself.

## Logs

```bash
pm2 logs kiosk-watchdog --lines 50
```

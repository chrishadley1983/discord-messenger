# kiosk-watchdog

Auto-recovers the IHD dashboard Chromium kiosk when its renderer freezes or crashes,
leaving a black/blank screen that ignores touch (the Next.js server on :3000 stays
healthy, so only a framebuffer check catches it).

## How it works

- Polls the screen-controller (`:5002`) every 60s. Only judges health when
  `state == "active"` (when the dashboard must be visible). In `dim`/`off` a black
  frame is legitimate, so it does nothing.
- Takes a `grim` screenshot and checks its byte size: healthy dashboard ~120 KB,
  black frame ~2.4 KB, "Aw, Snap!" crash ~18 KB. `< 40 KB` while active = fault.
- Requires two consecutive faults, then escalates recovery:
  1. `Ctrl+R` reload (`wtype`)
  2. kill the frozen renderer (`pkill -f 'chromium.*type=renderer'`) + reload
  3. full Chromium relaunch (the labwc autostart has no respawn loop)
- Runs a once-daily proactive reload at 04:xx to prevent multi-day tab rot
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

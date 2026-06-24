# IHD (In-Home Display) — folded into discord-messenger

This directory is the **In-Home Display** project, folded into the
discord-messenger repo on 2026-06-24 so it is version-controlled and backed up
alongside the rest of the home stack (it previously lived only in a separate
`claude-projects/ihd` repo, and parts of it lived *only on the Pi*).

## What it is

A Next.js kiosk dashboard (`ihd-app/`) running in Chromium kiosk mode on a
**Raspberry Pi 5** at `192.168.0.110:3000` (a Waveshare 13.3" touchscreen in the
kitchen). Pi-side Python helpers live in `pi-services/` and `health-logger/`.
Deploy is `deploy.sh` (tar → scp to `chrishadley1983@192.168.0.110` → `npm install`
→ `next build` → `pm2 restart ihd`).

## What was copied vs excluded

- **Copied:** all source (`ihd-app/src`, `public`), configs, `pi-services/`,
  `health-logger/`, `kiosk-touch-ext/`, docs, `deploy.sh`.
- **Excluded** (regenerable / not code): `node_modules/`, `.next/`, `.git/`,
  screenshots, the `ihd-deploy.tar` build artifact.

## ⚠️ Gaps & risks (see the integration report)

1. **On-Pi-only services — NOW RETRIEVED (2026-06-24).** Pulled off the Pi via
   the cloud-init SSH login (key-based, user `chrishadley1983`) into
   `pi-services/` — see `pi-services/README.md`:
   - `pi-services/zigbee-api/server.py` — the `:5001` **zigbee2mqtt → HTTP bridge**
     that serves live sensor data (`/`) **and ~30 days of history** (`/history`,
     SQLite `~/.data/sensors.db`). Feeds the temperature trend.
   - `pi-services/screen-control/controller.py` — the `:5002` screen/idle controller.
   - `pi-services/media-overlay/` and `pi-services/network-watchdog.sh` (cron WiFi watchdog).
   The in-repo `pi-services/sensor/main.py` is a *different*, history-less BME280
   I2C sensor API on `:5000`. Run mechanism (pm2 + cron) is documented in the README.
2. **Hardcoded secrets in source.** `ihd-app/src/app/api/hb/route.ts` contains a
   Supabase **service_role** JWT plus `HB_INTERNAL_KEY`; `energy/route.ts` and
   `kids/route.ts` carry Supabase anon JWTs. These were committed in the original
   ihd repo. They should be moved to env vars / `.env.sops` before this is
   committed here — do not `git add` these files until that's done, or the
   pre-commit secret hook will (rightly) block them.

## How Peter uses it

Peter does **not** import this source — he reaches the *running* IHD app and
bridge over HTTP. The integration lives in discord-messenger:
- `domains/ihd/service.py` — proxy helpers (base `http://192.168.0.110:3000`).
- `hadley_api/peter_routes/ihd.py` — `/ihd/*` endpoints (plug, pocket-money,
  pets, jokes, media, screen, kids).
- `hadley_api/peter_routes/home_sensors.py` — `/home/sensors` + `/home/sensors/history`
  + `/home/sensors/trend` (bridge `:5001`).
- Skills: `home-sensors` (+trends), `home-control`, `pocket-money`, `kids-pets`,
  `dad-jokes`.

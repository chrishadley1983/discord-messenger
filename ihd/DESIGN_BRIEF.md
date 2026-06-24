# In-Home Dashboard (IHD) — Design Brief
*Started: 10 March 2026 | Status: Planning / Mockup complete*

---

## Hardware

- **Device:** Raspberry Pi 5 (4GB)
- **Display:** Waveshare 13.3" 1920×1080 touchscreen
- **Pi hostname:** `dashboard` | **IP:** `192.168.0.110`
- **Sensors:** BME280 (temp/humidity/pressure), BH1750 (light/auto-brightness), HC-SR501 PIR (motion/screen wake)
- **Zigbee:** Sonoff ZBDongle-E + Sonoff S60ZBTPG smart plug (via Zigbee2MQTT on port 8080)
- Full hardware spec: see `dashboard-progress.md`

---

## Project Location

```
C:\Users\Chris Hadley\claude-projects\ihd
```

**Stack:** Next.js 14 (App Router), TypeScript, Tailwind CSS  
**Dev on:** Windows  
**Deploy to:** Raspberry Pi 5 via git pull + pm2  
**Chromium:** Kiosk mode on boot

---

## Audience & Goals

- **Primary audience:** Whole family (Chris, Abby, Max, Emmie)
- **Primary use case:** Family/home hub — calendar, meals, sensors
- **Interaction model:** Fully interactive touch UI with navigation
- **Theme:** Light mode — warm parchment palette (see mockup)

---

## Design Language

- **Font:** Fraunces (serif, display) + Figtree (sans, body)
- **Background:** `#f5f2eb` (warm parchment)
- **Cards:** `#ffffff` with `#e0d9cc` borders, subtle drop shadow
- **Accent:** `#c47f0a` (amber gold)
- **Status colours:** Green `#2a9e5c` · Blue `#2e78d0` · Rose `#d44868` · Purple `#7c52c8`
- **Person colours:** Chris `#c47f0a` · Abby `#c8304c` · Max `#2060b8` · Emmie `#7040b8` · Family `#1e8a50`

### Header (locked — keep as-is)
- Live clock (Fraunces serif, large) with blinking colon
- Day + full date (centre)
- Weather widget — icon, temperature, location (Tonbridge), feels-like, rain % (right)

---

## Page Structure

Five pages via bottom navigation:

| Icon | Page | Purpose |
|------|------|---------|
| 🏠 | Home | Primary family dashboard |
| 📅 | Calendar | 7-day week view |
| 🍽 | Meals | Weekly meal plan + tonight |
| 💡 | Control | Sensors + smart plug + Zigbee |
| 📊 | Chris | Personal — tasks, Hadley, running |

---

## Home Page — 6 Widgets (v1 priority)

This is the first page to build properly. Layout: header + 6-widget grid.

### 1. Events — Google Calendar
- Today's events, time + title + person pill
- Past events faded/struck through
- **Data source:** Google Calendar API (service account — TBC setup)
- **Calendars:** TBC — one shared family cal or separate per person (to confirm)
- **Polling:** 10-minute intervals

### 2. Peter Notifications
- Key messages/alerts pushed by Peterbot (school run reminders, delivery alerts, etc.)
- **Data source:** Peterbot API — endpoint TBC (see Peterbot codebase)
- **Architecture note:** Need to review Peterbot API routes to confirm available endpoints
- Read-only display; maybe last 3–5 notifications

### 3. Today's Food
- Tonight's dinner + brief prep note
- **Data source:** TBC — FamilyFuel Supabase or alternative (to confirm)

### 4. Next Trip
- Countdown days + destination + key alert (e.g. Shinkansen not booked)
- **Data source:** Hardcoded Japan data for v1 (Apr 3–19, Tokyo/Osaka/Kyoto)
- Future: drive from a `trips` table

### 5. Peter Interaction
- Chat window — send message to Peter, see response
- **Data source:** Peterbot API (REST, not Discord webhook)
- **Architecture note:** Need Peterbot API base URL + auth method + available endpoints
- Full conversation UI: input box, send button, scrollable message history

### 6. Learning Schedule
- This week's spelling + 11+ schedule for the kids
- Links/content for the week
- **Children:** Max and/or Emmie (to confirm which)
- **Data source:** TBC — Google Docs/Sheets, URLs, or manual (to confirm)

---

## Other Pages (post-home)

### Calendar
- 7-column week view (Mon–Sun)
- Events colour-coded by person
- Today's column highlighted

### Meals
- Full week grid + tonight's recipe detail
- Completed meals faded

### Control
- Smart plug toggle (Sonoff S60ZBTPG via Zigbee2MQTT MQTT)
- BME280 sensor readings (temp/humidity/pressure)
- BH1750 light level + brightness bar
- PIR status (shown as pending until wired)
- Zigbee device list with planned devices greyed

### Chris (personal page)
- Peter task list (tickable, urgent flagged)
- Hadley Bricks today's orders/revenue by platform
- Running week grid (distances + session types)
- Peterbot build phase progress

---

## Architecture

```
Next.js App (port 3000)
├── /app
│   ├── page.tsx              ← Home page (priority)
│   ├── calendar/page.tsx
│   ├── meals/page.tsx
│   ├── control/page.tsx
│   └── chris/page.tsx
├── /components
│   ├── Header.tsx            ← Clock + weather (locked design)
│   ├── BottomNav.tsx
│   └── home/
│       ├── EventsWidget.tsx
│       ├── NotificationsWidget.tsx
│       ├── FoodWidget.tsx
│       ├── TripWidget.tsx
│       ├── PeterWidget.tsx
│       └── LearningWidget.tsx
└── /app/api
    ├── calendar/route.ts     ← Google Calendar proxy
    ├── peter/route.ts        ← Peterbot API proxy
    ├── sensor/route.ts       ← BME280 data from Pi Python endpoint
    └── weather/route.ts      ← Open-Meteo (free, no key needed)
```

### Sensor API (Pi side)
- Small FastAPI or Flask service on the Pi reading BME280 via smbus2
- Exposes `GET /sensor` → `{ temp, humidity, pressure }`
- Next.js polls this from `/app/api/sensor/route.ts`

### Weather
- **Provider:** Open-Meteo (free, no API key)
- **Location:** Tonbridge, Kent (51.1959° N, 0.2729° E)
- Fetch: current temp, weather code, feels-like, precipitation probability

### Peterbot API
- **Status:** Base URL + auth + endpoints TBC — review Peterbot codebase in Claude Code
- Used for: notifications widget + Peter interaction widget

---

## Outstanding Questions (resolve in Claude Code)

1. **Peterbot API** — base URL, auth method, available endpoints (read codebase)
2. **Google Calendar** — service account setup needed? Which calendar IDs?
3. **Today's Food** — FamilyFuel Supabase table name/schema, or alternative source?
4. **Learning Schedule** — Max, Emmie, or both? Data source (Docs/Sheets/URLs)?
5. **Sensor endpoint** — build Python FastAPI service on Pi (BME280 script exists as `test_bme280.py`)

---

## Current Mockup

`mockup-home.jsx` — full 5-page interactive React mockup with light mode. Use for visual reference only; not production code.

---

## Next Steps

1. `npx create-next-app@latest ihd --typescript --tailwind --app`
2. Install deps: `fraunces` + `figtree` Google Fonts, `@supabase/supabase-js`, `date-fns`
3. Build `Header.tsx` first (locked design, clock + weather via Open-Meteo)
4. Review Peterbot codebase → document API
5. Build home page widgets one by one (order: Events → Food → Trip → Notifications → Learning → Peter)

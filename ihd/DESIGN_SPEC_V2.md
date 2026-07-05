# IHD Redesign V2 — "Sunburst Control Panel"

**Target**: 1024×768 fixed, touch-only, Raspberry Pi 5 + Chromium kiosk, viewed 1–5ft, used by adults AND young kids (Emmie, Max).
**Direction**: Bold + bright reboot. Saturated colour-blocked sections, giant confident type, sticker/comic card language — held together by a rigorous grid, one ink colour, and disciplined tokens. Fun face, professional bones.

---

## 1. Design tokens (globals.css `:root`)

```css
--paper:   #FFFDF6;   /* app background — warm white */
--ink:     #221A3A;   /* ALL text + borders — deep plum-ink, never pure black */
--ink-60:  rgba(34,26,58,.6);
--ink-30:  rgba(34,26,58,.3);
--ink-08:  rgba(34,26,58,.08);
--surface: #FFFFFF;

/* Section signature hues (bold, saturated) */
--home:     #FFB703;  /* marigold  — ink text on it */
--calendar: #1B9AAA;  /* cerulean  — white text */
--meals:    #FB5607;  /* tangerine — white text */
--kids:     #8338EC;  /* violet    — white text */
--media:    #F72585;  /* magenta   — white text */
--control:  #06D6A0;  /* mint      — ink text */
--hb:       #D01012;  /* LEGO red  — white text */

/* Status */
--good: #06D6A0;  --warn: #FFB703;  --bad: #EF4444;

/* Person colours (KEEP — family knows them) */
--chris: #c47f0a; --abby: #c8304c; --max: #2060b8; --emmie: #7040b8; --family: #1e8a50;

/* Screensaver */
--night-bg: #14102A;
```

Tint helper: each section colour also gets a `--<name>-tint` at 10% opacity over paper for card washes.

## 2. Typography

- **Display**: `Bricolage Grotesque` (next/font/google, weights 300–800). Headers, big numbers, clock, nav labels.
- **Body**: `Hanken Grotesk` (400/600/700). Everything else.
- Floors: body ≥16px, secondary labels ≥13px, key values 24–44px. html base stays 18px.
- Numerals in data contexts: `font-variant-numeric: tabular-nums`.

## 3. Card & shape language ("sticker sheet")

- Cards: `--surface`, border **2px solid var(--ink)**, radius **20px**, hard offset shadow `4px 4px 0 var(--ink-08)` (crisp, not blurry).
- Section header chip on every card: small pill, solid section colour, 700 display font, 13–14px, uppercase tracking +0.05em. Text ink on marigold/mint, white elsewhere.
- Decorative permission: ±1.5° rotation on badges/stickers ONLY (never on data), confetti-dot accents in section tint.
- Press state (everything tappable): `active: scale(.96)` + shadow collapses to `2px 2px 0`.

## 4. Motion (Pi-friendly: transform/opacity ONLY)

- Page mount: stagger-in — each card `opacity 0→1, translateY(12px)→0`, 300ms ease-out, 60ms delay steps.
- NO infinite animations except: live-energy pulse dot, pet sprites, clock colon (subtle 50% opacity step).
- Popup/takeover enter: scale .97→1 + fade, 200ms.

## 5. Shell

- **Header** (slim, shrink-0): time HH:MM (Bricolage 600 ~44px) + date; centre title "Hadley HQ" small; right = weather chip (icon, temp, feels, rain) → opens **centred** weather popup (Modal — fixes current right-edge overflow).
- **BottomNav**: 76px tall, 7 chunky pills. Active = solid section colour fill + 2px ink border + offset shadow + ink/white label; inactive = ink-60 icon+label on paper. Whole pill is the target (~140×64).
- **z-ladder (hard rule)**: chrome 100 · popup 200 · takeover 300 · screensaver 9999.

## 6. Interaction system — the two widget modes

### `<Modal>` (quick glance/act)  — components/ui/Modal.tsx
Centred; max-w 720px; max-h 85vh; backdrop `rgba(20,16,42,.55)` tap-closes; **X button 56×56** top-right; Escape closes. Content scrolls inside.
Used by: EventPopup, weather forecast, Recipe quick view? (no → takeover), TransactionPopup, AddMoneyPopup, HomeworkPopup, dad-joke.

### `<Takeover>` (rich/immersive full-screen) — components/ui/Takeover.tsx
`fixed inset-0 z-300`, paper bg. Fixed header bar (72px): **back button 72×72** top-left (◀ + label, section colour), title, optional actions. Body = the experience, fills rest.
Used by: **Pets playground** (iframe fills body — bigger than today's 70vw overlay), Kids practice/spelling iframes, Trip browser, SensorHistory charts, Recipe detail, PocketMoneyGrid.

### Single-modal rule
`ModalManager` React context in DashboardShell: registering a popup/takeover closes any open one. Never two stacked backdrops.

## 7. Edge-safety rules (the "never lose the screen" contract)

1. Nothing positioned by user input or randomness may exceed 5–95% of its container (pets messes/sparkles already comply; keep).
2. Pets game runs INSIDE a Takeover (fixed 72px back button always reachable) — no more floating 70vw iframe with corner X.
3. No trigger-anchored popovers — every overlay is a centred Modal or a Takeover.
4. Touch targets: ≥56px kids-facing screens (Kids, Pets, Media), ≥44px absolute floor elsewhere.
5. Scroll areas keep the 20px scrollbar + 24px bottom padding so last items clear the nav.
6. Auto-rotating content (TripWidget featured venue) pauses 60s on any pointerdown inside the card (fixes tap-vs-rotate race).
7. Fullscreen iframes (practice, pets) must sit inside Takeover body — never own fixed positioning.
8. ScreenOverlay (screensaver) stays z-9999, whole surface = wake target.

## 8. Per-screen specs

### Home `/` (marigold)
Keep current 3-col grid structure (works well). Restyle all widgets to card language; section chips in respective colours (events=calendar hue, food=meals, kids=kids, trip=media? no—trip keeps its own neutral ink chip w/ 🇯🇵; energy=control mint; sensors=cerulean; hb=LEGO red; pets=kids violet).
**FIX**: HadleyWidget currently HARDCODED (Orders 7 / £142.50) → fetch `/api/hb` (orders total + revenue this month), 5-min refresh, link → /chris on tap.
PetWidget tap → Pets Takeover. SensorWidget tap → SensorHistory Takeover.

### Calendar `/calendar` (cerulean)
Keep 3-column (Today large / Tomorrow / This Week). Today column gets cerulean-tint wash + bigger event cards (56px min row). Person-colour pills stay. EventPopup → Modal.

### Meals `/meals` (tangerine)
Keep day-nav + meal cards. Day selector pills ≥56px. RecipePopup → **Takeover** (ingredients left / steps right at 1024px). Source tags become sticker badges.

### Kids `/kids` (violet)
Balance cards: giant Bricolage balance (56px), child-colour headers (emmie/max person colours), buttons ≥64px.
PocketMoneyGrid → **Takeover** (4×7 grid, cells ≥64×64, day columns labelled, running total footer, big SAVE).
Dad joke card: sticker style, reveal animation kept. All current sub-44px targets (practice items etc.) → ≥56px rows.

### Media `/media` (magenta)
3 giant brand tiles (Netflix/YouTube/Now TV) ~280×200, brand-colour blocks with white logos, magenta section chip, press feedback, launching state (spinner + "Launching…"), Close-app button distinct (ink outline pill). Status of currently-running app shown if API provides it.

### Control `/control` (mint) — REAL SCREEN (currently stub)
2×2 grid of control cards:
1. **Screen** — current state (active/dim), idle seconds, "Rest now" (POST /api/screen → controller has no such endpoint? use wake only) → buttons: "Wake" (POST /api/screen/wake). Show state badge.
2. **Kitchen plug** — /api/plug GET state + toggle if reachable; if API offline show "Unreachable" badge gracefully (known: Z2M plug API may be offline).
3. **Media** — currently running app + Close button (POST /api/media {action:'close'}).
4. **Coming soon** — lights etc., honest sticker "SOON".

### HB `/chris` (LEGO red)
Keep 5-card layout (Orders / Targets / Sync / P&L / Quick Actions). LEGO-red chips; big dispatch number in Bricolage 44px; progress bars 14px tall with rounded ends; LEGO stud row as decorative footer strip on the P&L card (CSS circles, subtle). Quick Action buttons ≥64px.

### Screensaver clock (ScreenOverlay) — TIME-DOMINANT + date + weather
Background `--night-bg` (#14102A). NO pure-black; NOT paper (glare).
- **Time**: Bricolage 300, ~34vh tall (~260px), colour = marigold with subtle luminous gradient (marigold→tangerine), tabular. Blinking colon at 50% opacity steps.
- **Date**: below, 28px, white 60%, letterspaced uppercase.
- **Weather row**: pill under date — icon + current temp (28px, white 90%) + "H 21° L 12°" + rain % if >10%. Fetch /api/weather every 10 min while overlay visible.
- Whole screen = wake target. `dim` state shows this; `off` never happens (controller change already live).

## 9. Implementation architecture

- I author: `globals.css` (tokens/keyframes), `layout.tsx` (fonts), `ui/Modal.tsx`, `ui/Takeover.tsx`, `ui/Card.tsx` + `ui/SectionChip.tsx`, `ModalManager`, `Header.tsx`, `BottomNav.tsx`, `ScreenOverlay.tsx`.
- Screen bodies delegated per-screen (agents) consuming this spec + shared components. Agents may NOT edit shared files.
- No new deps (Tailwind 4 + next/font only). No external requests at runtime beyond existing APIs.

## 10. Acceptance criteria (challenge workflow tests these)

1. Every screen renders at exactly 1024×768 with no horizontal scroll and no clipped content.
2. All interactive elements ≥44px (≥56px on Kids/Media/Pets); verified by DOM audit.
3. Only one overlay can be open at a time; every overlay closable via ≥56px control AND backdrop/back.
4. Pets game: back button visible and functional at all times; no interactive element within 24px of viewport edge.
5. Clock screensaver shows time (dominant), date, live weather; readable from 3m (time ≥200px tall).
6. HadleyWidget shows live data (not hardcoded).
7. No purple-gradient-on-white, no Inter/Roboto/system fonts, no default Tailwind blue — passes "doesn't look AI-generated" review.
8. All animations transform/opacity only; no layout thrash on 20s energy polls.

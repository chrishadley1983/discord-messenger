# IHD → Peter Integration — Functionality Report

**Date:** 2026-06-24
**Scope:** Fold the IHD (in-home display) / Pi project into the discord-messenger
repo and extend Peter to use all of it. Validated end-to-end (PASS).

---

## TL;DR

Peter previously had **no access** to anything on the kitchen dashboard Pi beyond
the live temperature reading I wired up earlier today. He now has the **full IHD
surface**: temperature *trends*, the smart plug, the kids' pocket money, the
Tamagotchi pets, homework/spellings, dad jokes, and the ability to put streaming
on the kitchen screen. The IHD source is also now **backed up inside the main
repo** (it previously lived in a separate repo, with key pieces only on the Pi).

An adversarial end-to-end workflow verified the whole thing: **PASS** — 4/4
build dimensions and 3/3 independent skeptic checks (trend-math correctness,
pocket-money fidelity + write-protection, fold-in honesty), all at high confidence.

---

## 1. What Peter can now do

| Ask Peter… | Backed by |
|------------|-----------|
| "Is the bedroom warmer than yesterday?" / "What was the overnight low?" / "Has humidity climbed this week?" | `/home/sensors/trend`, `/home/sensors/history` (bridge's ~30-day store) |
| "How much pocket money does Max have?" / "Add £2 to Emmie for tidying her room" | `/ihd/pocket-money` (live: Emmie **£43.24**, Max **£46.45**) |
| "What did the kids earn this week?" | `/ihd/pocket-money/calculate` (grid → totals) |
| "Turn the plug on/off" / "Is the plug on?" | `/ihd/plug` |
| "Put Netflix on the kitchen screen" / "Turn the telly off" | `/ihd/media` (Netflix/YouTube/NowTV) |
| "How are the kids' pets?" / "Do they need feeding?" | `/ihd/pets` |
| "What are Max's spellings this week?" | `/ihd/kids` (spellings/homework/11PlusMate) |
| "Tell the kids a joke" / "Put a joke on the screen" | `/ihd/jokes` (the "Peter says…" card) |
| "Wake the kitchen screen" | `/ihd/screen/wake` |

All **read** endpoints are open; all **mutating** endpoints (plug on/off, money
add, media, joke add, screen wake) require the `x-api-key` header — verified
auth-gated (401 without it, no side effects).

---

## 2. What was folded in

- The entire IHD project source copied to **`ihd/`** in the repo — **94 files**
  (Next.js app, Pi services, health-logger, kiosk extension, docs).
- **Excluded** (regenerable/not code): `node_modules/`, `.next/`, `.git/`,
  screenshots, build tarball.
- **`ihd/PROVENANCE.md`** documents provenance, what was excluded, and the gaps below.

---

## 3. How Peter reaches it (architecture)

Peter does **not** import the IHD source — he reaches the *running* IHD app and
sensor bridge over HTTP, so there's one source of truth and no duplicated logic.

- `domains/ihd/service.py` — proxy over the IHD app (`192.168.0.110:3000`).
- `hadley_api/peter_routes/ihd.py` — the `/ihd/*` endpoints.
- `hadley_api/peter_routes/home_sensors.py` + `domains/home_sensors/service.py`
  — `/home/sensors/history` + `/trend` (bridge `:5001`).
- Skills (WSL-symlinked, live immediately): **home-control**, **pocket-money**,
  **kids-pets**, **dad-jokes**, and **home-sensors** (now with trends).

---

## 4. Validation (E2E workflow: PASS)

`.claude/workflows/verify-ihd-integration-e2e.js` — re-runnable anytime.

| Dimension | Result |
|-----------|--------|
| Fold-in integrity (files present, node_modules excluded, provenance) | PASS |
| Endpoints live + correct shape + POST auth-gating | PASS |
| Skills + manifest wiring (no regression to weather/pocket-money-weekly) | PASS |
| Code wiring + compile | PASS |
| **Adversarial: trend math** | Stood — recompute matched endpoint exactly (min 25.2 / max 30.1 / avg 27.1, 75 samples) |
| **Adversarial: pocket-money fidelity + write-protection** | Stood — proxy byte-identical to IHD app; unauthenticated POST → 401, balance unchanged |
| **Adversarial: fold-in / secrets honesty** | Stood — exclusions confirmed, secrets warning accurate |

---

## 5. Caveats & recommended follow-ups

1. **Smart plug reads "offline".** The route is correct and returns 200, but its
   upstream — Zigbee2MQTT's `/api/devices` on `192.168.0.110:8080` — isn't
   returning device JSON right now (the Z2M frontend is up on `:8080`, but the
   REST device list isn't responding). Worth checking the Z2M REST API config on
   the Pi; the plug control will work once that's back.
2. **Hardcoded secrets in the folded code.** `ihd-app/src/app/api/hb/route.ts`
   has a Supabase **service_role** JWT + `HB_INTERNAL_KEY`; `energy/route.ts` and
   `kids/route.ts` carry anon keys. These came across as-is. **Do not `git add`
   them until they're moved to env vars / `.env.sops`** — the pre-commit secret
   hook will (rightly) block them. Recommend a small follow-up to externalise.
3. **On-Pi-only services aren't backed up.** The `:5001` zigbee→HTTP bridge (the
   one with `/history` that feeds trends) and the `:5002` screen controller exist
   only on the Pi. Recommend `scp`-ing them off (cloud-init SSH, user
   `chrishadley1983`) into `ihd/pi-services/` so they're version-controlled.
4. **Everything is uncommitted** on `feat/reset-cut-dashboard-redesign`. Happy to
   commit on a dedicated branch once the secrets in (2) are externalised.

"""Proxy layer over the running IHD (in-home display) app on the Pi.

The IHD Next.js app at 192.168.0.110:3000 already encapsulates the logic for
the smart plug (Zigbee2MQTT), the kids' pocket money + dad jokes (.data/*.json
on the Pi), the Tamagotchi pets, media/TV launching, the screen controller and
the homework/spellings dashboard. Rather than re-implement each upstream, Peter
reaches these by proxying the IHD app's own /api/* routes.

Sensor temperature/humidity (live + history + trend) is handled separately in
``domains.home_sensors`` (the zigbee bridge on :5001). The IHD project source is
folded into the repo at ``ihd/`` (see ihd/PROVENANCE.md).
"""

from __future__ import annotations

import os

import httpx

IHD_APP = os.environ.get("IHD_APP_URL", "http://192.168.0.110:3000")
TIMEOUT = 8


def _get(path: str, params: dict | None = None) -> dict:
    resp = httpx.get(f"{IHD_APP}{path}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, payload: dict) -> dict:
    resp = httpx.post(f"{IHD_APP}{path}", json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# --- Smart plug (Sonoff S60ZBTPG via Zigbee2MQTT) ---
def plug_status() -> dict:
    return _get("/api/plug")


def plug_set(on: bool) -> dict:
    return _post("/api/plug", {"state": "ON" if on else "OFF"})


# --- Pocket money (.data/pocket-money.json on the Pi; amounts in PENCE) ---
def pocket_money_summary() -> dict:
    return _get("/api/kids/pocket-money/summary")


def pocket_money_full() -> dict:
    return _get("/api/kids/pocket-money")


def pocket_money_add(child: str, amount_pence: int, description: str = "",
                     category: str = "pocket_money") -> dict:
    return _post("/api/kids/pocket-money", {
        "child": child,
        "amount": amount_pence,
        "description": description,
        "category": category,
        "source": "peter",
    })


def pocket_money_grid(week: str | None = None) -> dict:
    return _get("/api/kids/pocket-money/grid", {"week": week} if week else None)


def pocket_money_calculate(week: str | None = None) -> dict:
    return _get("/api/kids/pocket-money/calculate", {"week": week} if week else None)


# --- Dad jokes (.data/dad-jokes.json — the "Peter says..." card) ---
def jokes() -> dict:
    return _get("/api/kids/jokes")


def jokes_add(text: str) -> dict:
    return _post("/api/kids/jokes", {"text": text})


# --- Tamagotchi pets (max + emmie) ---
def pets() -> dict:
    return _get("/api/pets")


# --- Kids homework / spellings / 11PlusMate summary ---
def kids_summary() -> dict:
    return _get("/api/kids", {"action": "summary"})


# --- Media / TV (launches Chromium kiosk on the Pi: netflix|youtube|nowtv) ---
def media(action: str, app: str | None = None) -> dict:
    payload: dict = {"action": action}
    if app:
        payload["app"] = app
    return _post("/api/media", payload)


# --- Screen / display controller ---
def screen_status() -> dict:
    return _get("/api/screen")


def screen_wake() -> dict:
    return _post("/api/screen/wake", {})

"""Live home environment sensors (Zigbee2MQTT bridge on the dashboard Pi).

GET /home/sensors — per-room temperature, humidity, occupancy, illuminance,
battery and link quality from the zigbee2mqtt HTTP bridge at
192.168.0.110:5001 (the same Pi that serves the pocket-money IHD dashboard).

Read-only. Reshaping + the bridge URL live in domains.home_sensors.service,
which also runs the reachability/low-battery watchdog registered in bot.py.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from domains.home_sensors import service

router = APIRouter(prefix="/home", tags=["home"])


@router.get("/sensors")
async def home_sensors():
    """Live indoor temperature/humidity/occupancy per room."""
    try:
        return await asyncio.to_thread(service.get_sensors)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"home sensors unavailable: {e}")


@router.get("/sensors/history")
async def home_sensors_history(room: str, hours: int = 24, kind: str = "readings"):
    """Raw time-series for one room/device. kind=readings (temp/humidity) | motion."""
    try:
        return await asyncio.to_thread(service.get_history, room, hours, kind)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"sensor history unavailable: {e}")


@router.get("/sensors/trend")
async def home_sensors_trend(days: int = 7):
    """Per-room daily min/max/avg temperature + humidity, with vs-prior-day delta."""
    try:
        return await asyncio.to_thread(service.get_trend, days)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"sensor trend unavailable: {e}")

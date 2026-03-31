"""Flight price monitoring API endpoints.

Endpoints:
    GET  /flights/routes         — list monitored routes
    POST /flights/routes         — add a new route
    DEL  /flights/routes/{id}    — deactivate a route
    GET  /flights/prices         — get cheapest prices found
    GET  /flights/history        — price history for a route+date
    GET  /flights/deals          — current deal alerts
    GET  /flights/summary        — monitoring summary stats
    POST /flights/check-now      — trigger an on-demand price scan
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from hadley_api.auth import require_auth
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/flights", tags=["flights"])


class RouteCreate(BaseModel):
    from_airport: str = "LHR"
    to_airport: str = "HND"
    label: str = "London to Tokyo"
    passengers: int = 2
    cabin: int = 1
    stops: int = 1


class CheckNowRequest(BaseModel):
    outbound: Optional[str] = None
    return_date: Optional[str] = None


def _get_monitor():
    from services.flight_prices import FlightPriceMonitor
    return FlightPriceMonitor()


# --- Read endpoints (no auth needed — LAN only) ---

@router.get("/routes")
async def list_routes():
    """List all monitored flight routes."""
    monitor = _get_monitor()
    return {"routes": monitor.get_routes()}


@router.get("/prices")
async def get_prices(
    route_id: Optional[int] = Query(None),
    days_back: int = Query(30),
    limit: int = Query(10),
):
    """Get cheapest prices found recently."""
    monitor = _get_monitor()
    cheapest = monitor.get_cheapest(route_id=route_id, days_back=days_back, limit=limit)
    return {"prices": cheapest}


@router.get("/history")
async def get_history(
    route_id: int = Query(...),
    outbound_date: str = Query(...),
):
    """Get price history for a specific route and departure date."""
    monitor = _get_monitor()
    trend = monitor.get_price_trend(route_id, outbound_date)
    return {"history": trend, "route_id": route_id, "outbound_date": outbound_date}


@router.get("/deals")
async def get_deals(route_id: Optional[int] = Query(None)):
    """Get current deal alerts (prices significantly below baseline)."""
    monitor = _get_monitor()
    deals = monitor.detect_deals(route_id=route_id)
    return {"deals": deals, "count": len(deals)}


@router.get("/summary")
async def get_summary(days_back: int = Query(7)):
    """Get monitoring summary stats."""
    monitor = _get_monitor()
    return monitor.get_summary(days_back=days_back)


# --- Write endpoints (auth required) ---

@router.post("/routes", dependencies=[Depends(require_auth)])
async def add_route(route: RouteCreate):
    """Add a new route to monitor."""
    monitor = _get_monitor()
    route_id = monitor.add_route(
        from_airport=route.from_airport,
        to_airport=route.to_airport,
        label=route.label,
        passengers=route.passengers,
        cabin=route.cabin,
        stops=route.stops,
    )
    return {"status": "added", "route_id": route_id}


@router.delete("/routes/{route_id}", dependencies=[Depends(require_auth)])
async def remove_route(route_id: int):
    """Deactivate a monitored route."""
    monitor = _get_monitor()
    monitor.remove_route(route_id)
    return {"status": "deactivated", "route_id": route_id}


@router.post("/check-now", dependencies=[Depends(require_auth)])
async def check_now(req: CheckNowRequest = CheckNowRequest()):
    """Trigger an on-demand price scan.

    If outbound and return_date are provided, checks that specific date pair.
    Otherwise, scans the next 3 weekend departures.
    """
    import asyncio
    monitor = _get_monitor()

    if not monitor.api_key:
        raise HTTPException(503, "SERPAPI_KEY not configured")

    if req.outbound and req.return_date:
        results = await monitor.check_all_routes(date_pairs=[(req.outbound, req.return_date)])
    else:
        from services.flight_prices import generate_date_pairs
        pairs = generate_date_pairs("weekends", window_days=90, trip_lengths=[10, 14])
        # Take first 3 unique departure dates
        seen = set()
        sample = []
        for out, ret in pairs:
            if out not in seen and len(seen) < 3:
                seen.add(out)
            if out in seen:
                sample.append((out, ret))
        results = await monitor.check_all_routes(date_pairs=sample)

    # Flatten for response
    summary = {}
    for label, data in results.items():
        summary[label] = [
            {
                "outbound": r["outbound"],
                "return": r["return"],
                "price_pp": r["cheapest"]["price_pp"],
                "price_total": r["cheapest"]["price_total"],
                "airline": r["cheapest"]["airline"],
            }
            for r in data["results"]
        ]

    return {"status": "completed", "results": summary}


class MonthScanRequest(BaseModel):
    month: int
    year: Optional[int] = None
    trip_length: int = 14
    weekends_only: bool = False


@router.post("/scan-month", dependencies=[Depends(require_auth)])
async def scan_month(req: MonthScanRequest):
    """Scan an entire month to find the cheapest departure dates.

    Example: POST /flights/scan-month {"month": 9, "trip_length": 14}
    Scans every day in September for 14-night trips.

    Set weekends_only=true to reduce API calls (Fri/Sat departures only).
    """
    monitor = _get_monitor()

    if not monitor.api_key:
        raise HTTPException(503, "SERPAPI_KEY not configured")

    if not 1 <= req.month <= 12:
        raise HTTPException(400, "month must be 1-12")

    results = await monitor.scan_month(
        month=req.month,
        year=req.year,
        trip_lengths=[req.trip_length],
        weekends_only=req.weekends_only,
    )

    return {
        "status": "completed",
        "month": results["month"],
        "year": results["year"],
        "trip_length": req.trip_length,
        "weekends_only": req.weekends_only,
        "api_calls_used": results["api_calls_used"],
        "results_found": results["results_count"],
        "cheapest_5": results["cheapest_5"],
        "most_expensive_5": results["most_expensive_5"],
    }

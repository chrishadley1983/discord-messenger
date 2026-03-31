"""Flight price monitoring service.

Uses SerpAPI to search Google Flights for nonstop economy fares.
Stores price history in SQLite for trend tracking and alerting.

Usage:
    from services.flight_prices import FlightPriceMonitor

    monitor = FlightPriceMonitor()
    results = await monitor.check_all_routes()
    deals = monitor.get_deals()
"""

import asyncio
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

from logger import logger

UK_TZ = ZoneInfo("Europe/London")
DB_PATH = Path(__file__).parent.parent / "data" / "flight_prices.db"
SERPAPI_BASE = "https://serpapi.com/search"

# Default config — override via .env or API
DEFAULT_CONFIG = {
    "routes": [
        {
            "from": "LHR",
            "to": "HND",
            "label": "London to Tokyo",
        }
    ],
    "passengers": 2,
    "cabin": 1,  # 1=economy, 2=premium_economy, 3=business, 4=first
    "stops": 1,  # SerpAPI: 1=nonstop, 2=1 stop max, 3=2 stops max
    "currency": "GBP",
    "alert_threshold_pct": 10,  # alert when price drops >10% from baseline
    "alert_threshold_abs": None,  # alert when price_pp drops below this (e.g. 500)
    "scan_window_days": 180,  # how far ahead to scan
    "scan_strategy": "weekends",  # weekends | specific_dates | flexible
}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_airport TEXT NOT NULL,
                to_airport TEXT NOT NULL,
                label TEXT NOT NULL,
                passengers INTEGER DEFAULT 2,
                cabin INTEGER DEFAULT 1,
                stops INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_airport, to_airport, label)
            );

            CREATE TABLE IF NOT EXISTS price_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_id INTEGER NOT NULL,
                outbound_date TEXT NOT NULL,
                return_date TEXT NOT NULL,
                price_total REAL,
                price_pp REAL,
                airline TEXT,
                duration_min INTEGER,
                departure_time TEXT,
                arrival_time TEXT,
                source TEXT DEFAULT 'serpapi',
                raw_json TEXT,
                checked_at TEXT NOT NULL,
                FOREIGN KEY(route_id) REFERENCES routes(id)
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_id INTEGER NOT NULL,
                outbound_date TEXT,
                return_date TEXT,
                alert_type TEXT NOT NULL,
                price_pp REAL,
                previous_price_pp REAL,
                message TEXT,
                sent_at TEXT NOT NULL,
                FOREIGN KEY(route_id) REFERENCES routes(id)
            );

            CREATE INDEX IF NOT EXISTS idx_checks_route_date
                ON price_checks(route_id, outbound_date, checked_at DESC);
            CREATE INDEX IF NOT EXISTS idx_checks_checked
                ON price_checks(checked_at DESC);
            CREATE INDEX IF NOT EXISTS idx_alerts_sent
                ON alerts(sent_at DESC);
        """)


# ---------------------------------------------------------------------------
# SerpAPI client
# ---------------------------------------------------------------------------

async def search_flights(
    api_key: str,
    departure_id: str,
    arrival_id: str,
    outbound_date: str,
    return_date: str,
    adults: int = 2,
    travel_class: int = 1,
    stops: int = 0,
    currency: str = "GBP",
) -> dict[str, Any]:
    """Query SerpAPI Google Flights endpoint."""
    params = {
        "engine": "google_flights",
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "return_date": return_date,
        "adults": adults,
        "travel_class": travel_class,
        "stops": stops,
        "currency": currency,
        "hl": "en",
        "gl": "uk",
        "api_key": api_key,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(SERPAPI_BASE, params=params)
        resp.raise_for_status()
        return resp.json()


def parse_flight_results(data: dict, passengers: int = 2) -> list[dict]:
    """Extract structured flight info from SerpAPI response."""
    flights = []

    for group_key in ("best_flights", "other_flights"):
        for flight_group in data.get(group_key, []):
            price_total = flight_group.get("price")
            if price_total is None:
                continue

            # Get outbound leg details (first flight in the group)
            legs = flight_group.get("flights", [])
            if not legs:
                continue

            outbound = legs[0]
            airline = outbound.get("airline", "Unknown")
            duration = flight_group.get("total_duration", 0)
            dep = outbound.get("departure_airport", {})
            arr = outbound.get("arrival_airport", {})

            flights.append({
                "price_total": price_total,
                "price_pp": round(price_total / passengers, 2),
                "airline": airline,
                "duration_min": duration,
                "departure_time": dep.get("time", ""),
                "arrival_time": arr.get("time", ""),
                "is_best": group_key == "best_flights",
                "type": flight_group.get("type", ""),
            })

    # Sort by price
    flights.sort(key=lambda f: f["price_total"])
    return flights


def extract_price_insights(data: dict) -> dict[str, Any]:
    """Extract Google's price insights from SerpAPI response."""
    insights = data.get("price_insights", {})
    return {
        "lowest_price": insights.get("lowest_price"),
        "typical_low": insights.get("typical_price_range", [None, None])[0],
        "typical_high": insights.get("typical_price_range", [None, None])[1],
        "price_level": insights.get("price_level"),  # "low", "typical", "high"
        "price_history": insights.get("price_history", []),
    }


# ---------------------------------------------------------------------------
# Date generation
# ---------------------------------------------------------------------------

def generate_date_pairs(
    strategy: str = "weekends",
    window_days: int = 180,
    trip_lengths: list[int] = None,
    specific_dates: list[dict] = None,
    month: int = None,
    year: int = None,
    weekends_only: bool = False,
) -> list[tuple[str, str]]:
    """Generate outbound/return date pairs to search.

    Args:
        strategy: "weekends" | "specific_dates" | "flexible" | "month"
        window_days: how far ahead to scan (ignored for "month" strategy)
        trip_lengths: list of trip durations in days (default [10, 14, 17])
        specific_dates: list of {"outbound": "YYYY-MM-DD", "return": "YYYY-MM-DD"}
        month: month number (1-12) for "month" strategy
        year: year for "month" strategy (default: current/next year)
        weekends_only: if True, only include Fri/Sat departures (for "month" strategy)

    Returns:
        List of (outbound_date, return_date) string tuples
    """
    if specific_dates:
        return [(d["outbound"], d["return"]) for d in specific_dates]

    if trip_lengths is None:
        trip_lengths = [10, 14, 17]

    today = datetime.now(UK_TZ).date()
    pairs = []

    if strategy == "month" and month:
        # Scan every day (or weekends) in a specific month
        import calendar
        if year is None:
            year = today.year if month > today.month else today.year + 1
        _, days_in_month = calendar.monthrange(year, month)

        for day in range(1, days_in_month + 1):
            from datetime import date as date_cls
            dep_date = date_cls(year, month, day)
            if dep_date <= today:
                continue
            if weekends_only and dep_date.weekday() not in (4, 5):
                continue
            for length in trip_lengths:
                ret_date = dep_date + timedelta(days=length)
                pairs.append((dep_date.isoformat(), ret_date.isoformat()))

    elif strategy == "weekends":
        # Find Fridays and Saturdays in the window
        for day_offset in range(7, window_days):
            date = today + timedelta(days=day_offset)
            if date.weekday() in (4, 5):  # Friday=4, Saturday=5
                for length in trip_lengths:
                    return_date = date + timedelta(days=length)
                    pairs.append((date.isoformat(), return_date.isoformat()))

    elif strategy == "flexible":
        # Sample dates across the window (every 7 days)
        for day_offset in range(14, window_days, 7):
            date = today + timedelta(days=day_offset)
            for length in trip_lengths:
                return_date = date + timedelta(days=length)
                pairs.append((date.isoformat(), return_date.isoformat()))

    return pairs


# ---------------------------------------------------------------------------
# Monitor class
# ---------------------------------------------------------------------------

class FlightPriceMonitor:
    """Main flight price monitoring service."""

    def __init__(self, api_key: str = None, config: dict = None):
        import os
        self.api_key = api_key or os.getenv("SERPAPI_KEY", "")
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        init_db()
        self._ensure_routes()

    def _ensure_routes(self):
        """Insert default routes if they don't exist."""
        with get_db() as conn:
            for route in self.config["routes"]:
                conn.execute(
                    """INSERT OR IGNORE INTO routes (from_airport, to_airport, label, passengers, cabin, stops)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (route["from"], route["to"], route["label"],
                     self.config["passengers"], self.config["cabin"], self.config["stops"]),
                )
            conn.commit()

    def get_routes(self) -> list[dict]:
        """Get all active monitored routes."""
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM routes WHERE active = 1").fetchall()
            return [dict(r) for r in rows]

    async def check_route(
        self,
        route: dict,
        date_pairs: list[tuple[str, str]] = None,
    ) -> list[dict]:
        """Check prices for a single route across date pairs.

        Returns list of cheapest flight per date pair.
        """
        if not self.api_key:
            logger.error("SERPAPI_KEY not set — cannot check flight prices")
            return []

        if date_pairs is None:
            date_pairs = generate_date_pairs(
                strategy=self.config.get("scan_strategy", "weekends"),
                window_days=self.config.get("scan_window_days", 180),
                trip_lengths=self.config.get("trip_lengths"),
                specific_dates=self.config.get("specific_dates"),
            )

        results = []
        now = datetime.now(UK_TZ).isoformat()

        for outbound, return_date in date_pairs:
            try:
                data = await search_flights(
                    api_key=self.api_key,
                    departure_id=route["from_airport"],
                    arrival_id=route["to_airport"],
                    outbound_date=outbound,
                    return_date=return_date,
                    adults=route.get("passengers", self.config["passengers"]),
                    travel_class=route.get("cabin", self.config["cabin"]),
                    stops=route.get("stops", self.config["stops"]),
                    currency=self.config.get("currency", "GBP"),
                )

                flights = parse_flight_results(data, route.get("passengers", self.config["passengers"]))
                insights = extract_price_insights(data)

                if flights:
                    cheapest = flights[0]

                    # Store in DB
                    with get_db() as conn:
                        conn.execute(
                            """INSERT INTO price_checks
                               (route_id, outbound_date, return_date, price_total, price_pp,
                                airline, duration_min, departure_time, arrival_time, source, raw_json, checked_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'serpapi', ?, ?)""",
                            (route["id"], outbound, return_date, cheapest["price_total"],
                             cheapest["price_pp"], cheapest["airline"], cheapest["duration_min"],
                             cheapest["departure_time"], cheapest["arrival_time"],
                             json.dumps({"flights": flights[:5], "insights": insights}), now),
                        )
                        conn.commit()

                    results.append({
                        "outbound": outbound,
                        "return": return_date,
                        "cheapest": cheapest,
                        "all_flights": flights[:5],
                        "insights": insights,
                    })

                # Rate limit: ~1 req/sec to stay within SerpAPI limits
                await asyncio.sleep(1.0)

            except httpx.HTTPStatusError as e:
                logger.warning(f"SerpAPI error for {outbound}-{return_date}: {e.response.status_code}")
                if e.response.status_code == 429:
                    logger.warning("Rate limited — stopping scan")
                    break
            except Exception as e:
                logger.warning(f"Flight check failed for {outbound}-{return_date}: {e}")

        return results

    async def check_all_routes(self, date_pairs: list[tuple[str, str]] = None) -> dict[str, Any]:
        """Check all active routes. Returns summary."""
        routes = self.get_routes()
        all_results = {}

        for route in routes:
            results = await self.check_route(route, date_pairs)
            all_results[route["label"]] = {
                "route": route,
                "results": results,
            }

        return all_results

    async def quick_check(self, outbound: str, return_date: str) -> dict[str, Any]:
        """Single date pair check across all routes. For on-demand queries."""
        return await self.check_all_routes(date_pairs=[(outbound, return_date)])

    async def scan_month(
        self,
        month: int,
        year: int = None,
        trip_lengths: list[int] = None,
        weekends_only: bool = False,
    ) -> dict[str, Any]:
        """Scan an entire month for the cheapest dates.

        Args:
            month: 1-12
            year: defaults to current/next year
            trip_lengths: durations in days (default [14])
            weekends_only: only scan Fri/Sat departures (fewer API calls)

        Returns:
            Dict with all results sorted by price, plus best date recommendation.
        """
        if trip_lengths is None:
            trip_lengths = [14]

        pairs = generate_date_pairs(
            strategy="month",
            month=month,
            year=year,
            trip_lengths=trip_lengths,
            weekends_only=weekends_only,
        )

        logger.info(f"Month scan: {len(pairs)} date pairs for month={month} year={year}")

        results = await self.check_all_routes(date_pairs=pairs)

        # Flatten and sort by price
        all_prices = []
        for label, data in results.items():
            for r in data["results"]:
                all_prices.append({
                    "route": label,
                    "outbound": r["outbound"],
                    "return": r["return"],
                    "price_pp": r["cheapest"]["price_pp"],
                    "price_total": r["cheapest"]["price_total"],
                    "airline": r["cheapest"]["airline"],
                    "duration_min": r["cheapest"]["duration_min"],
                    "insights": r.get("insights", {}),
                })

        all_prices.sort(key=lambda p: p["price_pp"])

        return {
            "month": month,
            "year": year or datetime.now(UK_TZ).year,
            "trip_lengths": trip_lengths,
            "weekends_only": weekends_only,
            "api_calls_used": len(pairs),
            "results_count": len(all_prices),
            "cheapest_5": all_prices[:5],
            "most_expensive_5": all_prices[-5:] if len(all_prices) >= 5 else [],
            "all_results": all_prices,
        }

    # -----------------------------------------------------------------------
    # Analysis
    # -----------------------------------------------------------------------

    def get_cheapest(self, route_id: int = None, days_back: int = 7, limit: int = 10) -> list[dict]:
        """Get cheapest prices found in recent checks."""
        with get_db() as conn:
            query = """
                SELECT pc.*, r.label, r.from_airport, r.to_airport
                FROM price_checks pc
                JOIN routes r ON r.id = pc.route_id
                WHERE pc.checked_at > datetime('now', ?)
            """
            params: list = [f"-{days_back} days"]

            if route_id:
                query += " AND pc.route_id = ?"
                params.append(route_id)

            query += " ORDER BY pc.price_pp ASC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_price_trend(self, route_id: int, outbound_date: str) -> list[dict]:
        """Get price history for a specific route+date combo."""
        with get_db() as conn:
            rows = conn.execute(
                """SELECT price_pp, price_total, airline, checked_at
                   FROM price_checks
                   WHERE route_id = ? AND outbound_date = ?
                   ORDER BY checked_at ASC""",
                (route_id, outbound_date),
            ).fetchall()
            return [dict(r) for r in rows]

    def detect_deals(self, route_id: int = None) -> list[dict]:
        """Find prices that are significantly below baseline.

        A "deal" is when the latest price for a date is:
        - Below the absolute threshold (if set), OR
        - X% below the average price we've seen for that date
        """
        threshold_pct = self.config.get("alert_threshold_pct", 10)
        threshold_abs = self.config.get("alert_threshold_abs")
        deals = []

        with get_db() as conn:
            # Get latest price per route+date combo
            query = """
                SELECT pc.route_id, pc.outbound_date, pc.return_date,
                       pc.price_pp, pc.price_total, pc.airline, pc.checked_at,
                       r.label
                FROM price_checks pc
                JOIN routes r ON r.id = pc.route_id
                WHERE pc.id IN (
                    SELECT id FROM price_checks sub
                    WHERE sub.route_id = pc.route_id
                      AND sub.outbound_date = pc.outbound_date
                      AND sub.return_date = pc.return_date
                    ORDER BY sub.checked_at DESC
                    LIMIT 1
                )
            """
            params = []
            if route_id:
                query += " AND pc.route_id = ?"
                params.append(route_id)

            for row in conn.execute(query, params).fetchall():
                row = dict(row)

                # Check absolute threshold
                if threshold_abs and row["price_pp"] <= threshold_abs:
                    row["deal_type"] = "below_target"
                    row["target"] = threshold_abs
                    deals.append(row)
                    continue

                # Check percentage drop vs average
                avg_row = conn.execute(
                    """SELECT AVG(price_pp) as avg_pp, MIN(price_pp) as min_pp, COUNT(*) as checks
                       FROM price_checks
                       WHERE route_id = ? AND outbound_date = ?""",
                    (row["route_id"], row["outbound_date"]),
                ).fetchone()

                if avg_row and avg_row["checks"] > 1 and avg_row["avg_pp"]:
                    drop_pct = ((avg_row["avg_pp"] - row["price_pp"]) / avg_row["avg_pp"]) * 100
                    if drop_pct >= threshold_pct:
                        row["deal_type"] = "price_drop"
                        row["drop_pct"] = round(drop_pct, 1)
                        row["avg_price_pp"] = round(avg_row["avg_pp"], 2)
                        row["min_price_pp"] = round(avg_row["min_pp"], 2)
                        deals.append(row)

        deals.sort(key=lambda d: d["price_pp"])
        return deals

    def get_summary(self, days_back: int = 7) -> dict[str, Any]:
        """Get a summary of recent monitoring activity."""
        with get_db() as conn:
            total_checks = conn.execute(
                "SELECT COUNT(*) as n FROM price_checks WHERE checked_at > datetime('now', ?)",
                (f"-{days_back} days",),
            ).fetchone()["n"]

            cheapest = conn.execute(
                """SELECT pc.*, r.label FROM price_checks pc
                   JOIN routes r ON r.id = pc.route_id
                   WHERE pc.checked_at > datetime('now', ?)
                   ORDER BY pc.price_pp ASC LIMIT 1""",
                (f"-{days_back} days",),
            ).fetchone()

            routes = conn.execute("SELECT COUNT(*) as n FROM routes WHERE active = 1").fetchone()["n"]

            recent_alerts = conn.execute(
                "SELECT COUNT(*) as n FROM alerts WHERE sent_at > datetime('now', ?)",
                (f"-{days_back} days",),
            ).fetchone()["n"]

        return {
            "period_days": days_back,
            "total_checks": total_checks,
            "active_routes": routes,
            "recent_alerts": recent_alerts,
            "cheapest": dict(cheapest) if cheapest else None,
        }

    # -----------------------------------------------------------------------
    # Route management
    # -----------------------------------------------------------------------

    def add_route(self, from_airport: str, to_airport: str, label: str,
                  passengers: int = 2, cabin: int = 1, stops: int = 0) -> int:
        """Add a new route to monitor. Returns route_id."""
        with get_db() as conn:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO routes (from_airport, to_airport, label, passengers, cabin, stops)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (from_airport, to_airport, label, passengers, cabin, stops),
            )
            conn.commit()
            if cursor.lastrowid:
                return cursor.lastrowid
            # Already exists — fetch id
            row = conn.execute(
                "SELECT id FROM routes WHERE from_airport = ? AND to_airport = ? AND label = ?",
                (from_airport, to_airport, label),
            ).fetchone()
            return row["id"]

    def remove_route(self, route_id: int):
        """Deactivate a route (soft delete)."""
        with get_db() as conn:
            conn.execute("UPDATE routes SET active = 0 WHERE id = ?", (route_id,))
            conn.commit()

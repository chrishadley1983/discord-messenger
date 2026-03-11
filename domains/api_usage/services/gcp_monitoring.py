"""Google Cloud Platform cost monitoring.

Two data sources:
  1. Supabase gemini_api_usage table — actual token counts for Gemini calls
     (image tokens estimated at ~258 per call since the extension only logs text tokens)
  2. Cloud Monitoring API — request counts for Maps, Geocoding, etc.

The balance monitor calls get_gcp_cost_summary() which combines both.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Service account key location (for Cloud Monitoring)
_DEFAULT_KEY_PATH = Path(__file__).parent.parent.parent.parent / "data" / "gcp-service-account.json"
GCP_KEY_PATH = Path(os.getenv("GCP_SERVICE_ACCOUNT_KEY", str(_DEFAULT_KEY_PATH)))
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")

# Supabase config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

# Gemini pricing (USD per 1M tokens)
GEMINI_PRICING = {
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.5-flash": {"input": 0.15, "output": 3.50},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "_default": {"input": 0.50, "output": 2.00},
}

# Estimated image tokens per Gemini Vision call (not tracked by the extension)
# Vinted Sniper sends product photos — typically 258-765 tokens depending on resolution
EST_IMAGE_TOKENS_PER_CALL = 258

# Maps API pricing (USD per 1,000 requests)
MAPS_PRICING_PER_1K = {
    "directions-backend.googleapis.com": ("Directions", 5.00),
    "geocoding-backend.googleapis.com": ("Geocoding", 5.00),
    "places-backend.googleapis.com": ("Places", 32.00),
    "distance-matrix-backend.googleapis.com": ("Distance Matrix", 5.00),
    "timezone-backend.googleapis.com": ("Timezone", 5.00),
    "elevation-backend.googleapis.com": ("Elevation", 5.00),
    "static-maps-backend.googleapis.com": ("Static Maps", 2.00),
    "street-view-image-backend.googleapis.com": ("Street View", 7.00),
    "routes.googleapis.com": ("Routes", 5.00),
    "translate.googleapis.com": ("Translation", 20.00),
}

# Free APIs (no cost)
FREE_APIS = {
    "gmail.googleapis.com",
    "calendar-json.googleapis.com",
    "drive.googleapis.com",
    "sheets.googleapis.com",
    "docs.googleapis.com",
    "youtube.googleapis.com",
    "artifactregistry.googleapis.com",
    "monitoring.googleapis.com",
    "generativelanguage.googleapis.com",  # Costed separately via Supabase
}


def _monitoring_configured() -> bool:
    return GCP_KEY_PATH.exists() and bool(GCP_PROJECT_ID)


async def _get_gemini_cost(start_iso: str, end_iso: str = None) -> dict:
    """Get Gemini API cost from Supabase gemini_api_usage table.

    Returns dict with calls, tokens, cost, and per-model breakdown.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"error": "Supabase not configured", "cost_usd": 0}

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Prefer": "count=exact",
    }

    # Build query params
    params = {
        "select": "model,input_tokens,output_tokens",
        "created_at": f"gte.{start_iso}",
        "order": "created_at.asc",
        "limit": "10000",
    }
    if end_iso:
        params["and"] = f"(created_at.lt.{end_iso})"

    try:
        # Get count first
        async with httpx.AsyncClient() as client:
            count_resp = await client.head(
                f"{SUPABASE_URL}/rest/v1/gemini_api_usage",
                params={
                    "select": "created_at",
                    "created_at": f"gte.{start_iso}",
                    **({"and": f"(created_at.lt.{end_iso})"} if end_iso else {}),
                },
                headers=headers,
                timeout=10,
            )
            total_count = 0
            content_range = count_resp.headers.get("content-range", "")
            if "/" in content_range:
                try:
                    total_count = int(content_range.split("/")[1])
                except (ValueError, IndexError):
                    pass

            # Get token data (sample up to 10000 rows)
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/gemini_api_usage",
                params=params,
                headers={k: v for k, v in headers.items() if k != "Prefer"},
                timeout=15,
            )

            if resp.status_code != 200:
                return {"error": f"Supabase {resp.status_code}", "cost_usd": 0}

            rows = resp.json()

        if not rows:
            return {"calls": 0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}

        # Aggregate by model
        models = {}
        for row in rows:
            model = row.get("model", "unknown")
            if model not in models:
                models[model] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
            models[model]["calls"] += 1
            models[model]["input_tokens"] += (row.get("input_tokens") or 0)
            models[model]["output_tokens"] += (row.get("output_tokens") or 0)

        # Scale up if we sampled
        sample_count = len(rows)
        scale = total_count / sample_count if total_count > sample_count else 1.0

        # Calculate cost per model
        total_cost = 0.0
        total_input = 0
        total_output = 0
        model_breakdown = []

        for model, data in models.items():
            pricing = GEMINI_PRICING.get(model, GEMINI_PRICING["_default"])
            calls = int(data["calls"] * scale)
            input_tokens = int(data["input_tokens"] * scale)
            output_tokens = int(data["output_tokens"] * scale)

            # Add estimated image tokens
            image_tokens = calls * EST_IMAGE_TOKENS_PER_CALL
            effective_input = input_tokens + image_tokens

            cost = (effective_input * pricing["input"] / 1e6) + (output_tokens * pricing["output"] / 1e6)
            total_cost += cost
            total_input += effective_input
            total_output += output_tokens

            model_breakdown.append({
                "model": model,
                "calls": calls,
                "input_tokens": effective_input,
                "output_tokens": output_tokens,
                "cost_usd": round(cost, 4),
            })

        return {
            "calls": total_count or sample_count,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost_usd": round(total_cost, 4),
            "models": model_breakdown,
        }

    except Exception as e:
        logger.error(f"Gemini cost query error: {e}")
        return {"error": str(e), "cost_usd": 0}


async def _get_maps_cost(hours: int) -> dict:
    """Get Maps/other paid API costs from Cloud Monitoring."""
    if not _monitoring_configured():
        return {"cost_usd": 0, "breakdown": [], "note": "Cloud Monitoring not configured"}

    try:
        import asyncio
        return await asyncio.to_thread(_query_maps_sync, hours)
    except ImportError:
        return {"cost_usd": 0, "breakdown": [], "note": "google-cloud-monitoring not installed"}
    except Exception as e:
        logger.error(f"Maps cost query error: {e}")
        return {"cost_usd": 0, "breakdown": [], "error": str(e)}


def _query_maps_sync(hours: int) -> dict:
    """Query Cloud Monitoring for non-Gemini API usage."""
    from google.cloud import monitoring_v3
    from google.oauth2 import service_account
    import time

    credentials = service_account.Credentials.from_service_account_file(
        str(GCP_KEY_PATH),
        scopes=["https://www.googleapis.com/auth/monitoring.read"],
    )

    client = monitoring_v3.MetricServiceClient(credentials=credentials)
    project_name = f"projects/{GCP_PROJECT_ID}"

    now = time.time()
    interval = monitoring_v3.TimeInterval({
        "end_time": {"seconds": int(now)},
        "start_time": {"seconds": int(now) - (hours * 3600)},
    })

    results = client.list_time_series(request={
        "name": project_name,
        "filter": 'metric.type = "serviceruntime.googleapis.com/api/request_count"',
        "interval": interval,
        "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
    })

    # Aggregate by service, only paid APIs
    services = {}
    for ts in results:
        service = ts.resource.labels.get("service", "unknown")
        if service in FREE_APIS:
            continue

        total_requests = sum(point.value.int64_value for point in ts.points)
        if service not in services:
            services[service] = 0
        services[service] += total_requests

    # Calculate costs
    breakdown = []
    total_cost = 0.0
    for service, requests in sorted(services.items(), key=lambda x: -x[1]):
        name, rate = MAPS_PRICING_PER_1K.get(service, (service, 5.00))
        cost = requests * rate / 1000
        total_cost += cost
        breakdown.append({
            "name": name,
            "requests": requests,
            "cost_usd": round(cost, 4),
        })

    return {
        "cost_usd": round(total_cost, 4),
        "breakdown": breakdown,
    }


async def get_gcp_cost_summary() -> dict:
    """Get combined GCP cost summary for the balance monitor.

    Returns:
        Dict with past_hour and month_to_date costs, combining Gemini + Maps data.
    """
    now = datetime.now(timezone.utc)
    hour_ago = (now - timedelta(hours=1)).isoformat()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    hours_in_month = (now - month_start).total_seconds() / 3600

    try:
        import asyncio

        # Fetch all data in parallel
        gemini_hour, gemini_mtd, maps_mtd = await asyncio.gather(
            _get_gemini_cost(hour_ago),
            _get_gemini_cost(month_start.isoformat()),
            _get_maps_cost(hours=int(hours_in_month) or 1),
            return_exceptions=True,
        )

        # Handle exceptions
        if isinstance(gemini_hour, Exception):
            gemini_hour = {"error": str(gemini_hour), "cost_usd": 0}
        if isinstance(gemini_mtd, Exception):
            gemini_mtd = {"error": str(gemini_mtd), "cost_usd": 0}
        if isinstance(maps_mtd, Exception):
            maps_mtd = {"cost_usd": 0, "breakdown": []}

        # Past hour
        hour_cost = gemini_hour.get("cost_usd", 0)
        hour_calls = gemini_hour.get("calls", 0)

        # Month to date
        gemini_mtd_cost = gemini_mtd.get("cost_usd", 0)
        maps_mtd_cost = maps_mtd.get("cost_usd", 0)
        mtd_cost = gemini_mtd_cost + maps_mtd_cost
        mtd_calls = gemini_mtd.get("calls", 0)

        # Projection
        days_elapsed = hours_in_month / 24
        if days_elapsed > 0.5:
            projected = mtd_cost / days_elapsed * 30
        else:
            projected = 0

        return {
            "configured": True,
            "past_hour": {
                "cost_usd": round(hour_cost, 4),
                "gemini_calls": hour_calls,
            },
            "month_to_date": {
                "cost_usd": round(mtd_cost, 3),
                "gemini_cost_usd": round(gemini_mtd_cost, 3),
                "maps_cost_usd": round(maps_mtd_cost, 3),
                "gemini_calls": mtd_calls,
                "maps_breakdown": maps_mtd.get("breakdown", []),
            },
            "projected_monthly_usd": round(projected, 2),
            "projected_monthly_gbp": round(projected * 0.79, 2),
            "days_elapsed": round(days_elapsed, 1),
        }

    except Exception as e:
        logger.error(f"GCP cost summary error: {e}")
        return {"configured": True, "error": str(e)}


# Keep these for the REST API endpoints
async def get_gcp_api_usage(hours: int = 24) -> dict:
    """Get API request counts per service from Cloud Monitoring."""
    if not _monitoring_configured():
        return {
            "configured": False,
            "error": "GCP monitoring not configured",
            "setup_instructions": (
                "1. GCP Console → IAM → Service Accounts → Create\n"
                "2. Grant role: Monitoring Viewer\n"
                "3. Create JSON key → save as data/gcp-service-account.json\n"
                "4. Add GCP_PROJECT_ID=<your-project-id> to .env"
            ),
        }
    try:
        import asyncio
        maps = await asyncio.to_thread(_query_maps_sync, hours)
        gemini = await _get_gemini_cost(
            (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        )
        return {
            "configured": True,
            "hours": hours,
            "gemini": gemini,
            "maps": maps,
            "total_cost_usd": round(gemini.get("cost_usd", 0) + maps.get("cost_usd", 0), 3),
        }
    except Exception as e:
        return {"configured": True, "error": str(e)}


async def get_gcp_monthly_estimate() -> dict:
    """Get month-to-date GCP spend with projection."""
    return await get_gcp_cost_summary()

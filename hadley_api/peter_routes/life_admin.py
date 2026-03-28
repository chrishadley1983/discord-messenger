"""Life Admin Agent API Routes.

CRUD and action endpoints for household obligations (MOT, insurance,
subscriptions, etc.) with recurring-obligation support, alert computation,
and email-scan tracking.

Tables:
  - life_admin_obligations
  - life_admin_alert_history
  - life_admin_email_scans
"""

import os
import httpx
from datetime import date, datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta

from hadley_api.auth import require_auth

UK_TZ = ZoneInfo("Europe/London")

router = APIRouter(prefix="/life-admin", tags=["Life Admin"])

# ============================================================
# Configuration
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

TABLE = "life_admin_obligations"
ALERT_HISTORY_TABLE = "life_admin_alert_history"
SCAN_HISTORY_TABLE = "life_admin_email_scans"


def _headers(*, prefer: str = "return=representation") -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


# ============================================================
# Pydantic Models
# ============================================================

class ObligationCreate(BaseModel):
    name: str
    category: str
    due_date: date
    subcategory: Optional[str] = None
    description: Optional[str] = None
    renewal_date: Optional[date] = None
    recurrence_months: Optional[int] = None
    auto_renews: bool = False
    alert_lead_days: list[int] = Field(default_factory=lambda: [90, 30, 14, 7, 3])
    alert_priority: str = "medium"
    provider: Optional[str] = None
    reference_number: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "GBP"
    url: Optional[str] = None
    gmail_query: Optional[str] = None
    notes: Optional[str] = None
    status: str = "active"


class ObligationUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[date] = None
    renewal_date: Optional[date] = None
    recurrence_months: Optional[int] = None
    auto_renews: Optional[bool] = None
    alert_lead_days: Optional[list[int]] = None
    alert_priority: Optional[str] = None
    provider: Optional[str] = None
    reference_number: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    url: Optional[str] = None
    gmail_query: Optional[str] = None
    last_email_id: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    snoozed_until: Optional[date] = None


class SnoozeBody(BaseModel):
    until: date


class AlertRecordBody(BaseModel):
    obligation_id: UUID
    alert_tier: str
    channel: str = "#alerts"


class ScanRecordBody(BaseModel):
    emails_checked: int = 0
    obligations_created: int = 0
    obligations_updated: int = 0
    details: Optional[dict] = None


# ============================================================
# Helper
# ============================================================

def _today() -> date:
    return datetime.now(UK_TZ).date()


async def _fetch_obligation(client: httpx.AsyncClient, obligation_id: UUID) -> dict:
    """Fetch a single obligation by ID. Raises 404 if not found."""
    resp = await client.get(
        f"{SUPABASE_URL}/rest/v1/{TABLE}",
        headers=_headers(),
        params={"id": f"eq.{obligation_id}", "limit": "1"},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    rows = resp.json()
    if not rows:
        raise HTTPException(status_code=404, detail="Obligation not found")
    return rows[0]


# ============================================================
# CRUD Endpoints
# ============================================================

@router.get("/obligations")
async def list_obligations(
    status: Optional[str] = Query(default="active"),
    category: Optional[str] = Query(default=None),
):
    """List obligations with optional status and category filters."""
    params: dict = {
        "select": "*",
        "order": "due_date.asc",
    }
    if status:
        params["status"] = f"eq.{status}"
    if category:
        params["category"] = f"eq.{category}"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params=params,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


@router.get("/obligations/{obligation_id}")
async def get_obligation(obligation_id: UUID):
    """Get a single obligation by ID."""
    async with httpx.AsyncClient(timeout=15) as client:
        return await _fetch_obligation(client, obligation_id)


@router.post("/obligations", status_code=201, dependencies=[Depends(require_auth)])
async def create_obligation(body: ObligationCreate):
    """Create a new obligation."""
    payload = body.model_dump(mode="json", exclude_none=True)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            json=payload,
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        rows = resp.json()
        return rows[0] if rows else payload


@router.patch("/obligations/{obligation_id}", dependencies=[Depends(require_auth)])
async def update_obligation(obligation_id: UUID, body: ObligationUpdate):
    """Partial update of an obligation. Auto-sets updated_at."""
    payload = body.model_dump(mode="json", exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    payload["updated_at"] = datetime.now(UK_TZ).isoformat()

    async with httpx.AsyncClient(timeout=15) as client:
        # Verify existence first
        await _fetch_obligation(client, obligation_id)

        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params={"id": f"eq.{obligation_id}"},
            json=payload,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        rows = resp.json()
        return rows[0] if rows else {"id": str(obligation_id), **payload}


@router.delete("/obligations/{obligation_id}", dependencies=[Depends(require_auth)])
async def delete_obligation(obligation_id: UUID):
    """Delete an obligation."""
    async with httpx.AsyncClient(timeout=15) as client:
        await _fetch_obligation(client, obligation_id)

        resp = await client.delete(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params={"id": f"eq.{obligation_id}"},
        )
        if resp.status_code not in (200, 204):
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return {"status": "deleted", "id": str(obligation_id)}


# ============================================================
# Action Endpoints
# ============================================================

@router.post("/obligations/{obligation_id}/action", dependencies=[Depends(require_auth)])
async def action_obligation(obligation_id: UUID):
    """Mark obligation as actioned. If recurring, create the next occurrence."""
    today = _today()

    async with httpx.AsyncClient(timeout=15) as client:
        obligation = await _fetch_obligation(client, obligation_id)

        # Mark current as actioned
        update_payload = {
            "status": "actioned",
            "last_actioned_date": today.isoformat(),
            "updated_at": datetime.now(UK_TZ).isoformat(),
        }
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params={"id": f"eq.{obligation_id}"},
            json=update_payload,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        actioned = resp.json()[0] if resp.json() else {**obligation, **update_payload}

        # Create next occurrence if recurring
        new_obligation = None
        recurrence_months = obligation.get("recurrence_months")
        if recurrence_months:
            original_due = date.fromisoformat(obligation["due_date"])
            next_due = original_due + relativedelta(months=recurrence_months)

            new_payload = {
                "name": obligation["name"],
                "category": obligation["category"],
                "due_date": next_due.isoformat(),
                "subcategory": obligation.get("subcategory"),
                "description": obligation.get("description"),
                "alert_lead_days": obligation.get("alert_lead_days", [90, 30, 14, 7, 3]),
                "alert_priority": obligation.get("alert_priority", "medium"),
                "recurrence_months": recurrence_months,
                "auto_renews": obligation.get("auto_renews", False),
                "provider": obligation.get("provider"),
                "reference_number": obligation.get("reference_number"),
                "amount": obligation.get("amount"),
                "currency": obligation.get("currency", "GBP"),
                "url": obligation.get("url"),
                "gmail_query": obligation.get("gmail_query"),
                "notes": obligation.get("notes"),
                "status": "active",
            }
            # Remove None values to let DB defaults apply
            new_payload = {k: v for k, v in new_payload.items() if v is not None}

            resp2 = await client.post(
                f"{SUPABASE_URL}/rest/v1/{TABLE}",
                headers=_headers(),
                json=new_payload,
            )
            if resp2.status_code in (200, 201) and resp2.json():
                new_obligation = resp2.json()[0]

        result = {"actioned": actioned}
        if new_obligation:
            result["next_occurrence"] = new_obligation
        return result


@router.post("/obligations/{obligation_id}/snooze", dependencies=[Depends(require_auth)])
async def snooze_obligation(obligation_id: UUID, body: SnoozeBody):
    """Snooze an obligation until a given date."""
    async with httpx.AsyncClient(timeout=15) as client:
        await _fetch_obligation(client, obligation_id)

        payload = {
            "status": "snoozed",
            "snoozed_until": body.until.isoformat(),
            "updated_at": datetime.now(UK_TZ).isoformat(),
        }
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params={"id": f"eq.{obligation_id}"},
            json=payload,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        rows = resp.json()
        return rows[0] if rows else {"id": str(obligation_id), **payload}


# ============================================================
# Query Endpoints
# ============================================================

@router.get("/alerts")
async def get_alerts(hours: int = Query(default=24)):
    """Compute obligation alerts grouped by urgency tier.

    For each active obligation, checks which alert_lead_days thresholds
    have been crossed and cross-references alert_history to avoid
    re-sending. Returns tiers: overdue, due_today, and each lead-day tier.
    """
    today = _today()

    async with httpx.AsyncClient(timeout=15) as client:
        # Fetch active obligations (include snoozed — we filter below)
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params={
                "select": "*",
                "status": "in.(active,snoozed)",
                "order": "due_date.asc",
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        obligations = resp.json()

        # Fetch recent alert history
        cutoff = (datetime.now(UK_TZ) - relativedelta(months=3)).isoformat()
        hist_resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{ALERT_HISTORY_TABLE}",
            headers=_headers(),
            params={
                "select": "obligation_id,alert_tier,sent_at",
                "sent_at": f"gte.{cutoff}",
            },
        )
        sent_alerts: dict[str, set[str]] = {}
        if hist_resp.status_code == 200:
            for row in hist_resp.json():
                oid = row["obligation_id"]
                sent_alerts.setdefault(oid, set()).add(row["alert_tier"])

    # Build alert tiers
    alerts: dict[str, list] = {
        "overdue": [],
        "due_today": [],
    }
    # Group by priority for delivery routing
    by_priority: dict[str, list] = {
        "critical": [],
        "high": [],
        "medium": [],
        "low": [],
    }

    for ob in obligations:
        # Skip snoozed obligations whose snooze hasn't expired
        if ob.get("status") == "snoozed":
            snoozed_until = ob.get("snoozed_until")
            if snoozed_until and date.fromisoformat(snoozed_until) > today:
                continue

        due = date.fromisoformat(ob["due_date"])
        days_until = (due - today).days
        oid = ob["id"]
        already_sent = sent_alerts.get(oid, set())
        priority = ob.get("alert_priority", "medium")

        if days_until < 0:
            ob["days_overdue"] = abs(days_until)
            tier = "overdue"
            if tier not in already_sent:
                ob["alert_tier"] = tier
                alerts["overdue"].append(ob)
                by_priority.get(priority, by_priority["medium"]).append(ob)
        elif days_until == 0:
            tier = "due_today"
            if tier not in already_sent:
                ob["alert_tier"] = tier
                alerts["due_today"].append(ob)
                by_priority.get(priority, by_priority["medium"]).append(ob)
        else:
            lead_days = ob.get("alert_lead_days") or [90, 30, 14, 7, 3]
            for ld in sorted(lead_days, reverse=True):
                if days_until <= ld:
                    tier = f"{ld}d"
                    if tier not in already_sent:
                        alerts.setdefault(tier, [])
                        ob["days_until_due"] = days_until
                        ob["alert_tier"] = tier
                        alerts[tier].append(ob)
                        by_priority.get(priority, by_priority["medium"]).append(ob)
                    break  # Only the widest matching tier

    # Remove empty tiers / priority groups
    alerts = {k: v for k, v in alerts.items() if v}
    by_priority = {k: v for k, v in by_priority.items() if v}

    return {
        "as_of": today.isoformat(),
        "total_alerts": sum(len(v) for v in alerts.values()),
        "tiers": alerts,
        "by_priority": by_priority,
    }


@router.get("/dashboard")
async def get_dashboard():
    """Dashboard data: obligations grouped by status with counts."""
    today = _today()
    end_of_week = today + relativedelta(weekday=6)  # Next Sunday
    end_of_month = (today + relativedelta(months=1)).replace(day=1) - relativedelta(days=1)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=_headers(),
            params={"select": "*", "order": "due_date.asc"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        all_obs = resp.json()

    groups: dict[str, list] = {
        "overdue": [],
        "due_this_week": [],
        "due_this_month": [],
        "all_clear": [],
        "snoozed": [],
        "actioned_recently": [],
    }

    for ob in all_obs:
        status = ob.get("status", "active")
        due = date.fromisoformat(ob["due_date"]) if ob.get("due_date") else None

        if status == "snoozed":
            groups["snoozed"].append(ob)
        elif status == "actioned":
            actioned_date = ob.get("last_actioned_date")
            if actioned_date and (today - date.fromisoformat(actioned_date)).days <= 30:
                groups["actioned_recently"].append(ob)
        elif status == "active" and due:
            if due < today:
                groups["overdue"].append(ob)
            elif due <= end_of_week:
                groups["due_this_week"].append(ob)
            elif due <= end_of_month:
                groups["due_this_month"].append(ob)
            else:
                groups["all_clear"].append(ob)

    return {
        "as_of": today.isoformat(),
        "counts": {k: len(v) for k, v in groups.items()},
        "groups": groups,
    }


# ============================================================
# Alert History Endpoints
# ============================================================

@router.post("/alerts/record", status_code=201, dependencies=[Depends(require_auth)])
async def record_alert(body: AlertRecordBody):
    """Record that an alert was sent for an obligation tier."""
    payload = {
        "obligation_id": str(body.obligation_id),
        "alert_tier": body.alert_tier,
        "channel": body.channel,
        "sent_at": datetime.now(UK_TZ).isoformat(),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/{ALERT_HISTORY_TABLE}",
            headers=_headers(),
            json=payload,
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        rows = resp.json()
        return rows[0] if rows else payload


# ============================================================
# Email Scan Endpoints
# ============================================================

@router.post("/scans", status_code=201, dependencies=[Depends(require_auth)])
async def record_scan(body: ScanRecordBody):
    """Record an email scan result."""
    payload = {
        "emails_checked": body.emails_checked,
        "obligations_created": body.obligations_created,
        "obligations_updated": body.obligations_updated,
        "details": body.details,
        "scanned_at": datetime.now(UK_TZ).isoformat(),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/{SCAN_HISTORY_TABLE}",
            headers=_headers(),
            json=payload,
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        rows = resp.json()
        return rows[0] if rows else payload


@router.get("/scans")
async def list_scans(limit: int = Query(default=10, le=100)):
    """Get recent email scan history."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{SCAN_HISTORY_TABLE}",
            headers=_headers(),
            params={
                "select": "*",
                "order": "scanned_at.desc",
                "limit": str(limit),
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

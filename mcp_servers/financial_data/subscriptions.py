"""Subscription management functions for Peter's MCP tools.

Provides CRUD operations on the finance.subscriptions table and
exclusion management for the health check's new-recurring detection.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Optional

import httpx

from .config import SUPABASE_URL, API_KEY
from .supabase_client import finance_query

_REST = f"{SUPABASE_URL}/rest/v1"


def _headers(*, write: bool = False) -> dict[str, str]:
    h = {
        "apikey": API_KEY,
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept-Profile": "finance",
        "Content-Profile": "finance",
    }
    if write:
        h["Prefer"] = "return=representation"
    return h


# ---------------------------------------------------------------------------
# Add subscription
# ---------------------------------------------------------------------------
async def add_subscription(
    name: str,
    amount: float,
    frequency: str = "monthly",
    scope: str = "personal",
    category: str | None = None,
    bank_description_pattern: str | None = None,
    payment_method: str | None = None,
    status: str = "active",
    notes: str | None = None,
) -> str:
    """Create a new tracked subscription."""
    body: dict = {
        "name": name,
        "amount": amount,
        "frequency": frequency,
        "scope": scope,
        "status": status,
    }
    if category:
        body["category"] = category
    if bank_description_pattern:
        body["bank_description_pattern"] = bank_description_pattern
    if payment_method:
        body["payment_method"] = payment_method
    if notes:
        body["notes"] = notes

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_REST}/subscriptions",
            headers={**_headers(write=True), "Prefer": "return=representation,resolution=merge-duplicates"},
            json=body,
        )
        if resp.status_code >= 400:
            return f"Failed to add subscription: {resp.text}"

        result = resp.json()
        sub = result[0] if isinstance(result, list) else result
        return (
            f"Added subscription: {sub['name']} — "
            f"{sub['amount']}/{sub['frequency']} ({sub['scope']})"
        )


# ---------------------------------------------------------------------------
# Update subscription (price, status, etc.)
# ---------------------------------------------------------------------------
async def update_subscription(
    name: str,
    amount: float | None = None,
    status: str | None = None,
    frequency: str | None = None,
    notes: str | None = None,
) -> str:
    """Update an existing subscription by name (case-insensitive partial match)."""
    # Find the subscription
    rows = await finance_query("subscriptions", {
        "select": "id,name,amount,frequency,status",
        "name": f"ilike.*{name}*",
    })

    if not rows:
        return f"No subscription found matching '{name}'."
    if len(rows) > 1:
        names = ", ".join(r["name"] for r in rows)
        return f"Multiple matches for '{name}': {names}. Be more specific."

    sub = rows[0]
    body: dict = {"updated_at": "now()"}
    changes = []

    if amount is not None:
        changes.append(f"amount: {sub['amount']} -> {amount}")
        body["amount"] = amount
    if status is not None:
        changes.append(f"status: {sub['status']} -> {status}")
        body["status"] = status
    if frequency is not None:
        changes.append(f"frequency: {sub['frequency']} -> {frequency}")
        body["frequency"] = frequency
    if notes is not None:
        body["notes"] = notes
        changes.append("notes updated")

    if not changes:
        return f"No changes specified for {sub['name']}."

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            f"{_REST}/subscriptions?id=eq.{sub['id']}",
            headers=_headers(write=True),
            json=body,
        )
        if resp.status_code >= 400:
            return f"Failed to update: {resp.text}"

    return f"Updated {sub['name']}: {', '.join(changes)}"


# ---------------------------------------------------------------------------
# Cancel subscription
# ---------------------------------------------------------------------------
async def cancel_subscription(name: str) -> str:
    """Mark a subscription as cancelled."""
    return await update_subscription(name, status="cancelled")


# ---------------------------------------------------------------------------
# Dismiss recurring alert (add to exclusions)
# ---------------------------------------------------------------------------
async def dismiss_recurring_alert(
    description_pattern: str,
    reason: str | None = None,
) -> str:
    """Exclude a transaction pattern from future subscription detection.

    Use when Chris says something like 'ignore Dart Charge' or
    'that's not a subscription'.
    """
    body = {"description_pattern": description_pattern.lower().strip()}
    if reason:
        body["reason"] = reason

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_REST}/subscription_exclusions",
            headers=_headers(write=True),
            json=body,
        )
        if resp.status_code >= 400:
            return f"Failed to add exclusion: {resp.text}"

    return f"Dismissed '{description_pattern}' — won't flag it again."


# ---------------------------------------------------------------------------
# Accept price change
# ---------------------------------------------------------------------------
async def accept_price_change(name: str, new_amount: float) -> str:
    """Accept a detected price change and update the stored amount."""
    return await update_subscription(name, amount=new_amount)


# ---------------------------------------------------------------------------
# List subscriptions (for conversational context)
# ---------------------------------------------------------------------------
async def list_subscriptions(
    scope: str | None = None,
    status: str | None = None,
) -> str:
    """List tracked subscriptions with summary."""
    params: dict[str, str] = {
        "select": "name,amount,frequency,scope,status,category",
        "order": "category.asc,name.asc",
    }
    if scope and scope != "all":
        params["scope"] = f"eq.{scope}"
    if status and status != "all":
        params["status"] = f"eq.{status}"

    rows = await finance_query("subscriptions", params, paginate=True)

    if not rows:
        return "No subscriptions found."

    multipliers = {
        "weekly": 52, "fortnightly": 26, "monthly": 12,
        "quarterly": 4, "termly": 3, "annual": 1,
    }

    active = [r for r in rows if r.get("status") == "active"]
    total_monthly = sum(
        float(r["amount"]) * multipliers.get(r["frequency"], 12) / 12
        for r in active
    )

    lines = [f"# Subscriptions ({len(active)} active, {len(rows)} total)", ""]

    current_cat = None
    for r in rows:
        cat = r.get("category") or "Uncategorised"
        if cat != current_cat:
            lines.append(f"\n## {cat}")
            current_cat = cat

        monthly = float(r["amount"]) * multipliers.get(r["frequency"], 12) / 12
        status_icon = {"active": "", "paused": " (paused)", "cancelled": " (cancelled)", "trial": " (trial)"}
        lines.append(
            f"- {r['name']}: {r['amount']}/{r['frequency']}"
            f" [{r['scope']}]{status_icon.get(r.get('status', ''), '')}"
        )

    lines.append(f"\n**Total monthly: {total_monthly:.2f}**")
    return "\n".join(lines)

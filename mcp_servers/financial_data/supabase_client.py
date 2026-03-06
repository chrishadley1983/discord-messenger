"""Async Supabase REST client supporting both finance and public schemas.

Uses httpx for async HTTP requests. All queries handle Supabase's 1,000-row
pagination limit internally.
"""

from __future__ import annotations

import httpx

from .config import SUPABASE_URL, API_KEY

# ---------------------------------------------------------------------------
# Shared HTTP client (lazy singleton)
# ---------------------------------------------------------------------------
_http_client: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=30,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _http_client


def _base_headers() -> dict[str, str]:
    if not API_KEY:
        raise RuntimeError("No Supabase key configured — set SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY")
    return {
        "apikey": API_KEY,
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


_REST = f"{SUPABASE_URL}/rest/v1"


# ---------------------------------------------------------------------------
# Schema-aware query helpers
# ---------------------------------------------------------------------------
async def finance_query(
    table: str,
    params: dict[str, str] | None = None,
    *,
    paginate: bool = False,
) -> list[dict]:
    """GET from finance schema table.  Set paginate=True to auto-fetch all rows."""
    headers = {**_base_headers(), "Accept-Profile": "finance"}
    return await _get(_REST, table, params or {}, headers, paginate)


async def finance_rpc(fn_name: str, body: dict | None = None) -> list[dict]:
    """Call an RPC in the finance schema."""
    headers = {**_base_headers(), "Content-Profile": "finance"}
    resp = await _client().post(f"{_REST}/rpc/{fn_name}", headers=headers, json=body or {})
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else [data] if data else []


async def public_query(
    table: str,
    params: dict[str, str] | None = None,
    *,
    paginate: bool = False,
) -> list[dict]:
    """GET from public schema table (default Supabase schema)."""
    headers = _base_headers()
    return await _get(_REST, table, params or {}, headers, paginate)


async def public_rpc(fn_name: str, body: dict | None = None) -> list[dict]:
    """Call an RPC in the public schema."""
    headers = _base_headers()
    resp = await _client().post(f"{_REST}/rpc/{fn_name}", headers=headers, json=body or {})
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else [data] if data else []


async def finance_count(table: str, params: dict[str, str] | None = None) -> int:
    """Return exact count of matching rows in finance schema."""
    headers = {**_base_headers(), "Accept-Profile": "finance", "Prefer": "count=exact"}
    return await _count(_REST, table, params or {}, headers)


async def public_count(table: str, params: dict[str, str] | None = None) -> int:
    """Return exact count of matching rows in public schema."""
    headers = {**_base_headers(), "Prefer": "count=exact"}
    return await _count(_REST, table, params or {}, headers)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
_PAGE_SIZE = 1000


async def _get(
    base: str,
    table: str,
    params: dict[str, str],
    headers: dict[str, str],
    paginate: bool,
) -> list[dict]:
    """GET with optional auto-pagination."""
    if not paginate:
        resp = await _client().get(f"{base}/{table}", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    all_rows: list[dict] = []
    offset = 0
    while True:
        page_params = {**params, "limit": str(_PAGE_SIZE), "offset": str(offset)}
        resp = await _client().get(f"{base}/{table}", params=page_params, headers=headers)
        resp.raise_for_status()
        batch = resp.json()
        all_rows.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return all_rows


async def _count(
    base: str,
    table: str,
    params: dict[str, str],
    headers: dict[str, str],
) -> int:
    """Return exact count via Prefer: count=exact header."""
    p = {**params, "limit": "0"}
    resp = await _client().get(f"{base}/{table}", params=p, headers=headers)
    resp.raise_for_status()
    cr = resp.headers.get("content-range", "0-0/0")
    return int(cr.split("/")[-1])

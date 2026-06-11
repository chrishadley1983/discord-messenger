"""Octopus Kraken GraphQL client with cached JWT auth.

Kraken tokens last ~1 hour; this module caches one and refreshes on expiry
or on an auth error. All GraphQL access (telemetry, dispatches, billing)
goes through gql().
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from logger import logger
from .config import OCTOPUS_API_KEY, OCTOPUS_GRAPHQL_URL

_TOKEN: str | None = None
_TOKEN_OBTAINED: float = 0.0
TOKEN_TTL_SECS = 50 * 60  # refresh before the ~60 min expiry


def _obtain_token() -> str:
    resp = httpx.post(
        OCTOPUS_GRAPHQL_URL,
        json={
            "query": "mutation($key: String!) { obtainKrakenToken(input: {APIKey: $key}) { token } }",
            "variables": {"key": OCTOPUS_API_KEY},
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = (resp.json().get("data") or {}).get("obtainKrakenToken", {}).get("token")
    if not token:
        raise RuntimeError(f"obtainKrakenToken failed: {str(resp.json())[:200]}")
    return token


def get_token(force: bool = False) -> str:
    global _TOKEN, _TOKEN_OBTAINED
    if force or not _TOKEN or time.time() - _TOKEN_OBTAINED > TOKEN_TTL_SECS:
        _TOKEN = _obtain_token()
        _TOKEN_OBTAINED = time.time()
    return _TOKEN


def gql(query: str, variables: dict | None = None) -> dict[str, Any]:
    """Run a GraphQL query; one retry with a fresh token on auth failure."""
    for attempt in (1, 2):
        resp = httpx.post(
            OCTOPUS_GRAPHQL_URL,
            headers={"Authorization": get_token(force=attempt == 2)},
            json={"query": query, "variables": variables or {}},
            timeout=30,
        )
        body = resp.json()
        errors = body.get("errors") or []
        auth_error = any(
            "KT-CT-1124" in str(e) or "expired" in str(e).lower() or "auth" in str(e).lower()
            for e in errors
        )
        if errors and auth_error and attempt == 1:
            logger.debug("Kraken token rejected — refreshing")
            continue
        if errors:
            raise RuntimeError(f"Kraken GraphQL error: {str(errors)[:300]}")
        return body.get("data") or {}
    return {}

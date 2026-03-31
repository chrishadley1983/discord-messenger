"""Shared API key authentication for Hadley API.

Checks the `x-api-key` header against the HADLEY_AUTH_KEY env var.
Use as a FastAPI dependency on any mutating endpoint that should not
be publicly accessible on the LAN.
"""

import os
from fastapi import Header, HTTPException


def require_auth(x_api_key: str = Header(default="")):
    """FastAPI dependency — raises 401 if the API key is missing or wrong."""
    auth_key = os.getenv("HADLEY_AUTH_KEY", "")
    if not auth_key:
        raise HTTPException(
            status_code=503,
            detail="HADLEY_AUTH_KEY not configured — refusing to serve without auth",
        )
    if x_api_key != auth_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

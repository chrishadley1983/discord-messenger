"""Shared Supabase/PostgREST helpers for accountability domain."""

import os

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def headers(*, returning: bool = False) -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    h["Prefer"] = "return=representation" if returning else "return=minimal"
    return h


def read_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }


def table_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"

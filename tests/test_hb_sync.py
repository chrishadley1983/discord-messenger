"""Tests for hadley_api.hb_sync — the fire-and-forget HB full-sync trigger.

Pure-helper tests import only hb_sync. The proxy-routing tests import the app
(like tests/accountability/test_api_routes.py does) and stub the runner so no
HTTP call to localhost:3000 is made.
"""

import asyncio
import os
from unittest.mock import patch

import httpx
import pytest

from hadley_api import hb_sync


@pytest.fixture(autouse=True)
def _reset_state():
    """Every test starts from a fresh 'never run' state."""
    hb_sync._state.update(
        running=False, started_at=None, finished_at=None, http_status=None,
        ok=None, error=None, summary=None, runs=0,
    )
    hb_sync._task = None
    yield
    hb_sync._task = None


# ── alias matching ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "sync/trigger", "/sync/trigger/", "SYNC/TRIGGER", "orders/refresh",
    "orders/sync", "sync/amazon", "workflow/sync-all", "cron/full-sync", "refresh",
])
def test_trigger_aliases_cover_peters_guesses(path):
    assert hb_sync.is_trigger(path)


@pytest.mark.parametrize("path", [
    "orders", "orders/123", "orders/amazon", "picking-list/amazon", "sync/status",
    "sync/inventory_items", "minifigs/sync/removals", "",
])
def test_non_sync_paths_are_not_triggers(path):
    assert not hb_sync.is_trigger(path)


def test_status_alias():
    assert hb_sync.is_status("sync/status")
    assert hb_sync.is_status("/sync/status/")
    assert not hb_sync.is_status("sync/trigger")


# ── secret resolution ──────────────────────────────────────────────────────

def test_cron_secret_prefers_env(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text('CRON_SECRET="from-file"\n')
    with patch.dict(os.environ, {"CRON_SECRET": "from-env"}):
        assert hb_sync.cron_secret(env_file) == "from-env"


def test_cron_secret_parses_env_local_and_strips_quotes(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text('OTHER=1\nCRON_SECRET="abc=123"\nMORE=2\n')
    with patch.dict(os.environ, {"CRON_SECRET": ""}):
        assert hb_sync.cron_secret(env_file) == "abc=123"


def test_cron_secret_missing_everywhere(tmp_path):
    with patch.dict(os.environ, {"CRON_SECRET": ""}):
        assert hb_sync.cron_secret(tmp_path / "nope") == ""


# ── trigger / dedupe ───────────────────────────────────────────────────────

async def test_trigger_without_secret_is_503():
    with patch.dict(os.environ, {"CRON_SECRET": ""}):
        with patch.object(hb_sync, "HB_ENV_LOCAL", hb_sync.Path("/definitely/missing")):
            code, body = hb_sync.trigger("http://hb")
    assert code == 503
    assert body["accepted"] is False
    assert hb_sync._task is None


async def test_trigger_starts_background_run_and_dedupes():
    release = asyncio.Event()
    calls = []

    async def fake_runner(base_url, secret):
        calls.append((base_url, secret))
        hb_sync._state["running"] = True
        await release.wait()
        hb_sync._state["running"] = False

    code, body = hb_sync.trigger("http://hb", secret="s3cret", runner=fake_runner)
    assert code == 202 and body["accepted"] and body["already_running"] is False
    assert body["poll"] == "/hb/sync/status"
    await asyncio.sleep(0)  # let the task start

    code2, body2 = hb_sync.trigger("http://hb", secret="s3cret", runner=fake_runner)
    assert code2 == 202 and body2["already_running"] is True
    assert calls == [("http://hb", "s3cret")], "second trigger must not start a second run"

    release.set()
    await hb_sync._task
    assert hb_sync._state["running"] is False

    # once finished, a new trigger starts a fresh run
    code3, body3 = hb_sync.trigger("http://hb", secret="s3cret", runner=fake_runner)
    assert code3 == 202 and body3["already_running"] is False
    release.set()
    await hb_sync._task


# ── run_full_sync outcome recording ────────────────────────────────────────

def _mock_transport(handler):
    return httpx.MockTransport(handler)


async def test_run_full_sync_records_success(monkeypatch):
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={
            "success": True, "duration": 1234,
            "orders": {"amazon": {"status": "COMPLETED", "processed": 3, "created": 1,
                                   "updated": 2, "latestDataDate": "x", "huge": [1] * 50}},
            "blob": {"lots": "of stuff"},
        })

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: real_client(transport=_mock_transport(handler), **kw),
    )
    await hb_sync.run_full_sync("http://hb/", "tok")

    assert seen["url"] == "http://hb/api/cron/full-sync"
    assert seen["auth"] == "Bearer tok"
    st = hb_sync.status()
    assert st["running"] is False and st["ok"] is True and st["http_status"] == 200
    assert st["runs"] == 1
    assert st["summary"]["orders"]["amazon"] == {
        "status": "COMPLETED", "processed": 3, "created": 1, "updated": 2,
    }
    assert "blob" not in st["summary"]
    assert st["finished_at"] and st["started_at"]


async def test_run_full_sync_records_401_as_failure(monkeypatch):
    def handler(request):
        return httpx.Response(401, json={"error": "Unauthorized"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: real_client(transport=_mock_transport(handler), **kw),
    )
    await hb_sync.run_full_sync("http://hb", "bad")
    st = hb_sync.status()
    assert st["ok"] is False and st["http_status"] == 401
    assert "401" in st["error"]
    assert st["running"] is False


async def test_run_full_sync_survives_connect_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: real_client(transport=_mock_transport(handler), **kw),
    )
    await hb_sync.run_full_sync("http://hb", "tok")  # must not raise
    st = hb_sync.status()
    assert st["ok"] is False and "not running" in st["error"]
    assert st["running"] is False


# ── proxy routing through the real FastAPI app ─────────────────────────────

@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    with patch.dict(os.environ, {"HADLEY_AUTH_KEY": "test-key"}):
        from hadley_api.main import app
        with TestClient(app) as c:
            yield c


def test_proxy_routes_trigger_aliases_to_background_sync(client):
    started = []

    async def fake_runner(base_url, secret):
        started.append(base_url)

    with patch.object(hb_sync, "run_full_sync", fake_runner), \
         patch.object(hb_sync, "cron_secret", lambda *a, **k: "tok"):
        r = client.post("/hb/orders/refresh")
        assert r.status_code == 202, r.text
        assert r.json()["accepted"] is True
        r = client.get("/hb/sync/trigger")
        assert r.status_code == 202
    assert started, "background runner should have been scheduled"


def test_proxy_status_endpoint_returns_state(client):
    r = client.get("/hb/sync/status")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"running", "ok", "started_at", "finished_at", "summary", "poll"}
    assert body["running"] is False


def test_proxy_trigger_without_secret_is_503(client):
    with patch.object(hb_sync, "cron_secret", lambda *a, **k: ""):
        r = client.post("/hb/sync/trigger")
    assert r.status_code == 503
    assert r.json()["accepted"] is False

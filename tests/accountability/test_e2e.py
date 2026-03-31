"""End-to-end tests for the accountability tracker.

These tests hit the LIVE Hadley API and Supabase. They create, update,
and delete real data — using a unique test prefix to avoid collisions.
Each test class cleans up after itself.

Requirements:
  - Hadley API running on localhost:8100
  - HADLEY_AUTH_KEY set in .env
  - Supabase tables created
"""

import os
import pytest
import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE = "http://localhost:8100/accountability"
AUTH_KEY = os.getenv("HADLEY_AUTH_KEY", "")
HEADERS = {"x-api-key": AUTH_KEY}
TEST_PREFIX = "[TEST] "


def _api_url(path: str) -> str:
    return f"{API_BASE}{path}"


@pytest.fixture(scope="module")
def api_client():
    """Shared httpx client for the test module."""
    with httpx.Client(timeout=15, headers=HEADERS) as client:
        yield client


@pytest.fixture(scope="module")
def created_goal_ids():
    """Track goal IDs created during tests for cleanup."""
    ids = []
    yield ids
    # Cleanup: delete all test goals
    with httpx.Client(timeout=15, headers=HEADERS) as client:
        for gid in ids:
            try:
                client.delete(_api_url(f"/goals/{gid}"))
            except Exception:
                pass


# ── Connectivity Check ───────────────────────────────────────────────────

class TestConnectivity:
    """Verify the API is reachable before running the suite."""

    def test_api_reachable(self, api_client):
        resp = api_client.get("http://localhost:8100/time")
        assert resp.status_code == 200, "Hadley API is not running"

    def test_accountability_endpoint_exists(self, api_client):
        resp = api_client.get(_api_url("/goals"))
        assert resp.status_code == 200, f"Accountability endpoint not found: {resp.status_code}"


# ── Goal CRUD E2E ────────────────────────────────────────────────────────

class TestGoalCRUD:
    """Full lifecycle: create → read → update → delete."""

    def test_create_habit_goal(self, api_client, created_goal_ids):
        resp = api_client.post(_api_url("/goals"), json={
            "title": f"{TEST_PREFIX}E2E Steps Habit",
            "goal_type": "habit",
            "metric": "steps",
            "target_value": 10000,
            "category": "fitness",
            "direction": "up",
            "frequency": "daily",
        })
        assert resp.status_code == 200, f"Create failed: {resp.text}"
        data = resp.json()
        assert data["status"] == "created"
        assert data["goal"]["title"] == f"{TEST_PREFIX}E2E Steps Habit"
        created_goal_ids.append(data["goal"]["id"])

    def test_create_target_goal(self, api_client, created_goal_ids):
        resp = api_client.post(_api_url("/goals"), json={
            "title": f"{TEST_PREFIX}E2E Weight Target",
            "goal_type": "target",
            "metric": "kg",
            "target_value": 80,
            "start_value": 85,
            "category": "health",
            "direction": "down",
            "deadline": "2026-12-31",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["goal"]["goal_type"] == "target"
        assert data["goal"]["deadline"] == "2026-12-31"
        created_goal_ids.append(data["goal"]["id"])

    def test_list_goals_includes_created(self, api_client, created_goal_ids):
        resp = api_client.get(_api_url("/goals?status=active"))
        assert resp.status_code == 200
        data = resp.json()
        goal_ids = [g["id"] for g in data["goals"]]
        for gid in created_goal_ids:
            assert gid in goal_ids, f"Goal {gid} not in list"

    def test_get_single_goal(self, api_client, created_goal_ids):
        gid = created_goal_ids[0]
        resp = api_client.get(_api_url(f"/goals/{gid}"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == gid
        assert "computed" in data
        assert "milestones" in data
        assert "recent_progress" in data

    def test_update_goal_title(self, api_client, created_goal_ids):
        gid = created_goal_ids[0]
        resp = api_client.patch(_api_url(f"/goals/{gid}"), json={
            "title": f"{TEST_PREFIX}E2E Steps Updated",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

        # Verify the update
        resp2 = api_client.get(_api_url(f"/goals/{gid}"))
        assert resp2.json()["title"] == f"{TEST_PREFIX}E2E Steps Updated"

    def test_delete_goal(self, api_client, created_goal_ids):
        # Create a throwaway goal to delete
        resp = api_client.post(_api_url("/goals"), json={
            "title": f"{TEST_PREFIX}E2E To Delete",
            "goal_type": "habit",
            "metric": "count",
            "target_value": 1,
        })
        del_id = resp.json()["goal"]["id"]

        resp = api_client.delete(_api_url(f"/goals/{del_id}"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "abandoned"

        # Verify it's no longer in active list
        resp2 = api_client.get(_api_url("/goals?status=active"))
        active_ids = [g["id"] for g in resp2.json()["goals"]]
        assert del_id not in active_ids


# ── Progress Logging E2E ─────────────────────────────────────────────────

class TestProgressLogging:
    """Test logging progress and verifying it updates goal state."""

    @pytest.fixture(autouse=True)
    def _setup_goal(self, api_client, created_goal_ids):
        """Create a fresh goal for progress tests."""
        resp = api_client.post(_api_url("/goals"), json={
            "title": f"{TEST_PREFIX}E2E Progress Test",
            "goal_type": "habit",
            "metric": "steps",
            "target_value": 10000,
            "category": "fitness",
            "direction": "up",
            "frequency": "daily",
        })
        self.goal_id = resp.json()["goal"]["id"]
        created_goal_ids.append(self.goal_id)

    def test_log_progress_manual(self, api_client):
        resp = api_client.post(_api_url(f"/goals/{self.goal_id}/progress"), json={
            "value": 8500,
            "source": "manual",
            "note": "E2E test entry",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "logged"
        assert resp.json()["entry"]["value"] == 8500

    def test_log_progress_updates_current_value(self, api_client):
        # Log a value
        api_client.post(_api_url(f"/goals/{self.goal_id}/progress"), json={
            "value": 12000,
            "source": "manual",
        })

        # Check goal's current_value was updated
        resp = api_client.get(_api_url(f"/goals/{self.goal_id}"))
        assert resp.status_code == 200
        assert float(resp.json()["current_value"]) == 12000

    def test_log_progress_streak_increments(self, api_client):
        # Log a value above target
        api_client.post(_api_url(f"/goals/{self.goal_id}/progress"), json={
            "value": 11000,
            "source": "peter_chat",
        })

        resp = api_client.get(_api_url(f"/goals/{self.goal_id}"))
        data = resp.json()
        # Should have streak >= 1
        assert data["current_streak"] >= 1

    def test_get_progress_history(self, api_client):
        # Log two entries
        api_client.post(_api_url(f"/goals/{self.goal_id}/progress"), json={
            "value": 9000, "source": "manual",
        })
        api_client.post(_api_url(f"/goals/{self.goal_id}/progress"), json={
            "value": 11000, "source": "peter_chat",
        })

        resp = api_client.get(_api_url(f"/goals/{self.goal_id}/progress?days=30"))
        assert resp.status_code == 200
        assert resp.json()["count"] >= 2


# ── Milestone E2E ────────────────────────────────────────────────────────

class TestMilestones:
    """Test milestone creation and listing."""

    @pytest.fixture(autouse=True)
    def _setup_goal(self, api_client, created_goal_ids):
        resp = api_client.post(_api_url("/goals"), json={
            "title": f"{TEST_PREFIX}E2E Milestone Test",
            "goal_type": "target",
            "metric": "gbp",
            "target_value": 5000,
            "start_value": 0,
            "category": "finance",
        })
        self.goal_id = resp.json()["goal"]["id"]
        created_goal_ids.append(self.goal_id)

    def test_create_milestone(self, api_client):
        resp = api_client.post(_api_url(f"/goals/{self.goal_id}/milestones"), json={
            "title": "First £1k",
            "target_value": 1000,
        })
        assert resp.status_code == 200
        assert resp.json()["milestone"]["title"] == "First £1k"

    def test_list_milestones(self, api_client):
        # Create two milestones
        api_client.post(_api_url(f"/goals/{self.goal_id}/milestones"), json={
            "title": "First £1k", "target_value": 1000,
        })
        api_client.post(_api_url(f"/goals/{self.goal_id}/milestones"), json={
            "title": "Half way", "target_value": 2500,
        })

        resp = api_client.get(_api_url(f"/goals/{self.goal_id}/milestones"))
        assert resp.status_code == 200
        assert resp.json()["count"] >= 2
        # Should be ordered by target_value
        milestones = resp.json()["milestones"]
        values = [float(m["target_value"]) for m in milestones]
        assert values == sorted(values)


# ── Summary & Reports E2E ────────────────────────────────────────────────

class TestSummaryAndReports:
    """Test the summary and report endpoints."""

    def test_summary_returns_goals(self, api_client):
        resp = api_client.get(_api_url("/summary"))
        assert resp.status_code == 200
        data = resp.json()
        assert "goals" in data
        assert "count" in data
        assert "date" in data

    def test_weekly_report(self, api_client):
        resp = api_client.get(_api_url("/report?period=week"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "week"
        assert data["days"] == 7
        assert "grade" in data
        assert "overall_score" in data

    def test_monthly_report(self, api_client):
        resp = api_client.get(_api_url("/report?period=month"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "month"
        assert data["days"] == 30


# ── Auto-Update E2E ──────────────────────────────────────────────────────

class TestAutoUpdate:
    """Test the auto-update trigger endpoint."""

    def test_auto_update_endpoint(self, api_client):
        resp = api_client.post(_api_url("/auto-update"))
        assert resp.status_code == 200
        data = resp.json()
        assert "updated" in data
        assert "skipped" in data
        assert "errors" in data
        assert "date" in data


# ── Computed Metrics E2E ─────────────────────────────────────────────────

class TestComputedMetrics:
    """Verify computed fields are returned correctly in API responses."""

    def test_goals_have_computed_field(self, api_client):
        resp = api_client.get(_api_url("/goals"))
        for goal in resp.json()["goals"]:
            assert "computed" in goal
            c = goal["computed"]
            assert "pct" in c
            assert "trend" in c

    def test_habit_goals_have_hit_rate(self, api_client):
        resp = api_client.get(_api_url("/goals"))
        habits = [g for g in resp.json()["goals"] if g["goal_type"] == "habit"]
        for h in habits:
            c = h["computed"]
            assert "hit_rate_7" in c

    def test_target_goals_have_on_track(self, api_client):
        resp = api_client.get(_api_url("/goals"))
        targets = [g for g in resp.json()["goals"] if g["goal_type"] == "target" and g.get("deadline")]
        for t in targets:
            c = t["computed"]
            assert "on_track" in c


# ── Edge Cases E2E ───────────────────────────────────────────────────────

class TestEdgeCases:
    """Test boundary conditions and error handling."""

    def test_get_nonexistent_goal(self, api_client):
        resp = api_client.get(_api_url("/goals/00000000-0000-0000-0000-000000000000"))
        assert resp.status_code == 404

    def test_create_goal_invalid_type(self, api_client):
        resp = api_client.post(_api_url("/goals"), json={
            "title": "Bad Goal",
            "goal_type": "invalid_type",
            "metric": "steps",
            "target_value": 100,
        })
        # Should fail at DB level since check constraint rejects 'invalid_type'
        assert resp.status_code == 500

    def test_create_goal_missing_required_fields(self, api_client):
        resp = api_client.post(_api_url("/goals"), json={
            "title": "Missing metric and target",
        })
        assert resp.status_code == 422  # Pydantic validation error

    def test_log_progress_to_nonexistent_goal(self, api_client):
        resp = api_client.post(
            _api_url("/goals/00000000-0000-0000-0000-000000000000/progress"),
            json={"value": 100}
        )
        # FK constraint should reject this
        assert resp.status_code == 500

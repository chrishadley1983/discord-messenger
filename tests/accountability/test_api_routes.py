"""Integration tests for the accountability API routes.

Tests the FastAPI endpoints via TestClient against mocked service layer.
"""

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


# ── Test client fixture ──────────────────────────────────────────────────

TEST_API_KEY = "test-accountability-key"


@pytest.fixture
def client():
    """Create a FastAPI TestClient with auth key set via env."""
    with patch.dict(os.environ, {"HADLEY_AUTH_KEY": TEST_API_KEY}):
        from hadley_api.main import app
        with TestClient(app) as c:
            yield c


@pytest.fixture
def auth_headers():
    return {"x-api-key": TEST_API_KEY}


MOCK_GOAL = {
    "id": "goal-001",
    "user_id": "chris",
    "title": "10k Steps",
    "goal_type": "habit",
    "category": "fitness",
    "metric": "steps",
    "current_value": 8000,
    "target_value": 10000,
    "start_value": 0,
    "direction": "up",
    "frequency": "daily",
    "start_date": "2026-03-01",
    "deadline": None,
    "status": "active",
    "completed_at": None,
    "current_streak": 3,
    "best_streak": 10,
    "last_hit_date": "2026-03-30",
    "auto_source": "garmin_steps",
    "auto_query": None,
    "created_at": "2026-03-01T00:00:00+00:00",
    "updated_at": "2026-03-30T00:00:00+00:00",
}


# ── GET /accountability/goals ────────────────────────────────────────────

class TestListGoals:

    def test_list_goals_returns_200(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.get_goals", new_callable=AsyncMock) as mock, \
             patch("hadley_api.accountability_routes.get_progress", new_callable=AsyncMock) as mock_prog, \
             patch("hadley_api.accountability_routes.compute_goal_status") as mock_compute:
            mock.return_value = [MOCK_GOAL]
            mock_prog.return_value = []
            mock_compute.return_value = {"pct": 80, "trend": "↑", "on_track": None,
                                          "current_streak": 3, "best_streak": 10,
                                          "hit_rate_7": {"hits": 5, "total": 7, "days": 7},
                                          "hit_rate_30": None}
            resp = client.get("/accountability/goals", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 1
            assert data["goals"][0]["computed"]["pct"] == 80

    def test_list_goals_empty(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.get_goals", new_callable=AsyncMock) as mock, \
             patch("hadley_api.accountability_routes.get_progress", new_callable=AsyncMock), \
             patch("hadley_api.accountability_routes.compute_goal_status"):
            mock.return_value = []
            resp = client.get("/accountability/goals", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["count"] == 0

    def test_list_goals_with_status_filter(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.get_goals", new_callable=AsyncMock) as mock, \
             patch("hadley_api.accountability_routes.get_progress", new_callable=AsyncMock), \
             patch("hadley_api.accountability_routes.compute_goal_status"):
            mock.return_value = []
            resp = client.get("/accountability/goals?status=completed", headers=auth_headers)
            assert resp.status_code == 200
            mock.assert_called_with(status="completed")


# ── POST /accountability/goals ───────────────────────────────────────────

class TestCreateGoal:

    def test_create_goal_success(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.create_goal", new_callable=AsyncMock) as mock:
            mock.return_value = MOCK_GOAL
            resp = client.post("/accountability/goals", headers=auth_headers, json={
                "title": "10k Steps",
                "goal_type": "habit",
                "metric": "steps",
                "target_value": 10000,
            })
            assert resp.status_code == 200
            assert resp.json()["status"] == "created"
            assert resp.json()["goal"]["title"] == "10k Steps"

    def test_create_goal_failure(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.create_goal", new_callable=AsyncMock) as mock:
            mock.return_value = None
            resp = client.post("/accountability/goals", headers=auth_headers, json={
                "title": "Bad Goal",
                "goal_type": "habit",
                "metric": "steps",
                "target_value": 10000,
            })
            assert resp.status_code == 500

    def test_create_goal_missing_fields(self, client, auth_headers):
        resp = client.post("/accountability/goals", headers=auth_headers, json={
            "title": "Missing fields",
        })
        assert resp.status_code == 422  # Validation error


# ── GET /accountability/goals/{id} ───────────────────────────────────────

class TestGetGoal:

    def test_get_goal_success(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.get_goal", new_callable=AsyncMock) as mock, \
             patch("hadley_api.accountability_routes.get_progress", new_callable=AsyncMock) as mock_prog, \
             patch("hadley_api.accountability_routes.compute_goal_status") as mock_compute, \
             patch("hadley_api.accountability_routes.get_milestones", new_callable=AsyncMock) as mock_ms:
            mock.return_value = MOCK_GOAL
            mock_prog.return_value = []
            mock_compute.return_value = {"pct": 80, "trend": "→", "on_track": None,
                                          "current_streak": 3, "best_streak": 10,
                                          "hit_rate_7": None, "hit_rate_30": None}
            mock_ms.return_value = []
            resp = client.get("/accountability/goals/goal-001", headers=auth_headers)
            assert resp.status_code == 200
            assert "milestones" in resp.json()
            assert "recent_progress" in resp.json()

    def test_get_goal_not_found(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.get_goal", new_callable=AsyncMock) as mock:
            mock.return_value = None
            resp = client.get("/accountability/goals/nonexistent", headers=auth_headers)
            assert resp.status_code == 404


# ── PATCH /accountability/goals/{id} ─────────────────────────────────────

class TestUpdateGoal:

    def test_update_goal_success(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.update_goal", new_callable=AsyncMock) as mock:
            mock.return_value = True
            resp = client.patch("/accountability/goals/goal-001", headers=auth_headers, json={
                "title": "Updated Title",
            })
            assert resp.status_code == 200
            assert resp.json()["status"] == "updated"

    def test_update_goal_no_changes(self, client, auth_headers):
        resp = client.patch("/accountability/goals/goal-001", headers=auth_headers, json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "no changes"


# ── DELETE /accountability/goals/{id} ────────────────────────────────────

class TestDeleteGoal:

    def test_delete_goal_success(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.delete_goal", new_callable=AsyncMock) as mock:
            mock.return_value = True
            resp = client.delete("/accountability/goals/goal-001", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["status"] == "abandoned"

    def test_delete_goal_failure(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.delete_goal", new_callable=AsyncMock) as mock:
            mock.return_value = False
            resp = client.delete("/accountability/goals/goal-001", headers=auth_headers)
            assert resp.status_code == 500


# ── POST /accountability/goals/{id}/progress ─────────────────────────────

class TestLogProgress:

    def test_log_progress_success(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.log_progress", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "p1", "value": 12000, "source": "manual"}
            resp = client.post("/accountability/goals/goal-001/progress", headers=auth_headers, json={
                "value": 12000,
                "note": "Great day!",
            })
            assert resp.status_code == 200
            assert resp.json()["status"] == "logged"

    def test_log_progress_failure(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.log_progress", new_callable=AsyncMock) as mock:
            mock.return_value = None
            resp = client.post("/accountability/goals/goal-001/progress", headers=auth_headers, json={
                "value": 12000,
            })
            assert resp.status_code == 500


# ── POST /accountability/goals/{id}/milestones ───────────────────────────

class TestCreateMilestone:

    def test_create_milestone_success(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.add_milestone", new_callable=AsyncMock) as mock:
            mock.return_value = {"id": "ms-1", "title": "First 5k", "target_value": 5000}
            resp = client.post("/accountability/goals/goal-001/milestones", headers=auth_headers, json={
                "title": "First 5k",
                "target_value": 5000,
            })
            assert resp.status_code == 200
            assert resp.json()["milestone"]["title"] == "First 5k"


# ── GET /accountability/summary ──────────────────────────────────────────

class TestSummary:

    def test_summary_returns_data(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.get_daily_summary", new_callable=AsyncMock) as mock:
            mock.return_value = {"goals": [], "count": 0, "date": "2026-03-31"}
            resp = client.get("/accountability/summary", headers=auth_headers)
            assert resp.status_code == 200
            assert "goals" in resp.json()


# ── GET /accountability/report ───────────────────────────────────────────

class TestReport:

    def test_weekly_report(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.get_report_data", new_callable=AsyncMock) as mock:
            mock.return_value = {"period": "week", "goals": [], "grade": "B+", "overall_score": 78}
            resp = client.get("/accountability/report?period=week", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["grade"] == "B+"

    def test_monthly_report(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.get_report_data", new_callable=AsyncMock) as mock:
            mock.return_value = {"period": "month", "goals": [], "grade": "A", "overall_score": 92}
            resp = client.get("/accountability/report?period=month", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["period"] == "month"


# ── POST /accountability/auto-update ─────────────────────────────────────

class TestAutoUpdate:

    def test_auto_update_trigger(self, client, auth_headers):
        with patch("hadley_api.accountability_routes.run_auto_updates", new_callable=AsyncMock) as mock:
            mock.return_value = {"updated": 2, "skipped": 1, "errors": [], "date": "2026-03-31"}
            resp = client.post("/accountability/auto-update", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["updated"] == 2

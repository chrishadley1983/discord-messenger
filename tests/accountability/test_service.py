"""Unit tests for the accountability service layer.

Tests all CRUD operations, computed metrics, streak tracking,
trend calculation, hit rates, and report generation.
All Supabase calls are mocked — no network required.
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock
import json

# ── Fixtures ─────────────────────────────────────────────────────────────

MOCK_GOAL_HABIT = {
    "id": "goal-steps-001",
    "user_id": "chris",
    "title": "10k Steps Daily",
    "description": None,
    "goal_type": "habit",
    "category": "fitness",
    "metric": "steps",
    "current_value": 8500,
    "target_value": 10000,
    "start_value": 0,
    "direction": "up",
    "frequency": "daily",
    "start_date": "2026-03-01",
    "deadline": None,
    "status": "active",
    "completed_at": None,
    "current_streak": 5,
    "best_streak": 12,
    "last_hit_date": "2026-03-30",
    "auto_source": "garmin_steps",
    "auto_query": None,
    "created_at": "2026-03-01T00:00:00+00:00",
    "updated_at": "2026-03-30T20:00:00+00:00",
}

MOCK_GOAL_TARGET = {
    "id": "goal-weight-001",
    "user_id": "chris",
    "title": "Hit 80kg",
    "description": None,
    "goal_type": "target",
    "category": "health",
    "metric": "kg",
    "current_value": 82,
    "target_value": 80,
    "start_value": 84,
    "direction": "down",
    "frequency": None,
    "start_date": "2026-03-01",
    "deadline": "2026-06-30",
    "status": "active",
    "completed_at": None,
    "current_streak": 0,
    "best_streak": 0,
    "last_hit_date": None,
    "auto_source": "weight",
    "auto_query": None,
    "created_at": "2026-03-01T00:00:00+00:00",
    "updated_at": "2026-03-30T20:00:00+00:00",
}


def _make_progress(days_back, values):
    """Generate mock progress entries going back N days."""
    today = date.today()
    entries = []
    for i, v in enumerate(values):
        d = today - timedelta(days=days_back - i)
        entries.append({
            "id": f"prog-{i}",
            "goal_id": "goal-steps-001",
            "value": v,
            "delta": v - values[i - 1] if i > 0 else None,
            "note": None,
            "source": "garmin",
            "logged_at": f"{d}T20:00:00+00:00",
            "date": d.isoformat(),
        })
    return entries


# ── compute_goal_status tests ────────────────────────────────────────────

class TestComputeGoalStatus:
    """Tests for the compute_goal_status function."""

    def test_habit_pct_above_target(self):
        from domains.accountability.service import compute_goal_status
        goal = {**MOCK_GOAL_HABIT, "current_value": 12000}
        result = compute_goal_status(goal, [])
        assert result["pct"] == 100.0  # Capped at 100

    def test_habit_pct_below_target(self):
        from domains.accountability.service import compute_goal_status
        goal = {**MOCK_GOAL_HABIT, "current_value": 5000}
        result = compute_goal_status(goal, [])
        assert result["pct"] == 50.0

    def test_habit_pct_zero(self):
        from domains.accountability.service import compute_goal_status
        goal = {**MOCK_GOAL_HABIT, "current_value": 0}
        result = compute_goal_status(goal, [])
        assert result["pct"] == 0.0

    def test_target_pct_direction_down(self):
        from domains.accountability.service import compute_goal_status
        goal = {**MOCK_GOAL_TARGET, "current_value": 82}
        # start=84, target=80, current=82 → (84-82)/(84-80) = 50%
        result = compute_goal_status(goal, [])
        assert result["pct"] == 50.0

    def test_target_pct_direction_up(self):
        from domains.accountability.service import compute_goal_status
        goal = {
            **MOCK_GOAL_TARGET,
            "direction": "up",
            "start_value": 0,
            "target_value": 5000,
            "current_value": 2500,
        }
        result = compute_goal_status(goal, [])
        assert result["pct"] == 50.0

    def test_target_complete(self):
        from domains.accountability.service import compute_goal_status
        goal = {**MOCK_GOAL_TARGET, "current_value": 79}
        result = compute_goal_status(goal, [])
        assert result["pct"] == 100.0

    def test_on_track_score_present_for_targets(self):
        from domains.accountability.service import compute_goal_status
        goal = {**MOCK_GOAL_TARGET}
        result = compute_goal_status(goal, [])
        assert result["on_track"] is not None

    def test_on_track_score_none_for_habits(self):
        from domains.accountability.service import compute_goal_status
        result = compute_goal_status(MOCK_GOAL_HABIT, [])
        assert result["on_track"] is None

    def test_streak_returned(self):
        from domains.accountability.service import compute_goal_status
        result = compute_goal_status(MOCK_GOAL_HABIT, [])
        assert result["current_streak"] == 5
        assert result["best_streak"] == 12

    def test_hit_rate_7_for_habits(self):
        from domains.accountability.service import compute_goal_status
        progress = _make_progress(7, [12000, 8000, 11000, 9500, 10500, 7000, 13000])
        result = compute_goal_status(MOCK_GOAL_HABIT, progress)
        hr = result["hit_rate_7"]
        assert hr is not None
        assert hr["days"] == 7
        # values >= 10000: 12000, 11000, 10500, 13000 = 4 hits
        assert hr["hits"] == 4

    def test_hit_rate_none_for_targets(self):
        from domains.accountability.service import compute_goal_status
        result = compute_goal_status(MOCK_GOAL_TARGET, [])
        assert result["hit_rate_7"] is None
        assert result["hit_rate_30"] is None


class TestComputeTrend:
    """Tests for _compute_trend."""

    def test_trend_up(self):
        from domains.accountability.service import _compute_trend
        today = date.today()
        progress = [
            {"value": 12000, "date": (today - timedelta(days=i)).isoformat()}
            for i in range(7)
        ] + [
            {"value": 8000, "date": (today - timedelta(days=7 + i)).isoformat()}
            for i in range(7)
        ]
        assert _compute_trend(progress) == "↑"

    def test_trend_down(self):
        from domains.accountability.service import _compute_trend
        today = date.today()
        progress = [
            {"value": 5000, "date": (today - timedelta(days=i)).isoformat()}
            for i in range(7)
        ] + [
            {"value": 12000, "date": (today - timedelta(days=7 + i)).isoformat()}
            for i in range(7)
        ]
        assert _compute_trend(progress) == "↓"

    def test_trend_flat(self):
        from domains.accountability.service import _compute_trend
        today = date.today()
        progress = [
            {"value": 10000, "date": (today - timedelta(days=i)).isoformat()}
            for i in range(14)
        ]
        assert _compute_trend(progress) == "→"

    def test_trend_no_data(self):
        from domains.accountability.service import _compute_trend
        assert _compute_trend([]) == "→"


class TestScoreToGrade:
    """Tests for _score_to_grade."""

    def test_a_grade(self):
        from domains.accountability.service import _score_to_grade
        assert _score_to_grade(95) == "A"

    def test_b_plus_grade(self):
        from domains.accountability.service import _score_to_grade
        assert _score_to_grade(85) == "B+"

    def test_b_grade(self):
        from domains.accountability.service import _score_to_grade
        assert _score_to_grade(75) == "B"

    def test_c_grade(self):
        from domains.accountability.service import _score_to_grade
        assert _score_to_grade(55) == "C"

    def test_f_grade(self):
        from domains.accountability.service import _score_to_grade
        assert _score_to_grade(30) == "F"


class TestHitRate:
    """Tests for _compute_hit_rate."""

    def test_all_hits(self):
        from domains.accountability.service import _compute_hit_rate
        today = date.today()
        progress = [
            {"value": 12000, "date": (today - timedelta(days=i)).isoformat()}
            for i in range(7)
        ]
        result = _compute_hit_rate(progress, 10000, "up", 7)
        assert result["hits"] == 7

    def test_no_hits(self):
        from domains.accountability.service import _compute_hit_rate
        today = date.today()
        progress = [
            {"value": 5000, "date": (today - timedelta(days=i)).isoformat()}
            for i in range(7)
        ]
        result = _compute_hit_rate(progress, 10000, "up", 7)
        assert result["hits"] == 0

    def test_direction_down(self):
        from domains.accountability.service import _compute_hit_rate
        today = date.today()
        progress = [
            {"value": 78, "date": (today - timedelta(days=i)).isoformat()}
            for i in range(7)
        ]
        result = _compute_hit_rate(progress, 80, "down", 7)
        assert result["hits"] == 7  # All below 80

    def test_empty_progress(self):
        from domains.accountability.service import _compute_hit_rate
        result = _compute_hit_rate([], 10000, "up", 7)
        assert result["hits"] == 0
        assert result["total"] == 7  # Days with no entry count as misses


# ── CRUD operation tests (mocked httpx) ──────────────────────────────────

class TestCreateGoal:
    """Tests for create_goal with mocked Supabase."""

    @pytest.mark.asyncio
    async def test_create_goal_success(self):
        from domains.accountability.service import create_goal
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = [MOCK_GOAL_HABIT]

        with patch("domains.accountability.service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
            result = await create_goal(
                title="10k Steps Daily",
                goal_type="habit",
                metric="steps",
                target_value=10000,
            )
            assert result is not None
            assert result["title"] == "10k Steps Daily"

    @pytest.mark.asyncio
    async def test_create_goal_failure(self):
        from domains.accountability.service import create_goal
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad request"

        with patch("domains.accountability.service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
            result = await create_goal(
                title="Bad Goal",
                goal_type="invalid",
                metric="steps",
                target_value=10000,
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_create_goal_with_all_fields(self):
        from domains.accountability.service import create_goal
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = [MOCK_GOAL_TARGET]

        with patch("domains.accountability.service.httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_resp)
            mock_client.return_value.__aenter__.return_value.post = mock_post
            await create_goal(
                title="Hit 80kg",
                goal_type="target",
                metric="kg",
                target_value=80,
                category="health",
                description="Weight loss goal",
                start_value=84,
                direction="down",
                deadline="2026-06-30",
                auto_source="weight",
            )
            # Verify the payload includes all fields
            call_kwargs = mock_post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["direction"] == "down"
            assert payload["deadline"] == "2026-06-30"
            assert payload["auto_source"] == "weight"


class TestGetGoals:
    """Tests for get_goals with mocked Supabase."""

    @pytest.mark.asyncio
    async def test_get_goals_active(self):
        from domains.accountability.service import get_goals
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [MOCK_GOAL_HABIT, MOCK_GOAL_TARGET]

        with patch("domains.accountability.service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            goals = await get_goals(status="active")
            assert len(goals) == 2

    @pytest.mark.asyncio
    async def test_get_goals_empty(self):
        from domains.accountability.service import get_goals
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []

        with patch("domains.accountability.service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            goals = await get_goals()
            assert goals == []

    @pytest.mark.asyncio
    async def test_get_goals_network_error(self):
        from domains.accountability.service import get_goals
        with patch("domains.accountability.service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=Exception("Network error"))
            goals = await get_goals()
            assert goals == []


class TestUpdateGoal:
    """Tests for update_goal."""

    @pytest.mark.asyncio
    async def test_update_success(self):
        from domains.accountability.service import update_goal
        mock_resp = MagicMock()
        mock_resp.status_code = 204

        with patch("domains.accountability.service.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.patch = AsyncMock(return_value=mock_resp)
            result = await update_goal("goal-001", status="paused")
            assert result is True

    @pytest.mark.asyncio
    async def test_update_no_fields(self):
        from domains.accountability.service import update_goal
        result = await update_goal("goal-001")
        assert result is True  # No-op returns True


class TestLogProgress:
    """Tests for log_progress."""

    @pytest.mark.asyncio
    async def test_log_progress_manual(self):
        from domains.accountability.service import log_progress
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = [{"id": "prog-001", "value": 12000, "source": "manual"}]

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = [{"value": 10000}]

        mock_goal_resp = MagicMock()
        mock_goal_resp.status_code = 200
        mock_goal_resp.json.return_value = [MOCK_GOAL_HABIT]

        mock_patch_resp = MagicMock()
        mock_patch_resp.status_code = 204

        mock_milestones_resp = MagicMock()
        mock_milestones_resp.status_code = 200
        mock_milestones_resp.json.return_value = []

        with patch("domains.accountability.service.httpx.AsyncClient") as mock_client:
            client = AsyncMock()
            # Return different responses for different calls
            client.get = AsyncMock(side_effect=[mock_get_resp, mock_goal_resp, mock_milestones_resp])
            client.post = AsyncMock(return_value=mock_post_resp)
            client.patch = AsyncMock(return_value=mock_patch_resp)
            mock_client.return_value.__aenter__.return_value = client

            result = await log_progress("goal-steps-001", 12000, source="manual", note="Great day!")
            assert result is not None


class TestCheckMilestones:
    """Tests for check_milestones."""

    @pytest.mark.asyncio
    async def test_milestone_reached_up(self):
        from domains.accountability.service import check_milestones
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = [
            {"id": "ms-1", "goal_id": "g1", "title": "First 5k", "target_value": 5000, "reached_at": None},
            {"id": "ms-2", "goal_id": "g1", "title": "10k!", "target_value": 10000, "reached_at": None},
        ]
        mock_patch_resp = MagicMock()
        mock_patch_resp.status_code = 204

        with patch("domains.accountability.service.httpx.AsyncClient") as mock_client:
            client = AsyncMock()
            client.get = AsyncMock(return_value=mock_get_resp)
            client.patch = AsyncMock(return_value=mock_patch_resp)
            mock_client.return_value.__aenter__.return_value = client

            newly = await check_milestones("g1", 7000, direction="up")
            # 7000 >= 5000 but not >= 10000
            assert len(newly) == 1
            assert newly[0]["title"] == "First 5k"

    @pytest.mark.asyncio
    async def test_milestone_reached_down(self):
        from domains.accountability.service import check_milestones
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = [
            {"id": "ms-1", "goal_id": "g1", "title": "Under 82kg", "target_value": 82, "reached_at": None},
        ]
        mock_patch_resp = MagicMock()
        mock_patch_resp.status_code = 204

        with patch("domains.accountability.service.httpx.AsyncClient") as mock_client:
            client = AsyncMock()
            client.get = AsyncMock(return_value=mock_get_resp)
            client.patch = AsyncMock(return_value=mock_patch_resp)
            mock_client.return_value.__aenter__.return_value = client

            newly = await check_milestones("g1", 81.5, direction="down")
            assert len(newly) == 1

    @pytest.mark.asyncio
    async def test_already_reached_skipped(self):
        from domains.accountability.service import check_milestones
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = [
            {"id": "ms-1", "goal_id": "g1", "title": "Already done", "target_value": 5000, "reached_at": "2026-03-20T00:00:00Z"},
        ]

        with patch("domains.accountability.service.httpx.AsyncClient") as mock_client:
            client = AsyncMock()
            client.get = AsyncMock(return_value=mock_get_resp)
            mock_client.return_value.__aenter__.return_value = client

            newly = await check_milestones("g1", 10000, direction="up")
            assert len(newly) == 0

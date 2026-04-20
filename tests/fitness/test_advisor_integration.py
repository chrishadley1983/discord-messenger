"""Integration tests for the fitness advisor.

Tests the snapshot builder (mocked I/O), the API endpoint (TestClient),
and the full get_advice() pipeline.
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import date, datetime
from zoneinfo import ZoneInfo

from domains.fitness.advisor import (
    Snapshot, build_snapshot, get_advice, evaluate_rules,
)

UK_TZ = ZoneInfo("Europe/London")

MOCK_PROGRAMME = {
    "id": "prog-1",
    "start_date": "2026-04-20",
    "end_date": "2026-07-19",
    "start_weight_kg": 90.0,
    "target_weight_kg": 80.0,
    "duration_weeks": 13,
    "split": "4x_upper_lower",
    "daily_calorie_target": 2343,
    "daily_protein_g": 150,
    "daily_steps_target": 15000,
    "weekly_strength_sessions": 4,
    "tdee_kcal": 2893,
    "deficit_kcal": 550,
    "status": "active",
}

MOCK_WEIGHT_HISTORY = [
    {"date": "2026-04-25", "value": 89.5},
    {"date": "2026-04-26", "value": 89.3},
    {"date": "2026-04-27", "value": 89.1},
    {"date": "2026-04-28", "value": 88.9},
    {"date": "2026-04-29", "value": 88.7},
    {"date": "2026-04-30", "value": 88.5},
    {"date": "2026-05-01", "value": 88.3},
]

MOCK_NUTRITION = {
    "calories": 1800.0,
    "protein_g": 120.0,
    "carbs_g": 200.0,
    "fat_g": 60.0,
    "water_ml": 2000.0,
}

MOCK_STEPS = [
    {"date": "2026-04-25", "value": 14000},
    {"date": "2026-04-26", "value": 13500},
    {"date": "2026-04-27", "value": 15200},
    {"date": "2026-04-28", "value": 12000},
    {"date": "2026-04-29", "value": 14500},
    {"date": "2026-04-30", "value": 13000},
    {"date": "2026-05-01", "value": 11000},
]

MOCK_GARMIN_ROWS = [
    {
        "date": "2026-05-01",
        "resting_hr": 60,
        "sleep_hours": 7.5,
        "sleep_score": 75,
        "hrv_weekly_avg": 45,
        "hrv_last_night": 42,
        "hrv_status": "BALANCED",
        "avg_stress": 30,
    },
    {"date": "2026-04-30", "resting_hr": 59, "sleep_hours": 7.0, "sleep_score": 70,
     "hrv_weekly_avg": 44, "hrv_last_night": 40, "hrv_status": "BALANCED", "avg_stress": 35},
    {"date": "2026-04-29", "resting_hr": 58, "sleep_hours": 8.0, "sleep_score": 82,
     "hrv_weekly_avg": 46, "hrv_last_night": 45, "hrv_status": "BALANCED", "avg_stress": 28},
]


def _mock_httpx_response(json_data, status_code=200):
    resp = Mock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.raise_for_status = Mock()
    return resp


def _mock_trend():
    from domains.fitness.trend import TrendResult
    return TrendResult(
        readings_count=7,
        latest_raw=88.3,
        trend_7d=88.5,
        trend_ema=88.4,
        slope_kg_per_week=-0.7,
        stalled=False,
        message="Losing steadily",
    )


class _MockSession:
    def __init__(self, day_of_week, session_type):
        self.day_of_week = day_of_week
        self.session_type = session_type


# ── Snapshot builder tests ───────────────────────────────────────────


class TestBuildSnapshot:
    @pytest.mark.asyncio
    async def test_builds_with_active_programme(self):
        """Full snapshot build with all service calls mocked at source."""
        with (
            patch("domains.fitness.service.get_active_programme", new_callable=AsyncMock, return_value=MOCK_PROGRAMME) as mock_prog,
            patch("domains.fitness.service.week_number", return_value=2),
            patch("domains.fitness.service.fetch_weight_history", new_callable=AsyncMock, return_value=MOCK_WEIGHT_HISTORY),
            patch("domains.fitness.service.fetch_nutrition_today", new_callable=AsyncMock, return_value=MOCK_NUTRITION),
            patch("domains.fitness.service.fetch_steps_history", new_callable=AsyncMock, return_value=MOCK_STEPS),
            patch("domains.fitness.service.count_sessions_this_week", new_callable=AsyncMock, return_value=3),
            patch("domains.fitness.service.get_sessions_in_range", new_callable=AsyncMock, return_value=[
                {"rpe": 7, "session_type": "push"},
                {"rpe": 6, "session_type": "pull"},
            ]),
            patch("domains.fitness.service.mobility_today", new_callable=AsyncMock, return_value={"morning": True, "evening": False}),
            patch("domains.fitness.service.compute_current_targets", return_value=Mock(
                target_calories=2343, target_protein_g=150, bmr=1808, tdee=2893
            )),
            patch("domains.fitness.service._today", return_value=date(2026, 5, 1)),
            patch("domains.fitness.trend.compute_trend", return_value=_mock_trend()),
            patch("domains.fitness.programme_generator.generate_week", return_value=[
                _MockSession(0, "push"),
                _MockSession(2, "pull"),
                _MockSession(3, "legs"),
            ]),
            patch("httpx.AsyncClient") as mock_httpx_cls,
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=[
                _mock_httpx_response(MOCK_GARMIN_ROWS),
                _mock_httpx_response([
                    {"session_date": "2026-05-01"},
                    {"session_date": "2026-04-30"},
                    {"session_date": "2026-04-29"},
                ]),
                _mock_httpx_response([
                    {"logged_at": "2026-04-28T12:00:00", "calories": 2300, "protein_g": 140},
                    {"logged_at": "2026-04-29T12:00:00", "calories": 2100, "protein_g": 150},
                ]),
            ])
            mock_httpx_cls.return_value.__aenter__.return_value = mock_client

            snap = await build_snapshot()

            assert snap.programme_active is True
            assert snap.week_no == 2
            assert snap.calories_eaten == 1800.0
            assert snap.protein_eaten == 120.0
            assert snap.current_weight_kg == pytest.approx(88.5, abs=0.1)
            assert snap.calories_target == 2343
            assert snap.strength_sessions_week == 3
            assert snap.sleep_score == 75
            assert snap.resting_hr == 60
            assert snap.hrv_status == "BALANCED"
            assert len(snap.resting_hr_5d) == 3

    @pytest.mark.asyncio
    async def test_builds_without_programme(self):
        with patch("domains.fitness.service.get_active_programme", new_callable=AsyncMock, return_value=None):
            snap = await build_snapshot()

            assert snap.programme_active is False
            assert snap.week_no == 0
            assert snap.calories_target == 0


# ── get_advice() pipeline tests ──────────────────────────────────────


class TestGetAdvice:
    @pytest.mark.asyncio
    async def test_returns_structured_output(self):
        with patch("domains.fitness.advisor.build_snapshot") as mock_build:
            mock_build.return_value = Snapshot(
                programme_active=True,
                week_no=3,
                calories_eaten=2300,
                calories_target=2343,
                protein_eaten=145,
                protein_target=150,
                steps_today=14000,
                steps_target=15000,
                current_weight_kg=88.0,
                slope_kg_per_week=-0.7,
                hour_of_day=21,
                sleep_score=85,
                sleep_hours=8.0,
                mobility_streak=7,
            )

            result = await get_advice()

            assert "advice" in result
            assert "snapshot" in result
            assert "counts" in result
            assert isinstance(result["advice"], list)
            assert result["counts"]["total"] == len(result["advice"])

            for item in result["advice"]:
                assert "severity" in item
                assert "headline" in item
                assert "detail" in item
                assert "action" in item
                assert "category" in item

    @pytest.mark.asyncio
    async def test_snapshot_summary_fields(self):
        with patch("domains.fitness.advisor.build_snapshot") as mock_build:
            mock_build.return_value = Snapshot(
                programme_active=True,
                week_no=3,
                day_no=18,
                is_training_day=True,
                session_type="push",
                calories_eaten=2000,
                calories_target=2343,
                protein_eaten=120,
                protein_target=150,
                steps_today=12000,
                steps_target=15000,
                current_weight_kg=88.0,
                slope_kg_per_week=-0.7,
                sleep_score=75,
                resting_hr=60,
                hrv_status="BALANCED",
                mobility_streak=5,
                strength_sessions_week=3,
                strength_target=4,
            )

            result = await get_advice()
            snap = result["snapshot"]

            assert snap["programme_active"] is True
            assert snap["week_no"] == 3
            assert snap["calories"]["eaten"] == 2000
            assert snap["calories"]["target"] == 2343
            assert snap["protein"]["eaten"] == 120
            assert snap["protein"]["target"] == 150
            assert snap["weight_kg"] == 88.0
            assert snap["sleep_score"] == 75
            assert snap["hrv_status"] == "BALANCED"

    @pytest.mark.asyncio
    async def test_severity_counts(self):
        with patch("domains.fitness.advisor.build_snapshot") as mock_build:
            mock_build.return_value = Snapshot(
                programme_active=True,
                calories_eaten=1200,
                calories_target=2343,
                protein_eaten=60,
                protein_target=150,
                hour_of_day=17,
                sleep_score=85,
                sleep_hours=8.0,
                mobility_streak=10,
                current_weight_kg=88.0,
            )

            result = await get_advice()
            counts = result["counts"]

            assert counts["warning"] >= 1
            assert counts["total"] == sum(
                counts[s] for s in ("warning", "caution", "info", "positive")
            )


# ── API endpoint tests ───────────────────────────────────────────────


class TestFitnessAdviceEndpoint:
    @pytest.fixture
    def client(self):
        with patch.dict(os.environ, {"HADLEY_AUTH_KEY": "test-key"}):
            from fastapi import FastAPI
            from starlette.testclient import TestClient
            from hadley_api.fitness_routes import router
            app = FastAPI()
            app.include_router(router)
            with TestClient(app) as c:
                yield c

    def test_get_advice_200(self, client):
        with patch("hadley_api.fitness_routes.get_advice", new_callable=AsyncMock) as mock_advice:
            mock_advice.return_value = {
                "advice": [
                    {
                        "severity": "caution",
                        "category": "nutrition",
                        "headline": "Behind on protein",
                        "detail": "110g of 150g",
                        "action": "Add a shake",
                    }
                ],
                "snapshot": {"programme_active": True},
                "counts": {"warning": 0, "caution": 1, "info": 0, "positive": 0, "total": 1},
            }

            resp = client.get("/fitness/advice")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["advice"]) == 1
            assert data["advice"][0]["severity"] == "caution"
            assert data["counts"]["total"] == 1

    def test_get_advice_empty(self, client):
        with patch("hadley_api.fitness_routes.get_advice", new_callable=AsyncMock) as mock_advice:
            mock_advice.return_value = {
                "advice": [],
                "snapshot": {"programme_active": False},
                "counts": {"warning": 0, "caution": 0, "info": 0, "positive": 0, "total": 0},
            }

            resp = client.get("/fitness/advice")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["advice"]) == 0
            assert data["counts"]["total"] == 0


# ── Garmin HRV sync tests ───────────────────────────────────────────


class TestGarminHrvSync:
    @pytest.mark.asyncio
    async def test_sync_includes_hrv_fields(self):
        """Verify _sync_garmin_to_supabase persists HRV + stress fields."""
        import importlib

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_resp = Mock(status_code=201, text="ok")
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value.__aenter__.return_value = mock_client

            # Import after mocking to ensure config module loads
            with (
                patch.dict(os.environ, {"SUPABASE_URL": "https://test.co", "SUPABASE_KEY": "k"}),
            ):
                # Re-import to pick up env vars
                import config as cfg_mod
                with (
                    patch.object(cfg_mod, "SUPABASE_URL", "https://test.co", create=True),
                    patch.object(cfg_mod, "SUPABASE_KEY", "k", create=True),
                ):
                    from domains.peterbot.data_fetchers import _sync_garmin_to_supabase

                    data = {
                        "steps": {"steps": 14000, "goal": 15000},
                        "sleep": {"total_hours": 7.5, "quality_score": 80},
                        "heart_rate": {"resting": 58},
                        "hrv": {"weekly_avg": 45, "last_night": 42, "status": "BALANCED"},
                        "stress": {"average": 30},
                    }

                    await _sync_garmin_to_supabase("2026-05-01", data)

                    assert mock_client.post.called
                    call_args = mock_client.post.call_args
                    record = call_args.kwargs.get("json") or call_args[1].get("json")

                    assert record["hrv_weekly_avg"] == 45
                    assert record["hrv_last_night"] == 42
                    assert record["hrv_status"] == "BALANCED"
                    assert record["avg_stress"] == 30
                    assert record["steps"] == 14000
                    assert record["sleep_hours"] == 7.5
                    assert record["resting_hr"] == 58

    @pytest.mark.asyncio
    async def test_sync_without_hrv_data(self):
        """HRV/stress fields should be absent when Garmin didn't return them."""
        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_resp = Mock(status_code=201, text="ok")
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value.__aenter__.return_value = mock_client

            with patch.dict(os.environ, {"SUPABASE_URL": "https://test.co", "SUPABASE_KEY": "k"}):
                import config as cfg_mod
                with (
                    patch.object(cfg_mod, "SUPABASE_URL", "https://test.co", create=True),
                    patch.object(cfg_mod, "SUPABASE_KEY", "k", create=True),
                ):
                    from domains.peterbot.data_fetchers import _sync_garmin_to_supabase

                    data = {
                        "steps": {"steps": 10000, "goal": 15000},
                        "sleep": {"total_hours": 6.0},
                        "heart_rate": {"resting": 62},
                        "hrv": {},
                        "stress": {},
                    }

                    await _sync_garmin_to_supabase("2026-05-01", data)

                    call_args = mock_client.post.call_args
                    record = call_args.kwargs.get("json") or call_args[1].get("json")

                    assert "hrv_weekly_avg" not in record
                    assert "avg_stress" not in record
                    assert record["steps"] == 10000


# ── E2E scenario tests ──────────────────────────────────────────────


class TestE2EScenarios:
    """Full pipeline E2E tests: build snapshot → evaluate → get_advice."""

    @pytest.mark.asyncio
    async def test_under_eating_on_training_day_produces_warnings(self):
        with patch("domains.fitness.advisor.build_snapshot") as mock_build:
            mock_build.return_value = Snapshot(
                programme_active=True,
                week_no=5,
                day_no=30,
                is_training_day=True,
                session_type="legs",
                calories_eaten=1400,
                calories_target=2343,
                protein_eaten=70,
                protein_target=150,
                hour_of_day=17,
                current_weight_kg=86.0,
                slope_kg_per_week=-0.8,
                sleep_score=45,
                mobility_streak=0,
                mobility_done_today=False,
            )

            result = await get_advice()
            severities = [a["severity"] for a in result["advice"]]
            categories = [a["category"] for a in result["advice"]]

            assert "warning" in severities
            assert "energy_balance" in categories
            assert "nutrition" in categories
            assert result["counts"]["warning"] >= 2

    @pytest.mark.asyncio
    async def test_perfect_day_produces_positives(self):
        with patch("domains.fitness.advisor.build_snapshot") as mock_build:
            mock_build.return_value = Snapshot(
                programme_active=True,
                week_no=4,
                calories_eaten=2300,
                calories_target=2343,
                protein_eaten=148,
                protein_target=150,
                steps_today=15500,
                steps_target=15000,
                hour_of_day=21,
                current_weight_kg=87.0,
                slope_kg_per_week=-0.65,
                sleep_score=88,
                sleep_hours=8.2,
                mobility_streak=10,
                mobility_done_today=True,
                strength_sessions_week=4,
                strength_target=4,
                hrv_status="BALANCED",
                resting_hr=58,
                resting_hr_5d=[58, 58, 57, 57, 58],
            )

            result = await get_advice()
            severities = [a["severity"] for a in result["advice"]]

            assert "positive" in severities
            assert "warning" not in severities
            has_nailing_it = any("nailing" in a["headline"].lower() for a in result["advice"])
            assert has_nailing_it

    @pytest.mark.asyncio
    async def test_stalled_weight_with_poor_adherence_suggests_diet_break(self):
        with patch("domains.fitness.advisor.build_snapshot") as mock_build:
            mock_build.return_value = Snapshot(
                programme_active=True,
                week_no=8,
                weight_stalled=True,
                avg_protein_pct_this_week=55.0,
                current_weight_kg=84.0,
                calories_eaten=2000,
                calories_target=2200,
            )

            result = await get_advice()
            headlines = [a["headline"].lower() for a in result["advice"]]

            assert any("diet break" in h for h in headlines)

    @pytest.mark.asyncio
    async def test_recovery_warnings_on_bad_sleep_high_stress(self):
        with patch("domains.fitness.advisor.build_snapshot") as mock_build:
            mock_build.return_value = Snapshot(
                programme_active=True,
                is_training_day=True,
                session_type="push",
                sleep_score=40,
                stress_avg=65,
                resting_hr_5d=[65, 64, 63, 61, 60],
                hrv_status="LOW",
                calories_eaten=2000,
                calories_target=2343,
            )

            result = await get_advice()
            categories = [a["category"] for a in result["advice"]]

            assert "recovery" in categories
            assert sum(1 for c in categories if c == "recovery") >= 2

"""Unit tests for the auto-update engine.

Tests the AUTO_SOURCE_REGISTRY, fetch_auto_value, and run_auto_updates.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date


class TestAutoSourceRegistry:
    """Tests for the registry structure."""

    def test_registry_has_expected_sources(self):
        from domains.accountability.auto_sources import AUTO_SOURCE_REGISTRY
        expected = ["garmin_steps", "garmin_sleep", "nutrition_calories",
                    "nutrition_water", "nutrition_protein", "weight"]
        for key in expected:
            assert key in AUTO_SOURCE_REGISTRY, f"Missing source: {key}"

    def test_registry_entries_have_required_fields(self):
        from domains.accountability.auto_sources import AUTO_SOURCE_REGISTRY
        for key, config in AUTO_SOURCE_REGISTRY.items():
            assert "table" in config, f"{key} missing 'table'"
            assert "column" in config, f"{key} missing 'column'"
            assert "date_col" in config, f"{key} missing 'date_col'"
            assert "agg" in config, f"{key} missing 'agg'"
            assert config["agg"] in ("latest", "sum_today"), f"{key} has invalid agg: {config['agg']}"

    def test_garmin_steps_config(self):
        from domains.accountability.auto_sources import AUTO_SOURCE_REGISTRY
        cfg = AUTO_SOURCE_REGISTRY["garmin_steps"]
        assert cfg["table"] == "garmin_daily_summary"
        assert cfg["column"] == "steps"
        assert cfg["agg"] == "latest"

    def test_nutrition_calories_config(self):
        from domains.accountability.auto_sources import AUTO_SOURCE_REGISTRY
        cfg = AUTO_SOURCE_REGISTRY["nutrition_calories"]
        assert cfg["table"] == "nutrition_logs"
        assert cfg["column"] == "calories"
        assert cfg["agg"] == "sum_today"


class TestFetchAutoValue:
    """Tests for fetch_auto_value."""

    @pytest.mark.asyncio
    async def test_fetch_latest_value(self):
        from domains.accountability.auto_sources import fetch_auto_value
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"steps": 11234}]

        with patch("domains.accountability.auto_sources.SUPABASE_URL", "https://test.supabase.co"), \
             patch("domains.accountability.auto_sources.SUPABASE_KEY", "test-key"), \
             patch("domains.accountability.auto_sources.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            val = await fetch_auto_value("garmin_steps", "2026-03-31")
            assert val == 11234.0

    @pytest.mark.asyncio
    async def test_fetch_sum_today_value(self):
        from domains.accountability.auto_sources import fetch_auto_value
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"calories": 450, "logged_at": "2026-03-31T08:00:00"},
            {"calories": 600, "logged_at": "2026-03-31T12:30:00"},
            {"calories": 350, "logged_at": "2026-03-31T15:00:00"},
        ]

        with patch("domains.accountability.auto_sources.SUPABASE_URL", "https://test.supabase.co"), \
             patch("domains.accountability.auto_sources.SUPABASE_KEY", "test-key"), \
             patch("domains.accountability.auto_sources.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            val = await fetch_auto_value("nutrition_calories", "2026-03-31")
            assert val == 1400.0

    @pytest.mark.asyncio
    async def test_fetch_unknown_source(self):
        from domains.accountability.auto_sources import fetch_auto_value
        val = await fetch_auto_value("nonexistent_source")
        assert val is None

    @pytest.mark.asyncio
    async def test_fetch_no_data(self):
        from domains.accountability.auto_sources import fetch_auto_value
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []

        with patch("domains.accountability.auto_sources.SUPABASE_URL", "https://test.supabase.co"), \
             patch("domains.accountability.auto_sources.SUPABASE_KEY", "test-key"), \
             patch("domains.accountability.auto_sources.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
            val = await fetch_auto_value("garmin_steps", "2026-03-31")
            assert val is None

    @pytest.mark.asyncio
    async def test_fetch_no_credentials(self):
        from domains.accountability.auto_sources import fetch_auto_value
        with patch("domains.accountability.auto_sources.SUPABASE_URL", ""), \
             patch("domains.accountability.auto_sources.SUPABASE_KEY", ""):
            val = await fetch_auto_value("garmin_steps")
            assert val is None

    @pytest.mark.asyncio
    async def test_fetch_network_error(self):
        from domains.accountability.auto_sources import fetch_auto_value
        with patch("domains.accountability.auto_sources.SUPABASE_URL", "https://test.supabase.co"), \
             patch("domains.accountability.auto_sources.SUPABASE_KEY", "test-key"), \
             patch("domains.accountability.auto_sources.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=Exception("timeout"))
            val = await fetch_auto_value("garmin_steps")
            assert val is None


class TestRunAutoUpdates:
    """Tests for run_auto_updates."""

    @pytest.mark.asyncio
    async def test_auto_updates_skips_manual_goals(self):
        from domains.accountability.auto_sources import run_auto_updates
        mock_goal_no_source = {
            "id": "g1", "title": "Manual Goal", "auto_source": None, "status": "active"
        }
        with patch("domains.accountability.service.get_goals", new_callable=AsyncMock) as mock_get, \
             patch("domains.accountability.service.log_progress", new_callable=AsyncMock) as mock_log:
            mock_get.return_value = [mock_goal_no_source]
            result = await run_auto_updates()
            mock_log.assert_not_called()
            assert result["updated"] == 0

    @pytest.mark.asyncio
    async def test_auto_updates_processes_auto_goals(self):
        from domains.accountability.auto_sources import run_auto_updates
        mock_goal = {
            "id": "g1", "title": "Steps", "auto_source": "garmin_steps", "status": "active"
        }
        with patch("domains.accountability.service.get_goals", new_callable=AsyncMock) as mock_get, \
             patch("domains.accountability.auto_sources.fetch_auto_value", new_callable=AsyncMock) as mock_fetch, \
             patch("domains.accountability.service.log_progress", new_callable=AsyncMock) as mock_log:
            mock_get.return_value = [mock_goal]
            mock_fetch.return_value = 11234
            mock_log.return_value = {"id": "p1", "value": 11234}
            result = await run_auto_updates()
            assert result["updated"] == 1
            mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_updates_skips_null_values(self):
        from domains.accountability.auto_sources import run_auto_updates
        mock_goal = {
            "id": "g1", "title": "Steps", "auto_source": "garmin_steps", "status": "active"
        }
        with patch("domains.accountability.service.get_goals", new_callable=AsyncMock) as mock_get, \
             patch("domains.accountability.auto_sources.fetch_auto_value", new_callable=AsyncMock) as mock_fetch, \
             patch("domains.accountability.service.log_progress", new_callable=AsyncMock) as mock_log:
            mock_get.return_value = [mock_goal]
            mock_fetch.return_value = None  # No data available
            result = await run_auto_updates()
            assert result["skipped"] == 1
            mock_log.assert_not_called()

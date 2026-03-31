"""Tests for accountability skill files and data fetcher registration.

Validates skill YAML frontmatter, content structure, and data fetcher registration.
"""

import os
import pytest
from pathlib import Path

SKILLS_DIR = Path("domains/peterbot/wsl_config/skills")
SCHEDULE_PATH = Path("domains/peterbot/wsl_config/SCHEDULE.md")


class TestSkillFiles:
    """Verify all three accountability skill files exist and are well-formed."""

    @pytest.mark.parametrize("skill_name", [
        "accountability-update",
        "accountability-weekly",
        "accountability-monthly",
    ])
    def test_skill_file_exists(self, skill_name):
        path = SKILLS_DIR / skill_name / "SKILL.md"
        assert path.exists(), f"Skill file not found: {path}"

    @pytest.mark.parametrize("skill_name", [
        "accountability-update",
        "accountability-weekly",
        "accountability-monthly",
    ])
    def test_skill_has_frontmatter(self, skill_name):
        path = SKILLS_DIR / skill_name / "SKILL.md"
        content = path.read_text(encoding="utf-8")
        assert content.startswith("---"), f"{skill_name} missing frontmatter"
        # Should have a closing ---
        parts = content.split("---")
        assert len(parts) >= 3, f"{skill_name} frontmatter not properly closed"

    @pytest.mark.parametrize("skill_name,expected_scheduled", [
        ("accountability-update", "false"),
        ("accountability-weekly", "true"),
        ("accountability-monthly", "true"),
    ])
    def test_skill_scheduled_flag(self, skill_name, expected_scheduled):
        path = SKILLS_DIR / skill_name / "SKILL.md"
        content = path.read_text(encoding="utf-8")
        assert f"scheduled: {expected_scheduled}" in content

    def test_update_skill_is_conversational(self):
        path = SKILLS_DIR / "accountability-update" / "SKILL.md"
        content = path.read_text(encoding="utf-8")
        assert "conversational: true" in content

    def test_weekly_skill_targets_whatsapp(self):
        path = SKILLS_DIR / "accountability-weekly" / "SKILL.md"
        content = path.read_text(encoding="utf-8")
        assert "WhatsApp:chris" in content

    def test_monthly_skill_targets_both_channels(self):
        path = SKILLS_DIR / "accountability-monthly" / "SKILL.md"
        content = path.read_text(encoding="utf-8")
        assert "#food-log" in content
        assert "WhatsApp:chris" in content

    def test_update_skill_has_api_endpoints(self):
        path = SKILLS_DIR / "accountability-update" / "SKILL.md"
        content = path.read_text(encoding="utf-8")
        assert "/accountability/goals" in content
        assert "/accountability/goals/{id}/progress" in content or "/goals/{id}/progress" in content

    def test_weekly_skill_has_output_format(self):
        path = SKILLS_DIR / "accountability-weekly" / "SKILL.md"
        content = path.read_text(encoding="utf-8")
        assert "NO_REPLY" in content
        assert "progress" in content.lower() or "Progress" in content


class TestScheduleEntries:
    """Verify schedule entries are present for weekly and monthly reports."""

    def test_schedule_file_exists(self):
        assert SCHEDULE_PATH.exists()

    def test_weekly_accountability_scheduled(self):
        content = SCHEDULE_PATH.read_text(encoding="utf-8")
        assert "accountability-weekly" in content
        assert "Sunday" in content

    def test_monthly_accountability_scheduled(self):
        content = SCHEDULE_PATH.read_text(encoding="utf-8")
        assert "accountability-monthly" in content
        assert "1st" in content


class TestDataFetcherRegistration:
    """Verify data fetchers are registered in the SKILL_DATA_FETCHERS dict."""

    def test_weekly_fetcher_registered(self):
        from domains.peterbot.data_fetchers import SKILL_DATA_FETCHERS
        assert "accountability-weekly" in SKILL_DATA_FETCHERS

    def test_monthly_fetcher_registered(self):
        from domains.peterbot.data_fetchers import SKILL_DATA_FETCHERS
        assert "accountability-monthly" in SKILL_DATA_FETCHERS

    def test_weekly_fetcher_is_callable(self):
        from domains.peterbot.data_fetchers import SKILL_DATA_FETCHERS
        fetcher = SKILL_DATA_FETCHERS["accountability-weekly"]
        assert callable(fetcher)

    def test_monthly_fetcher_is_callable(self):
        from domains.peterbot.data_fetchers import SKILL_DATA_FETCHERS
        fetcher = SKILL_DATA_FETCHERS["accountability-monthly"]
        assert callable(fetcher)


class TestMigrationFile:
    """Verify the migration SQL file exists and has the right structure."""

    def test_migration_file_exists(self):
        path = Path("supabase/migrations/20260331_accountability_tracker.sql")
        assert path.exists()

    def test_migration_creates_three_tables(self):
        path = Path("supabase/migrations/20260331_accountability_tracker.sql")
        content = path.read_text(encoding="utf-8")
        assert "accountability_goals" in content
        assert "accountability_milestones" in content
        assert "accountability_progress" in content

    def test_migration_has_dedup_index(self):
        path = Path("supabase/migrations/20260331_accountability_tracker.sql")
        content = path.read_text(encoding="utf-8")
        assert "idx_progress_dedup" in content

    def test_migration_has_trigger(self):
        path = Path("supabase/migrations/20260331_accountability_tracker.sql")
        content = path.read_text(encoding="utf-8")
        assert "trg_goals_updated" in content

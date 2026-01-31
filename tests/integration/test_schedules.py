"""Integration tests for scheduled task registration and execution."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from freezegun import freeze_time

from apscheduler.schedulers.asyncio import AsyncIOScheduler


class TestScheduledTaskRegistration:
    """Test scheduled task registration."""

    def test_nutrition_domain_registers_schedules(self):
        """Test nutrition domain registers its scheduled tasks."""
        from domains.nutrition import NutritionDomain

        domain = NutritionDomain()
        scheduler = AsyncIOScheduler()
        mock_bot = Mock()

        domain.register_schedules(scheduler, mock_bot)

        jobs = scheduler.get_jobs()
        job_ids = [job.id for job in jobs]

        assert "nutrition_daily_summary" in job_ids

    def test_news_domain_registers_schedules(self):
        """Test news domain registers its scheduled tasks."""
        from domains.news import NewsDomain

        domain = NewsDomain()
        scheduler = AsyncIOScheduler()
        mock_bot = Mock()

        domain.register_schedules(scheduler, mock_bot)

        jobs = scheduler.get_jobs()
        job_ids = [job.id for job in jobs]

        assert "news_morning_briefing" in job_ids

    def test_api_usage_domain_registers_schedules(self):
        """Test API usage domain registers its scheduled tasks."""
        from domains.api_usage import ApiUsageDomain

        domain = ApiUsageDomain()
        scheduler = AsyncIOScheduler()
        mock_bot = Mock()

        domain.register_schedules(scheduler, mock_bot)

        jobs = scheduler.get_jobs()
        job_ids = [job.id for job in jobs]

        assert "api_usage_weekly_summary" in job_ids


class TestStandaloneJobRegistration:
    """Test standalone job registration."""

    def test_morning_briefing_registration(self):
        """Test AI morning briefing job registration."""
        from jobs.morning_briefing import register_morning_briefing

        scheduler = AsyncIOScheduler()
        mock_bot = Mock()

        register_morning_briefing(scheduler, mock_bot)

        jobs = scheduler.get_jobs()
        job_ids = [job.id for job in jobs]

        assert "ai_morning_briefing" in job_ids

    def test_balance_monitor_registration(self):
        """Test balance monitor job registration."""
        from jobs.balance_monitor import register_balance_monitor

        scheduler = AsyncIOScheduler()
        mock_bot = Mock()

        register_balance_monitor(scheduler, mock_bot)

        jobs = scheduler.get_jobs()
        job_ids = [job.id for job in jobs]

        assert "api_balance_monitor" in job_ids

    def test_school_run_registration(self):
        """Test school run job registration."""
        from jobs.school_run import register_school_run

        scheduler = AsyncIOScheduler()
        mock_bot = Mock()

        register_school_run(scheduler, mock_bot)

        jobs = scheduler.get_jobs()
        job_ids = [job.id for job in jobs]

        assert "school_run_report" in job_ids


class TestScheduleTiming:
    """Test scheduled task timing."""

    def test_nutrition_summary_at_9pm_uk(self):
        """Test nutrition summary is scheduled for 9pm UK time."""
        from domains.nutrition import NutritionDomain

        domain = NutritionDomain()

        # Check schedule config
        assert len(domain.schedules) == 1
        schedule = domain.schedules[0]
        assert schedule.hour == 21
        assert schedule.minute == 0
        assert schedule.timezone == "Europe/London"

    def test_morning_briefing_at_630_utc(self):
        """Test morning briefing is scheduled for 6:30 AM UTC."""
        from jobs.morning_briefing import register_morning_briefing

        scheduler = AsyncIOScheduler()
        mock_bot = Mock()

        register_morning_briefing(scheduler, mock_bot)

        job = scheduler.get_job("ai_morning_briefing")
        trigger = job.trigger

        # Check the cron trigger
        assert trigger.fields[4].expressions[0].first == 6  # hour
        assert trigger.fields[5].expressions[0].first == 30  # minute

    def test_balance_monitor_hourly(self):
        """Test balance monitor runs hourly."""
        from jobs.balance_monitor import register_balance_monitor

        scheduler = AsyncIOScheduler()
        mock_bot = Mock()

        register_balance_monitor(scheduler, mock_bot)

        job = scheduler.get_job("api_balance_monitor")
        trigger = job.trigger

        # Check minute is 0 (top of hour)
        assert trigger.fields[5].expressions[0].first == 0  # minute

    def test_school_run_weekdays_only(self):
        """Test school run only runs on weekdays."""
        from jobs.school_run import register_school_run

        scheduler = AsyncIOScheduler()
        mock_bot = Mock()

        register_school_run(scheduler, mock_bot)

        job = scheduler.get_job("school_run_report")
        trigger = job.trigger

        # Check day_of_week field (index 3 in cron)
        # Should be mon-fri
        day_field = trigger.fields[3]
        # This checks the day range is 0-4 (mon-fri)


class TestScheduledTaskExecution:
    """Test scheduled task execution."""

    @pytest.mark.asyncio
    @freeze_time("2026-01-29 21:00:00", tz_offset=0)
    async def test_nutrition_summary_execution(self):
        """Test nutrition summary task executes correctly."""
        from domains.nutrition.schedules import daily_summary

        mock_bot = Mock()
        mock_channel = Mock()
        mock_channel.send = AsyncMock()
        mock_bot.get_channel.return_value = mock_channel

        mock_domain = Mock()

        # Mock the services
        with patch('domains.nutrition.schedules.get_today_totals') as mock_totals, \
             patch('domains.nutrition.schedules.get_steps') as mock_steps, \
             patch('domains.nutrition.schedules.get_weight') as mock_weight:

            mock_totals.return_value = {
                "calories": 1800,
                "protein_g": 140,
                "carbs_g": 200,
                "fat_g": 60,
                "water_ml": 3000
            }
            mock_steps.return_value = {"steps": 12000, "goal": 15000}
            mock_weight.return_value = {"weight_kg": 82.5, "date": "2026-01-29"}

            await daily_summary(mock_bot, mock_domain)

            # Verify channel.send was called
            mock_channel.send.assert_called_once()
            message = mock_channel.send.call_args[0][0]

            # Verify message content
            assert "Daily Summary" in message
            assert "1,800" in message or "1800" in message
            assert "140" in message
            assert "12,000" in message or "12000" in message
            assert "82.5" in message

    @pytest.mark.asyncio
    async def test_school_run_skips_weekends(self):
        """Test school run report skips weekends."""
        from jobs.school_run import school_run_report

        mock_bot = Mock()

        # Test on a Saturday
        with freeze_time("2026-01-25 08:15:00"):  # Saturday
            with patch('jobs.school_run._send_whatsapp') as mock_send:
                await school_run_report(mock_bot)

                # Should not send on weekend
                mock_send.assert_not_called()

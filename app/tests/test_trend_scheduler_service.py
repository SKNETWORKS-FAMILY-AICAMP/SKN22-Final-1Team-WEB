from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from app.services.trend_scheduler import (
    TrendSchedulerConfig,
    choose_next_run,
    compute_next_weekly_run,
    execute_scheduled_refresh,
    should_autostart_scheduler,
)


class TrendSchedulerServiceTests(SimpleTestCase):
    def test_compute_next_weekly_run_rolls_to_next_week_when_time_passed(self):
        now = datetime(2026, 3, 27, 11, 13, tzinfo=ZoneInfo("Asia/Seoul"))

        scheduled = compute_next_weekly_run(
            now=now,
            weekly_day="fri",
            weekly_hour=8,
            weekly_minute=0,
        )

        self.assertEqual(scheduled.isoformat(), "2026-04-03T08:00:00+09:00")

    def test_choose_next_run_prefers_test_run_before_weekly(self):
        config = TrendSchedulerConfig(
            timezone_name="Asia/Seoul",
            weekly_day="fri",
            weekly_hour=8,
            weekly_minute=0,
            test_run_at=datetime(2026, 3, 27, 11, 30, tzinfo=ZoneInfo("Asia/Seoul")),
        )
        now = datetime(2026, 3, 27, 11, 13, tzinfo=ZoneInfo("Asia/Seoul"))

        run_type, scheduled = choose_next_run(
            now=now,
            config=config,
            test_run_completed=False,
        )

        self.assertEqual(run_type, "test")
        self.assertEqual(scheduled.isoformat(), "2026-03-27T11:30:00+09:00")

    def test_execute_scheduled_refresh_writes_success_record(self):
        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "trend_scheduler_runs.jsonl"
            config = TrendSchedulerConfig(
                log_path=log_path,
                steps=["crawl", "refine", "llm_refine", "vectorize"],
            )

            with (
                patch("app.services.trend_scheduler.try_acquire_scheduler_lock", return_value=True),
                patch("app.services.trend_scheduler.release_scheduler_lock", return_value=None),
                patch(
                    "app.services.trend_scheduler.trigger_local_trend_refresh",
                    return_value={"local_pipeline": {"success": True}},
                ) as mock_trigger,
            ):
                record = execute_scheduled_refresh(
                    config,
                    run_type="test",
                    scheduled_for=datetime(2026, 3, 27, 11, 30, tzinfo=ZoneInfo("Asia/Seoul")),
                )

            self.assertTrue(record["success"])
            self.assertTrue(log_path.exists())
            mock_trigger.assert_called_once()

    def test_execute_scheduled_refresh_skips_when_lock_not_acquired(self):
        with TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "trend_scheduler_runs.jsonl"
            config = TrendSchedulerConfig(log_path=log_path)

            with (
                patch("app.services.trend_scheduler.try_acquire_scheduler_lock", return_value=False),
                patch("app.services.trend_scheduler.trigger_local_trend_refresh") as mock_trigger,
            ):
                record = execute_scheduled_refresh(
                    config,
                    run_type="weekly",
                    scheduled_for=datetime(2026, 3, 27, 8, 0, tzinfo=ZoneInfo("Asia/Seoul")),
                )

        self.assertTrue(record["success"])
        self.assertTrue(record["skipped"])
        self.assertEqual(record["reason"], "scheduler_lock_not_acquired")
        mock_trigger.assert_not_called()

    def test_default_scheduler_steps_exclude_optional_style_rebuild(self):
        config = TrendSchedulerConfig()

        self.assertEqual(
            config.normalized_steps(),
            ["crawl", "refine", "llm_refine", "vectorize", "rebuild_ncs"],
        )

    @override_settings(TREND_SCHEDULER_ENABLED=True)
    def test_should_autostart_scheduler_for_runserver_reloader_child(self):
        with patch.object(sys, "argv", ["manage.py", "runserver"]), patch.dict(os.environ, {"RUN_MAIN": "true"}, clear=False):
            self.assertTrue(should_autostart_scheduler())

    @override_settings(TREND_SCHEDULER_ENABLED=True)
    def test_should_autostart_scheduler_for_gunicorn_when_enabled(self):
        with patch.object(sys, "argv", ["gunicorn", "mirrai_project.wsgi:application"]), patch.dict(os.environ, {}, clear=False):
            self.assertTrue(should_autostart_scheduler())

    @override_settings(TREND_SCHEDULER_ENABLED=False)
    def test_should_not_autostart_scheduler_when_disabled(self):
        with patch.object(sys, "argv", ["gunicorn", "mirrai_project.wsgi:application"]), patch.dict(os.environ, {}, clear=False):
            self.assertFalse(should_autostart_scheduler())

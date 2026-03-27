from __future__ import annotations

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from app.services.trend_scheduler import TrendSchedulerConfig, build_test_datetime, run_scheduler_loop


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the in-project trend scheduler loop."

    def add_arguments(self, parser):
        parser.add_argument("--timezone", default=getattr(settings, "TREND_SCHEDULER_TIMEZONE", "Asia/Seoul"))
        parser.add_argument("--weekly-day", default=getattr(settings, "TREND_SCHEDULER_WEEKLY_DAY", "fri"))
        parser.add_argument("--weekly-hour", type=int, default=getattr(settings, "TREND_SCHEDULER_WEEKLY_HOUR", 8))
        parser.add_argument("--weekly-minute", type=int, default=getattr(settings, "TREND_SCHEDULER_WEEKLY_MINUTE", 0))
        parser.add_argument(
            "--steps",
            default=getattr(settings, "TREND_SCHEDULER_STEPS", "crawl,refine,llm_refine,vectorize,rebuild_styles"),
            help="Comma-separated local build steps before archive upload.",
        )
        parser.add_argument(
            "--include-ncs",
            action="store_true",
            default=bool(getattr(settings, "TREND_SCHEDULER_INCLUDE_NCS", False)),
            help="Include chromadb_ncs in the uploaded archive.",
        )
        parser.add_argument(
            "--include-styles",
            action="store_true",
            default=bool(getattr(settings, "TREND_SCHEDULER_INCLUDE_STYLES", False)),
            help="Include chromadb_styles in the uploaded archive.",
        )
        parser.add_argument("--timeout", type=int, default=getattr(settings, "TREND_SCHEDULER_TIMEOUT", 1800))
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=float(getattr(settings, "TREND_SCHEDULER_POLL_INTERVAL", 5.0)),
        )
        parser.add_argument(
            "--sleep-interval",
            type=float,
            default=float(getattr(settings, "TREND_SCHEDULER_SLEEP_INTERVAL", 15.0)),
        )
        parser.add_argument(
            "--test-at",
            default=getattr(settings, "TREND_SCHEDULER_TEST_AT", ""),
            help="One-off test run time in 'YYYY-MM-DD HH:MM' format.",
        )
        parser.add_argument(
            "--exit-after-test",
            action="store_true",
            help="Exit after the one-off test run finishes.",
        )

    def handle(self, *args, **options):
        weekly_day = str(options["weekly_day"]).strip().lower()
        if weekly_day not in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
            raise CommandError("weekly-day must be one of: mon,tue,wed,thu,fri,sat,sun")

        try:
            test_run_at = build_test_datetime(options["test_at"], options["timezone"])
        except ValueError as exc:
            raise CommandError("test-at must match 'YYYY-MM-DD HH:MM'") from exc

        config = TrendSchedulerConfig(
            timezone_name=options["timezone"],
            weekly_day=weekly_day,
            weekly_hour=options["weekly_hour"],
            weekly_minute=options["weekly_minute"],
            steps=[item.strip() for item in str(options["steps"]).split(",") if item.strip()],
            include_ncs=bool(options["include_ncs"]),
            include_styles=bool(options["include_styles"]),
            runpod_timeout=options["timeout"],
            runpod_poll_interval=options["poll_interval"],
            sleep_interval_seconds=options["sleep_interval"],
            test_run_at=test_run_at,
        )

        logger.info(
            "[trend_scheduler] start timezone=%s weekly=%s %02d:%02d test_at=%s",
            config.timezone_name,
            config.weekly_day,
            config.weekly_hour,
            config.weekly_minute,
            (config.test_run_at.isoformat() if config.test_run_at else ""),
        )
        run_scheduler_loop(config, exit_after_test=bool(options["exit_after_test"]))

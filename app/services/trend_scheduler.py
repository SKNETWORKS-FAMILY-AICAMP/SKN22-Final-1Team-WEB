from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection

from app.services.trend_refresh import parse_refresh_steps, trigger_local_trend_refresh
from app.trend_pipeline.paths import RAG_DIR


logger = logging.getLogger(__name__)

WEEKDAY_TO_INT = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}
DEFAULT_STEPS = ["crawl", "refine", "llm_refine", "vectorize", "rebuild_ncs", "rebuild_styles"]
DEFAULT_LOG_PATH = RAG_DIR / "logs" / "trend_scheduler_runs.jsonl"
SCHEDULER_LOCK_NAMESPACE = 143
_SCHEDULER_THREAD: threading.Thread | None = None
_SCHEDULER_THREAD_LOCK = threading.Lock()


@dataclass(slots=True)
class TrendSchedulerConfig:
    timezone_name: str = "Asia/Seoul"
    weekly_day: str = "fri"
    weekly_hour: int = 8
    weekly_minute: int = 0
    steps: list[str] | None = None
    include_ncs: bool = False
    include_styles: bool = False
    runpod_timeout: int = 1800
    runpod_poll_interval: float = 5.0
    sleep_interval_seconds: float = 15.0
    test_run_at: datetime | None = None
    log_path: Path = DEFAULT_LOG_PATH

    def normalized_steps(self) -> list[str]:
        return parse_refresh_steps(self.steps) or list(DEFAULT_STEPS)


def build_scheduler_config_from_settings() -> TrendSchedulerConfig:
    try:
        test_run_at = build_test_datetime(
            getattr(settings, "TREND_SCHEDULER_TEST_AT", ""),
            getattr(settings, "TREND_SCHEDULER_TIMEZONE", "Asia/Seoul"),
        )
    except ValueError:
        test_run_at = None

    return TrendSchedulerConfig(
        timezone_name=getattr(settings, "TREND_SCHEDULER_TIMEZONE", "Asia/Seoul"),
        weekly_day=str(getattr(settings, "TREND_SCHEDULER_WEEKLY_DAY", "fri")).strip().lower(),
        weekly_hour=int(getattr(settings, "TREND_SCHEDULER_WEEKLY_HOUR", 8)),
        weekly_minute=int(getattr(settings, "TREND_SCHEDULER_WEEKLY_MINUTE", 0)),
        steps=[
            item.strip()
            for item in str(getattr(settings, "TREND_SCHEDULER_STEPS", ",".join(DEFAULT_STEPS))).split(",")
            if item.strip()
        ],
        include_ncs=bool(getattr(settings, "TREND_SCHEDULER_INCLUDE_NCS", False)),
        include_styles=bool(getattr(settings, "TREND_SCHEDULER_INCLUDE_STYLES", False)),
        runpod_timeout=int(getattr(settings, "TREND_SCHEDULER_TIMEOUT", 1800)),
        runpod_poll_interval=float(getattr(settings, "TREND_SCHEDULER_POLL_INTERVAL", 5.0)),
        sleep_interval_seconds=float(getattr(settings, "TREND_SCHEDULER_SLEEP_INTERVAL", 15.0)),
        test_run_at=test_run_at,
    )


def should_autostart_scheduler() -> bool:
    if not bool(getattr(settings, "TREND_SCHEDULER_ENABLED", False)):
        return False

    argv = [str(arg).lower() for arg in sys.argv]
    if "runserver" not in argv:
        return False

    if "--noreload" in argv:
        return True

    return os.environ.get("RUN_MAIN") == "true"


def start_scheduler_background_if_configured() -> bool:
    global _SCHEDULER_THREAD

    if not should_autostart_scheduler():
        return False

    with _SCHEDULER_THREAD_LOCK:
        if _SCHEDULER_THREAD is not None and _SCHEDULER_THREAD.is_alive():
            return False

        config = build_scheduler_config_from_settings()
        thread = threading.Thread(
            target=run_scheduler_loop,
            kwargs={"config": config},
            name="trend-scheduler",
            daemon=True,
        )
        thread.start()
        _SCHEDULER_THREAD = thread

    logger.info(
        "[trend_scheduler] background thread started timezone=%s weekly=%s %02d:%02d",
        config.timezone_name,
        config.weekly_day,
        config.weekly_hour,
        config.weekly_minute,
    )
    print(
        f"[trend_scheduler] auto-started in background "
        f"weekly={config.weekly_day} {config.weekly_hour:02d}:{config.weekly_minute:02d} "
        f"timezone={config.timezone_name}"
    )
    return True


def build_test_datetime(value: str | None, timezone_name: str) -> datetime | None:
    if not value:
        return None

    parsed = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")
    return parsed.replace(tzinfo=ZoneInfo(timezone_name))


def compute_next_weekly_run(
    *,
    now: datetime,
    weekly_day: str,
    weekly_hour: int,
    weekly_minute: int,
) -> datetime:
    weekday = WEEKDAY_TO_INT[weekly_day]
    days_ahead = (weekday - now.weekday()) % 7
    candidate = now.replace(hour=weekly_hour, minute=weekly_minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def choose_next_run(
    *,
    now: datetime,
    config: TrendSchedulerConfig,
    test_run_completed: bool,
) -> tuple[str, datetime]:
    weekly_run = compute_next_weekly_run(
        now=now,
        weekly_day=config.weekly_day,
        weekly_hour=config.weekly_hour,
        weekly_minute=config.weekly_minute,
    )

    if config.test_run_at and not test_run_completed:
        if config.test_run_at <= now:
            return "test", now
        if config.test_run_at < weekly_run:
            return "test", config.test_run_at

    return "weekly", weekly_run


def _scheduler_lock_key(*, run_type: str, scheduled_for: datetime) -> int:
    lock_value = f"{run_type}:{scheduled_for.astimezone(ZoneInfo('UTC')).isoformat()}"
    return zlib.crc32(lock_value.encode("utf-8")) & 0x7FFFFFFF


def try_acquire_scheduler_lock(*, run_type: str, scheduled_for: datetime) -> bool:
    if connection.vendor != "postgresql":
        return True

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_try_advisory_lock(%s, %s)",
            [SCHEDULER_LOCK_NAMESPACE, _scheduler_lock_key(run_type=run_type, scheduled_for=scheduled_for)],
        )
        row = cursor.fetchone()
    return bool(row and row[0])


def release_scheduler_lock(*, run_type: str, scheduled_for: datetime) -> None:
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_unlock(%s, %s)",
            [SCHEDULER_LOCK_NAMESPACE, _scheduler_lock_key(run_type=run_type, scheduled_for=scheduled_for)],
        )


@contextmanager
def scheduler_execution_guard(*, run_type: str, scheduled_for: datetime):
    acquired = try_acquire_scheduler_lock(run_type=run_type, scheduled_for=scheduled_for)
    try:
        yield acquired
    finally:
        if acquired:
            release_scheduler_lock(run_type=run_type, scheduled_for=scheduled_for)


def execute_scheduled_refresh(config: TrendSchedulerConfig, *, run_type: str, scheduled_for: datetime) -> dict[str, Any]:
    started_at = datetime.now(ZoneInfo(config.timezone_name))
    with scheduler_execution_guard(run_type=run_type, scheduled_for=scheduled_for) as lock_acquired:
        if not lock_acquired:
            ended_at = datetime.now(ZoneInfo(config.timezone_name))
            record = {
                "run_type": run_type,
                "scheduled_for": scheduled_for.isoformat(),
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "success": True,
                "skipped": True,
                "reason": "scheduler_lock_not_acquired",
            }
            append_scheduler_record(record, config.log_path)
            print(f"[trend_scheduler] skipped run_type={run_type} reason=scheduler_lock_not_acquired")
            logger.info("[trend_scheduler] skipped run_type=%s because advisory lock was not acquired", run_type)
            return record

        print(
            f"[trend_scheduler] starting run_type={run_type} "
            f"scheduled_for={scheduled_for.isoformat()} "
            f"steps={','.join(config.normalized_steps())}"
        )
        logger.info(
            "[trend_scheduler] run_type=%s scheduled_for=%s steps=%s include_ncs=%s include_styles=%s",
            run_type,
            scheduled_for.isoformat(),
            ",".join(config.normalized_steps()),
            config.include_ncs,
            config.include_styles,
        )

        try:
            result = trigger_local_trend_refresh(
                steps=config.normalized_steps(),
            )
            ended_at = datetime.now(ZoneInfo(config.timezone_name))
            record = {
                "run_type": run_type,
                "scheduled_for": scheduled_for.isoformat(),
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "success": True,
                "result": result,
            }
            append_scheduler_record(record, config.log_path)
            print(f"[trend_scheduler] completed run_type={run_type} success=true")
            logger.info("[trend_scheduler] completed run_type=%s", run_type)
            return record
        except Exception as exc:
            ended_at = datetime.now(ZoneInfo(config.timezone_name))
            record = {
                "run_type": run_type,
                "scheduled_for": scheduled_for.isoformat(),
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
            append_scheduler_record(record, config.log_path)
            print(f"[trend_scheduler] completed run_type={run_type} success=false error={type(exc).__name__}: {exc}")
            logger.exception("[trend_scheduler] failed run_type=%s", run_type)
            raise


def append_scheduler_record(record: dict[str, Any], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_scheduler_loop(
    config: TrendSchedulerConfig,
    *,
    exit_after_test: bool = False,
) -> None:
    timezone = ZoneInfo(config.timezone_name)
    test_run_completed = False

    while True:
        now = datetime.now(timezone)
        run_type, scheduled_for = choose_next_run(
            now=now,
            config=config,
            test_run_completed=test_run_completed,
        )
        wait_seconds = max(0.0, (scheduled_for - now).total_seconds())
        print(
            f"[trend_scheduler] next run_type={run_type} "
            f"scheduled_for={scheduled_for.isoformat()} "
            f"wait_seconds={wait_seconds:.1f}"
        )
        logger.info(
            "[trend_scheduler] next run_type=%s scheduled_for=%s wait_seconds=%.1f",
            run_type,
            scheduled_for.isoformat(),
            wait_seconds,
        )

        while wait_seconds > 0:
            time.sleep(min(config.sleep_interval_seconds, wait_seconds))
            now = datetime.now(timezone)
            wait_seconds = (scheduled_for - now).total_seconds()

        execute_scheduled_refresh(config, run_type=run_type, scheduled_for=scheduled_for)

        if run_type == "test":
            test_run_completed = True
            if exit_after_test:
                print("[trend_scheduler] exiting after test run")
                logger.info("[trend_scheduler] exiting after test run")
                return

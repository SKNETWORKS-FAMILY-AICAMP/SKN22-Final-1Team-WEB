from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.services.trend_refresh import parse_refresh_steps, trigger_runpod_trend_refresh_with_archive
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
DEFAULT_STEPS = ["crawl", "refine", "llm_refine", "vectorize"]
DEFAULT_LOG_PATH = RAG_DIR / "logs" / "trend_scheduler_runs.jsonl"


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


def execute_scheduled_refresh(config: TrendSchedulerConfig, *, run_type: str, scheduled_for: datetime) -> dict[str, Any]:
    started_at = datetime.now(ZoneInfo(config.timezone_name))
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
        result = trigger_runpod_trend_refresh_with_archive(
            build_locally=True,
            steps=config.normalized_steps(),
            include_ncs=config.include_ncs,
            include_styles=config.include_styles,
            sync=True,
            wait=True,
            timeout=config.runpod_timeout,
            poll_interval=config.runpod_poll_interval,
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

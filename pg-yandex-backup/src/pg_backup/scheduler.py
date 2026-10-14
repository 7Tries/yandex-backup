"""APScheduler integration."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)


class BackupScheduler:
    """Wraps APScheduler to schedule cron backups."""

    def __init__(self, cron_expr: str, callback: Callable[[], Awaitable[None]]) -> None:
        self._cron = cron_expr
        self._callback = callback
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        parts = self._cron.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {self._cron!r}")
        minute, hour, day, month, day_of_week = parts
        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        )
        self._scheduler.add_job(
            self._callback,
            trigger=trigger,
            id="scheduled_backup",
            replace_existing=True,
        )
        self._scheduler.start()
        log.info("Scheduler started with cron: %s", self._cron)

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        log.info("Scheduler stopped.")

"""Debounce logic: start a backup N seconds after the last change."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)


class DebounceController:
    """Ensures at most one backup runs at a time, with debounce.

    - On change: reset the timer to fire after `delay` seconds.
    - If a backup is already running when the timer fires: schedule another
      one for immediately after the current backup finishes.
    """

    def __init__(self, delay: float, callback: Callable[[], Awaitable[None]]) -> None:
        self._delay = delay
        self._callback = callback
        self._timer_task: asyncio.Task[None] | None = None
        self._running = False
        self._pending = False
        self._lock = asyncio.Lock()

    def trigger(self) -> None:
        """Called when a DB change is detected."""
        if self._timer_task is not None and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = asyncio.ensure_future(self._wait_and_fire())

    async def _wait_and_fire(self) -> None:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            return
        # Launch backup independently so future triggers cancelling the timer
        # will never cancel an actively running backup.
        asyncio.create_task(self._fire())

    async def _fire(self) -> None:
        async with self._lock:
            if self._running:
                log.info("Backup already running; will schedule one after it finishes.")
                self._pending = True
                return
            self._running = True

        try:
            log.info("Debounce timer fired — starting backup.")
            await self._callback()
        except Exception:
            log.exception("Backup callback raised an exception.")
        finally:
            async with self._lock:
                self._running = False
                pending = self._pending
                self._pending = False

            if pending:
                log.info("Pending backup detected — running it now.")
                await self._fire()

    async def fire_immediately(self) -> None:
        """Trigger a backup right now (bypasses debounce timer)."""
        if self._timer_task is not None and not self._timer_task.done():
            self._timer_task.cancel()
        await self._fire()

    async def stop(self) -> None:
        """Cancel any pending timer."""
        if self._timer_task is not None and not self._timer_task.done():
            self._timer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._timer_task

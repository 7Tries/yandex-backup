"""PostgreSQL LISTEN/NOTIFY listener with exponential-backoff reconnect."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

import psycopg

from pg_backup.config import Settings

log = logging.getLogger(__name__)

ChangeCallback = Callable[[], Awaitable[None]]

CHANNEL = "data_changed"
MAX_BACKOFF = 60.0
INITIAL_BACKOFF = 1.0


class PgListener:
    """Async PostgreSQL listener with automatic reconnection."""

    def __init__(
        self,
        settings: Settings,
        on_change: ChangeCallback,
        on_reconnect: ChangeCallback | None = None,
        on_disconnect: Callable[[Exception], Awaitable[None]] | None = None,
    ) -> None:
        self._settings = settings
        self._on_change = on_change
        self._on_reconnect = on_reconnect
        self._on_disconnect = on_disconnect
        self._callback: ChangeCallback | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._connected_once = False

    def set_on_change(self, callback: ChangeCallback) -> None:
        self._callback = callback

    async def start(self) -> None:
        self._stop_event.clear()
        self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        backoff = INITIAL_BACKOFF
        while not self._stop_event.is_set():
            try:
                await self._listen_loop()
                backoff = INITIAL_BACKOFF  # reset on clean exit
                if not self._stop_event.is_set():
                    log.warning(
                        "Listen loop ended; reconnecting in %.1f seconds...", backoff
                    )
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(), timeout=backoff
                        )
                        break
                    except TimeoutError:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("Listener disconnected: %s", exc)
                if self._on_disconnect is not None:
                    try:
                        await self._on_disconnect(exc)
                    except Exception:
                        log.exception("on_disconnect callback failed")
                if self._stop_event.is_set():
                    break
                log.info("Reconnecting in %.1f seconds...", backoff)
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=backoff
                    )
                    break  # stop was requested during the wait
                except TimeoutError:
                    pass
                backoff = min(backoff * 2, MAX_BACKOFF)

    async def _listen_loop(self) -> None:
        dsn = self._settings.postgres_dsn
        log.info("Connecting to PostgreSQL for LISTEN on channel '%s'...", CHANNEL)
        async with await psycopg.AsyncConnection.connect(
            dsn,
            autocommit=True,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
        ) as conn:
            await conn.execute(f"LISTEN {CHANNEL}")
            log.info("Listening on channel '%s'.", CHANNEL)

            # Trigger on_reconnect only on subsequent reconnects, not initial start
            if self._connected_once:
                if self._on_reconnect is not None:
                    log.info("Triggering post-reconnect backup.")
                    try:
                        await self._on_reconnect()
                    except Exception:
                        log.exception("post-reconnect backup failed")
            else:
                self._connected_once = True

            async for notify in conn.notifies():
                if self._stop_event.is_set():
                    break
                log.debug("Received notify: %s", notify.payload)
                cb_target = self._callback or self._on_change
                try:
                    await cb_target()
                except Exception:
                    log.exception("on_change callback failed")

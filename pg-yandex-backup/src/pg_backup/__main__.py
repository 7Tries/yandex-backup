"""Main service entry point."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

import httpx

from pg_backup.backup import PgBackupService
from pg_backup.config import get_settings
from pg_backup.debounce import DebounceController
from pg_backup.listener import PgListener
from pg_backup.logging_setup import setup_logging
from pg_backup.notifier import LogNotifier, TelegramNotifier
from pg_backup.pipeline import BackupPipeline
from pg_backup.rotation import Rotator
from pg_backup.scheduler import BackupScheduler
from pg_backup.uploader import Uploader
from pg_backup.yadisk import YaDiskClient

log = logging.getLogger(__name__)


async def run() -> None:
    setup_logging()
    settings = get_settings()

    # Build notifier
    notifier: TelegramNotifier | LogNotifier
    if settings.telegram_token and settings.telegram_chat_id:
        http_telegram = httpx.AsyncClient(timeout=10.0)
        notifier = TelegramNotifier(
            settings.telegram_token, settings.telegram_chat_id, http_telegram
        )
    else:
        log.warning("Telegram not configured — using log notifier.")
        notifier = LogNotifier()

    # Build Yandex.Disk client
    http_yadisk = httpx.AsyncClient(timeout=120.0)
    yadisk = YaDiskClient(settings.yandex_token, http_yadisk)

    # Build pipeline components
    backup_svc = PgBackupService(settings)
    uploader = Uploader(
        client=yadisk,
        notifier=notifier,
        remote_folder=settings.yandex_backup_folder,
        min_free_bytes=settings.min_free_bytes,
    )
    rotator = Rotator(
        client=yadisk,
        notifier=notifier,
        remote_folder=settings.yandex_backup_folder,
        retention_days=settings.retention_days,
        min_keep=settings.min_keep_backups,
    )
    pipeline = BackupPipeline(
        backup_service=backup_svc,
        uploader=uploader,
        rotator=rotator,
        notifier=notifier,
    )

    async def do_backup() -> None:
        await pipeline.run()

    # Debounce controller
    debounce = DebounceController(
        delay=float(settings.debounce_seconds),
        callback=do_backup,
    )

    async def on_change() -> None:
        debounce.trigger()

    async def on_reconnect() -> None:
        log.warning("Reconnected to DB — running immediate backup.")
        await notifier.notify("🔌 Reconnected to DB. Running immediate backup.")
        await debounce.fire_immediately()

    async def on_disconnect(exc: Exception) -> None:
        await notifier.notify(f"⚠️ Lost DB connection: {exc}")

    listener = PgListener(
        settings=settings,
        on_change=on_change,
        on_reconnect=on_reconnect,
        on_disconnect=on_disconnect,
    )
    listener.set_on_change(on_change)

    scheduler = BackupScheduler(
        cron_expr=settings.backup_cron, callback=debounce.fire_immediately
    )

    # Start listener and scheduler
    await listener.start()
    scheduler.start()

    # Initial backup on startup (runs through debounce controller to prevent concurrency)
    log.info("Running initial backup on startup...")
    await debounce.fire_immediately()

    await notifier.notify("🚀 pg-yandex-backup service started.")

    # Wait for shutdown signal
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("Shutdown signal received.")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _signal_handler)

    try:
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        log.info("Shutdown requested.")
    finally:
        log.info("Shutting down...")
        scheduler.stop()
        await listener.stop()
        await debounce.stop()

        if isinstance(notifier, TelegramNotifier):
            with contextlib.suppress(Exception):
                await notifier.notify("🛑 pg-yandex-backup service stopped.")
            await notifier.aclose()

        await yadisk.aclose()
        await http_yadisk.aclose()
        log.info("Done.")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

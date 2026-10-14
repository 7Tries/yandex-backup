"""Rotation: delete old backups from Yandex.Disk."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from pg_backup.interfaces import Notifier, YandexDiskClient

log = logging.getLogger(__name__)

BACKUP_PREFIX = "backup_"


class Rotator:
    """Deletes old backups from Yandex.Disk while keeping at least K recent ones."""

    def __init__(
        self,
        client: YandexDiskClient,
        notifier: Notifier,
        remote_folder: str,
        retention_days: int,
        min_keep: int,
    ) -> None:
        self._client = client
        self._notifier = notifier
        self._remote_folder = remote_folder
        self._retention_days = retention_days
        self._min_keep = min_keep

    async def rotate(self) -> None:
        """Remove expired backups, keeping at least min_keep recent."""
        items = await self._client.list_folder(self._remote_folder)

        # Only touch files with backup_ prefix
        backups = [
            item
            for item in items
            if item.get("type") == "file"
            and str(item.get("name", "")).startswith(BACKUP_PREFIX)
        ]

        # Sort newest-first
        def _created(item: dict[str, object]) -> datetime:
            raw = str(item.get("created", "1970-01-01T00:00:00+00:00"))
            return datetime.fromisoformat(raw)

        backups.sort(key=_created, reverse=True)

        if len(backups) <= self._min_keep:
            log.info(
                "Rotation: %d backups, nothing to delete (min_keep=%d).",
                len(backups),
                self._min_keep,
            )
            return

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=self._retention_days)
        protected = {str(b["name"]) for b in backups[: self._min_keep]}

        deleted = 0
        for item in backups[self._min_keep :]:
            name = str(item.get("name", ""))
            created = _created(item)
            if created >= cutoff:
                continue  # still within retention window
            if name in protected:
                continue  # never delete the K most recent
            path = str(item.get("path", f"{self._remote_folder}/{name}"))
            log.info(
                "Rotation: moving %s to trash (created=%s).", name, created.isoformat()
            )
            try:
                await self._client.move_to_trash(path)
                deleted += 1
            except Exception:
                log.exception("Failed to trash %s", name)

        log.info("Rotation done: %d file(s) moved to trash.", deleted)
        if deleted:
            await self._notifier.notify(
                f"🗑 Rotation: {deleted} old backup(s) moved to trash."
            )

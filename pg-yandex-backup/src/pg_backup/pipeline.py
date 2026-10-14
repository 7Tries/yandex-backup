"""backup -> upload -> verify -> rotate pipeline."""
from __future__ import annotations

import logging
from pathlib import Path

from pg_backup.interfaces import BackupService, Notifier, YandexDiskClient
from pg_backup.rotation import Rotator
from pg_backup.uploader import Uploader

log = logging.getLogger(__name__)


class BackupPipeline:
    """Runs the full backup -> upload -> rotate pipeline."""

    def __init__(
        self,
        backup_service: BackupService,
        uploader: Uploader,
        rotator: Rotator,
        notifier: Notifier,
    ) -> None:
        self._backup = backup_service
        self._uploader = uploader
        self._rotator = rotator
        self._notifier = notifier

    async def run(self) -> None:
        """Execute full pipeline; delete local file only on success."""
        local_path: Path | None = None
        try:
            local_path = await self._backup.create_backup()
            log.info("Pipeline: backup created at %s", local_path)

            remote_path = await self._uploader.upload(local_path)
            log.info("Pipeline: uploaded to %s", remote_path)

            # Delete local file only after confirmed upload
            local_path.unlink()
            log.info("Pipeline: local file deleted.")
            local_path = None

            await self._rotator.rotate()
            await self._notifier.notify(
                f"✅ Backup completed and uploaded: <code>{remote_path}</code>"
            )
        except Exception as exc:
            log.exception("Pipeline failed")
            await self._notifier.notify(f"❌ Backup pipeline failed: {exc}")
            # Do NOT delete local file on failure — keep for retry

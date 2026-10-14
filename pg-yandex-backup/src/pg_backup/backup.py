"""Creates PostgreSQL backups using pg_dump."""
from __future__ import annotations

import asyncio
import gzip
import logging
from datetime import datetime, timezone
from pathlib import Path

from pg_backup.config import Settings

log = logging.getLogger(__name__)


class PgBackupService:
    """Creates .sql.gz backups via pg_dump."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._backup_dir = Path(settings.local_backup_dir)

    async def create_backup(self) -> Path:
        """Run pg_dump and return the path to the created .sql.gz file."""
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{timestamp}.sql.gz"
        dest = self._backup_dir / filename

        log.info("Starting pg_dump -> %s", dest)
        env = {
            "PGPASSWORD": self._settings.postgres_password,
            "PATH": "/usr/lib/postgresql/16/bin:/usr/bin:/bin",
        }

        cmd = [
            "pg_dump",
            "-h", self._settings.postgres_host,
            "-p", str(self._settings.postgres_port),
            "-U", self._settings.postgres_user,
            "-d", self._settings.postgres_db,
            "--format=plain",
            "--no-password",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            log.error("pg_dump failed: %s", stderr.decode())
            raise RuntimeError(
                f"pg_dump failed (rc={proc.returncode}): {stderr.decode()[:500]}"
            )

        # Compress output
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._compress, stdout, dest)

        size = dest.stat().st_size
        log.info("Backup created: %s (%d bytes)", dest, size)
        return dest

    @staticmethod
    def _compress(data: bytes, dest: Path) -> None:
        with gzip.open(dest, "wb", compresslevel=9) as f:
            f.write(data)

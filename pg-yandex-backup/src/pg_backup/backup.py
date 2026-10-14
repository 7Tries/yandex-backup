"""Creates PostgreSQL backups using pg_dump."""
from __future__ import annotations

import asyncio
import gzip
import logging
import os
from datetime import UTC, datetime
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
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{timestamp}.sql.gz"
        dest = self._backup_dir / filename

        log.info("Starting pg_dump -> %s", dest)

        system_path = os.environ.get("PATH", "")
        pg16_path = "/usr/lib/postgresql/16/bin"
        custom_path = f"{pg16_path}:{system_path}" if pg16_path not in system_path else system_path
        env = {
            **os.environ,
            "PGPASSWORD": self._settings.postgres_password,
            "PATH": custom_path,
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

        async def _drain_stderr() -> bytes:
            if proc.stderr is None:
                return b""
            return await proc.stderr.read()

        stderr_task = asyncio.create_task(_drain_stderr())

        # Stream stdout into gzip file without loading the whole dump into memory
        assert proc.stdout is not None
        with gzip.open(dest, "wb", compresslevel=9) as gz_out:
            while True:
                chunk = await proc.stdout.read(65536)
                if not chunk:
                    break
                gz_out.write(chunk)

        stderr = await stderr_task
        await proc.wait()

        if proc.returncode != 0:
            dest.unlink(missing_ok=True)
            err_msg = stderr.decode(errors="replace")
            log.error("pg_dump failed: %s", err_msg)
            raise RuntimeError(
                f"pg_dump failed (rc={proc.returncode}): {err_msg[:500]}"
            )

        size = dest.stat().st_size
        log.info("Backup created: %s (%d bytes)", dest, size)
        return dest
